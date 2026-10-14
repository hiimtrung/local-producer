"""Install, load, reload and remove engine packages; hand the pipelines the loaded package's runners.

ENGINES_DIR/<id>/<version>/              one installed package (the extracted items, at their `dest`)
ENGINES_DIR/<id>/<version>/package.json  the catalog entry it was installed from (so an older version stays loadable)
ENGINES_DIR/active.json                  {"id", "version"}: what to load at startup
ENGINES_DIR/.cache/                      downloads in progress (resumable), deleted after the install

Loading a package checks, in order: it was built for this machine (host.py), the stack's preflight passes
(backends.py, e.g. cwsr_enable=0 for ROCm), and each runner's self-test exits 0 (proves its libraries resolve,
without touching the GPU). Only then does it become the active package. Each job resolves its runner when it
starts, so loading another package or version takes effect with the next job, without a restart.

Updates: a new version is a reviewed catalog change (pinned hashes), never a download from wherever upstream points.
check_updates() only reports, per pinned component, whether upstream has published a newer release.

CLI (cwd = server/): python -m app.engines.registry status | install [id [version]] | load <id> <version> |
                     remove <id> <version> | updates
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from .. import model_setup
from ..gpu import JobFailed, gpu_lock, log
from ..model_setup import Opener, Progress, SetupError
from ..schemas import ApiModel
from ..settings import paths
from . import backends
from .catalog import Catalog, PackageSpec, Planned, load_catalog, version_key
from .host import HostInfo, detect

SELF_TEST_TIMEOUT = 60


class EngineUnavailable(JobFailed):
    pass


class EngineBusy(RuntimeError):
    pass


@dataclass(frozen=True)
class Runner:
    """A CLI from the loaded package: its path and the environment to start it with."""

    bin: str
    env: dict[str, str]
    package: str


class EngineStatus(ApiModel):
    state: Literal["ready", "none", "blocked"]
    id: str = ""
    version: str = ""
    title: str = ""
    problem: str = Field("", description="Why nothing is loaded, or what blocks the chosen package")
    runners: list[str] = Field(default_factory=list)
    loaded_at: float | None = None


class InstalledPackage(ApiModel):
    id: str
    version: str
    title: str
    size: int
    installed_at: float
    active: bool
    in_catalog: bool = Field(description="False when the catalog no longer lists this version")
    latest: bool = Field(description="The newest catalog version of this package")


class PackageInfo(ApiModel):
    id: str
    version: str
    title: str
    description: str
    accelerator: str
    download_size: int
    compatible: bool
    mismatch: str
    installed: bool
    loaded: bool
    latest: bool = Field(description="The newest catalog version of this package")


class UpstreamRelease(ApiModel):
    package: str
    component: str
    repo: str
    pinned: str
    latest: str = Field(description="Upstream's latest release tag; empty when it could not be read")
    newer: bool
    url: str
    published: str = ""
    error: str = ""


class UpdateReport(ApiModel):
    checked_at: float
    packages: list[PackageInfo] = Field(description="Catalog versions newer than the newest installed one")
    upstream: list[UpstreamRelease]


class StorageInfo(ApiModel):
    name: str
    path: str
    source: str = Field(description="Where it lives on the host (set by scripts/run-server.sh)")
    free: int | None


class EnginesOverview(ApiModel):
    host: HostInfo
    engine: EngineStatus
    recommended: str | None = Field(description="The catalog package for this machine")
    packages: list[PackageInfo]
    installed: list[InstalledPackage]
    planned: list[Planned]
    install: model_setup.DownloadProgress
    storage: list[StorageInfo]


@dataclass(frozen=True)
class _Loaded:
    spec: PackageSpec
    root: str
    at: float


def _free(path: str) -> int | None:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def _upstream(package: str, component: str, repo: str, pinned: str, opener: Opener) -> UpstreamRelease:
    """The latest release of a GitHub repository (the API's /releases/latest, no token: 60 requests per hour)."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    base = UpstreamRelease(
        package=package, component=component, repo=repo, pinned=pinned, latest="", newer=False,
        url=f"https://github.com/{repo}/releases",
    )  # fmt: skip
    try:
        model_setup.check_url(url, ["github.com"])
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.github+json", "User-Agent": model_setup.USER_AGENT}
        )
        with opener.open(req, timeout=15) as resp:
            data = json.loads(resp.read(1 << 20))
        tag = str(data.get("tag_name", ""))
        return base.model_copy(
            update={
                "latest": tag,
                "newer": bool(tag) and tag != pinned,
                "url": str(data.get("html_url", base.url)),
                "published": str(data.get("published_at", "")),
            }
        )
    except (OSError, ValueError, SetupError) as e:
        return base.model_copy(update={"error": str(e)[:200]})


def _storage(name: str, path: str, host_env: str) -> StorageInfo:
    return StorageInfo(name=name, path=path, source=os.environ.get(host_env, ""), free=_free(path))


def _dir_size(path: str) -> int:
    total = 0
    for base, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(base, name)).st_size
            except OSError:
                pass
    return total


class Engines:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.progress = Progress()
        self._catalog: Catalog | None = None
        self._host: HostInfo | None = None
        self._active: _Loaded | None = None
        self._status = EngineStatus(state="none", problem="not loaded yet")

    # ------------------------------------------------------------ facts

    @property
    def root(self) -> str:
        return paths.engines

    def catalog(self) -> Catalog:
        with self.lock:
            if self._catalog is None:
                self._catalog = load_catalog()
            return self._catalog

    def host(self) -> HostInfo:
        with self.lock:
            if self._host is None:
                self._host = detect()
            return self._host

    def recommended(self) -> PackageSpec | None:
        host = self.host()
        return next((p for p in self.catalog().packages if not p.platform.mismatch(host)), None)

    def status(self) -> EngineStatus:
        with self.lock:
            return self._status.model_copy()

    @property
    def ready(self) -> bool:
        return self._active is not None

    def _dir(self, pid: str, version: str) -> str:
        return os.path.join(self.root, model_setup.safe_relpath(pid), model_setup.safe_relpath(version))

    def _read_installed(self, pid: str, version: str) -> tuple[PackageSpec, dict[str, float]] | None:
        try:
            with open(os.path.join(self._dir(pid, version), "package.json")) as f:
                raw = json.load(f)
            return PackageSpec.model_validate(raw["spec"]), {"size": raw["size"], "installed_at": raw["installed_at"]}
        except (OSError, ValueError, KeyError, SetupError):
            return None

    def installed(self) -> list[InstalledPackage]:
        out: list[InstalledPackage] = []
        if not os.path.isdir(self.root):
            return out
        cat, active = self.catalog(), self._active
        for pid in sorted(os.listdir(self.root)):
            if pid.startswith(".") or not os.path.isdir(os.path.join(self.root, pid)):
                continue
            for version in sorted(os.listdir(os.path.join(self.root, pid)), reverse=True):
                found = self._read_installed(pid, version)
                if found is None:
                    continue
                spec, meta = found
                listed = cat.find(pid, version)
                newest = cat.find(pid)
                out.append(
                    InstalledPackage(
                        id=pid,
                        version=version,
                        title=spec.title,
                        size=int(meta["size"]),
                        installed_at=meta["installed_at"],
                        active=active is not None and (active.spec.id, active.spec.version) == (pid, version),
                        in_catalog=listed is not None,
                        latest=newest is not None and newest.version == version,
                    )
                )
        return out

    def overview(self) -> EnginesOverview:
        installed = self.installed()
        rec = self.recommended()
        cat = self.catalog()
        return EnginesOverview(
            host=self.host(),
            engine=self.status(),
            recommended=rec.id if rec else None,
            packages=[
                self._info(p, installed) for pid in dict.fromkeys(p.id for p in cat.packages) for p in cat.versions(pid)
            ],
            installed=installed,
            planned=self.catalog().planned,
            install=self.progress.snapshot(),
            storage=[
                _storage("Models", paths.models, "HOST_MODELS"),
                _storage("Engines", paths.engines, "HOST_ENGINES"),
                _storage("Library", paths.library, "HOST_LIBRARY"),
                _storage("Server state", paths.data, "HOST_DATA"),
            ],
        )

    def _info(self, p: PackageSpec, installed: list[InstalledPackage]) -> PackageInfo:
        host, newest = self.host(), self.catalog().find(p.id)
        match = [i for i in installed if (i.id, i.version) == (p.id, p.version)]
        return PackageInfo(
            id=p.id,
            version=p.version,
            title=p.title,
            description=p.description,
            accelerator=p.platform.accelerator,
            download_size=p.download_size,
            compatible=not p.platform.mismatch(host),
            mismatch=p.platform.mismatch(host),
            installed=bool(match),
            loaded=bool(match) and match[0].active,
            latest=newest is not None and newest.version == p.version,
        )

    def check_updates(self, opener: Opener | None = None) -> UpdateReport:
        """Re-read the catalog; list catalog versions newer than what is installed, and ask GitHub whether the pinned
        components have newer upstream releases (information only)."""
        with self.lock:
            self._catalog = None
        cat, installed = self.catalog(), self.installed()
        newer: list[PackageInfo] = []
        for pid in dict.fromkeys(p.id for p in cat.packages):
            have = [version_key(i.version) for i in installed if i.id == pid]
            for p in cat.versions(pid):
                if (not have or version_key(p.version) > max(have)) and not p.platform.mismatch(self.host()):
                    newer.append(self._info(p, installed))
        upstream: list[UpstreamRelease] = []
        seen: set[str] = set()
        op = opener or model_setup._opener(cat.allowed_domains)
        for pid in dict.fromkeys(p.id for p in cat.packages):
            newest = cat.find(pid)
            for it in newest.items if newest else []:
                up = it.get("upstream")
                if up is None or up["github"] in seen:
                    continue
                seen.add(up["github"])
                upstream.append(_upstream(pid, it["id"], up["github"], up["tag"], op))
        return UpdateReport(checked_at=time.time(), packages=newer, upstream=upstream)

    # ------------------------------------------------------------ runners

    def missing(self, names: tuple[str, ...]) -> str:
        """Why these runners cannot start now, or ""."""
        with self.lock:
            a, problem = self._active, self._status.problem
        if not names:
            return ""
        if a is None:
            return f"no engine is loaded: {problem or 'install one on the Engines page'}"
        lacking = [n for n in names if n not in a.spec.runners]
        return f"the loaded engine {a.spec.id} {a.spec.version} has no {', '.join(lacking)}" if lacking else ""

    def runner(self, name: str) -> Runner:
        """The named CLI of the loaded package, ready to start. Raises EngineUnavailable."""
        with self.lock:
            a, problem = self._active, self._status.problem
        if a is None:
            raise EngineUnavailable(f"no engine is loaded: {problem or 'install one on the Engines page'}")
        spec = a.spec.runners.get(name)
        if spec is None:
            raise EngineUnavailable(f"the loaded engine {a.spec.id} {a.spec.version} has no {name}")
        lib_dirs = [os.path.join(a.root, d) for d in (*spec.lib_dirs, *a.spec.lib_dirs)]
        env = dict(os.environ, **a.spec.env, LD_LIBRARY_PATH=":".join(lib_dirs))
        return Runner(bin=os.path.join(a.root, spec.bin), env=env, package=f"{a.spec.id} {a.spec.version}")

    # ------------------------------------------------------------ load / reload

    def _block(self, spec: PackageSpec, problem: str) -> EngineStatus:
        self._active = None
        self._status = EngineStatus(
            state="blocked", id=spec.id, version=spec.version, title=spec.title, problem=problem
        )
        log(f"== engine {spec.id} {spec.version} not loaded: {problem}")
        return self._status.model_copy()

    def _self_test(self, spec: PackageSpec, root: str) -> str:
        for name, r in spec.runners.items():
            exe = os.path.join(root, r.bin)
            if not os.access(exe, os.X_OK):
                return f"{name}: {r.bin} is missing or not executable; reinstall the package"
            lib_dirs = [os.path.join(root, d) for d in (*r.lib_dirs, *spec.lib_dirs)]
            env = dict(os.environ, **spec.env, LD_LIBRARY_PATH=":".join(lib_dirs))
            try:
                p = subprocess.run(
                    [exe, *r.self_test], env=env, capture_output=True, text=True, errors="replace",
                    timeout=SELF_TEST_TIMEOUT, cwd=tempfile.gettempdir(),
                )  # fmt: skip
            except (OSError, subprocess.TimeoutExpired) as e:
                return f"{name} self-test failed: {e}"
            if p.returncode != 0:
                last = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
                return f"{name} self-test failed (rc={p.returncode}): {last[0][:300]}"
        return ""

    def load(self, pid: str, version: str) -> EngineStatus:
        """Check and activate an installed package; remembered for the next start when it loads."""
        with self.lock:
            found = self._read_installed(pid, version)
            if found is None:
                raise SetupError(f"{pid} {version} is not installed")
            spec = found[0]
            root = self._dir(pid, version)
            problem = (
                spec.platform.mismatch(self.host())
                or backends.preflight(spec.platform.accelerator)
                or self._self_test(spec, root)
            )
            if problem:
                return self._block(spec, problem)
            self._active = _Loaded(spec=spec, root=root, at=time.time())
            self._status = EngineStatus(
                state="ready", id=pid, version=version, title=spec.title,
                runners=sorted(spec.runners), loaded_at=self._active.at,
            )  # fmt: skip
            os.makedirs(self.root, exist_ok=True)
            tmp = os.path.join(self.root, "active.json.tmp")
            with open(tmp, "w") as f:
                json.dump({"id": pid, "version": version}, f)
            os.replace(tmp, os.path.join(self.root, "active.json"))
            log(f"== engine {pid} {version} loaded ({', '.join(sorted(spec.runners))})")
            return self._status.model_copy()

    def reload(self) -> EngineStatus:
        """Re-read the catalog, detect the machine again and load the remembered package (else the newest installed
        one that fits this machine)."""
        with self.lock:
            self._catalog, self._host = None, None
            self._active = None
            choice: tuple[str, str] | None = None
            try:
                with open(os.path.join(self.root, "active.json")) as f:
                    raw = json.load(f)
                choice = (str(raw["id"]), str(raw["version"]))
            except (OSError, ValueError, KeyError):
                pass
            installed = self.installed()
            if choice is None or not any((i.id, i.version) == choice for i in installed):
                host = self.host()
                fits = [
                    i
                    for i in installed
                    if (spec := self._read_installed(i.id, i.version)) and not spec[0].platform.mismatch(host)
                ]
                fits.sort(key=lambda i: i.installed_at, reverse=True)
                choice = (fits[0].id, fits[0].version) if fits else None
            if choice is None:
                rec = self.recommended()
                hint = (
                    f"install {rec.title} on the Engines page"
                    if rec
                    else f"no engine package for this machine yet ({self.host().accelerator}, {self.host().gpu})"
                )
                self._status = EngineStatus(state="none", problem=hint)
                return self._status.model_copy()
            return self.load(*choice)

    # ------------------------------------------------------------ install / remove

    def install(
        self, pid: str, version: str | None = None, progress: Progress | None = None, opener: Opener | None = None
    ) -> EngineStatus:
        """Download, verify and unpack a catalog package version (default: the newest) into its own directory, then
        load it."""
        p = progress or self.progress
        spec = self.catalog().find(pid, version)
        if spec is None:
            raise SetupError(f"unknown engine package {pid} {version or ''}".rstrip())
        mismatch = spec.platform.mismatch(self.host())
        if mismatch:
            raise SetupError(f"{spec.title} does not fit this machine: {mismatch}")
        dest = self._dir(spec.id, spec.version)
        if self._read_installed(spec.id, spec.version):
            return self.load(spec.id, spec.version)
        os.makedirs(self.root, exist_ok=True)
        need = spec.download_size * 4  # archive + unpacked, measured ~3.5x for the ROCm wheels
        free = shutil.disk_usage(self.root).free
        if need > free:
            raise SetupError(
                f"not enough disk space under {self.root}: need ~{need / 2**30:.1f} GiB, free {free / 2**30:.1f} GiB"
            )
        p.update(running=True, total_items=len(spec.items), done_items=0, error="", started=time.time(), finished=0.0)
        p.log(f"installing {spec.title} ({spec.id} {spec.version}), {spec.download_size / 2**30:.2f} GiB to download")
        staging = tempfile.mkdtemp(prefix=f".install-{spec.id}-", dir=self.root)
        cache = os.path.join(self.root, ".cache")
        try:
            for n, it in enumerate(spec.items):
                p.update(item=it["id"], item_done=0, item_size=int(it["size"]))
                p.log(f"[{n + 1}/{len(spec.items)}] {it['id']}")
                local = os.path.join(cache, os.path.basename(urllib.parse.urlsplit(it["url"]).path))

                def cb(done: int) -> None:
                    p.update(item_done=done)

                model_setup.fetch(
                    it["url"], int(it["size"]), it["sha256"], local, self.catalog().allowed_domains, cb, opener
                )
                model_setup.extract_archive(it, local, os.path.join(staging, model_setup.safe_relpath(it["dest"])))
                os.unlink(local)
                p.update(done_items=n + 1)
            for r in spec.runners.values():
                exe = os.path.join(staging, r.bin)
                if not os.path.isfile(exe):
                    raise SetupError(f"{spec.id}: {r.bin} is not in the package")
                os.chmod(exe, 0o755)  # noqa: S103  the pinned CLI must be executable
            with open(os.path.join(staging, "package.json"), "w") as f:
                json.dump(
                    {"spec": spec.model_dump(), "size": _dir_size(staging), "installed_at": time.time()}, f, indent=2
                )
            os.chmod(staging, 0o755)  # noqa: S103  mkdtemp makes it 0700
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            os.replace(staging, dest)
            p.log(f"installed into {dest}")
        except Exception as e:
            p.update(error=str(e))
            p.log(f"error: {e}")
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            p.update(running=False, finished=time.time())
        status = self.load(spec.id, spec.version)
        p.log(f"load: {status.state}{': ' + status.problem if status.problem else ''}")
        return status

    def remove(self, pid: str, version: str) -> None:
        """Delete an installed version. The loaded one is unloaded first (no GPU job can run until another is
        loaded), so this is refused while a job runs."""
        with self.lock:
            if gpu_lock.locked():
                raise EngineBusy("a job is running; remove the package when it has finished")
            if self._read_installed(pid, version) is None:
                raise SetupError(f"{pid} {version} is not installed")
            if self._active and (self._active.spec.id, self._active.spec.version) == (pid, version):
                self._active = None
                self._status = EngineStatus(
                    state="none", problem=f"{pid} {version} was removed; install or load another version"
                )
                try:
                    os.unlink(os.path.join(self.root, "active.json"))
                except FileNotFoundError:
                    pass
            shutil.rmtree(self._dir(pid, version))
            parent = os.path.join(self.root, pid)
            if not os.listdir(parent):
                os.rmdir(parent)
            log(f"== engine {pid} {version} removed")


engines = Engines()


def main(argv: list[str]) -> int:
    cmd, args = (argv[1] if len(argv) > 1 else "status"), argv[2:]
    try:
        if cmd == "status":
            st = engines.reload()
            o = engines.overview()
            print(f"host: {o.host.os} {o.host.arch}, {o.host.accelerator} ({o.host.gpu})")
            for i in o.installed:
                print(f"installed: {i.id} {i.version} {i.size / 2**30:.2f} GiB{' (loaded)' if i.active else ''}")
            print(f"engine: {st.state} {st.id} {st.version} {st.problem}".rstrip())
            return 0 if st.state == "ready" else 1
        if cmd == "install":
            rec = engines.recommended()
            pid = args[0] if args else (rec.id if rec else "")
            if not pid:
                print("no engine package for this machine", file=sys.stderr)
                return 1
            version = args[1] if len(args) > 1 else None
            st = engines.install(pid, version, Progress(echo=lambda line: print(line, flush=True)))
            print(f"engine: {st.state} {st.problem}".rstrip())
            return 0 if st.state == "ready" else 1
        if cmd == "load" and len(args) == 2:
            st = engines.load(args[0], args[1])
            print(f"engine: {st.state} {st.problem}".rstrip())
            return 0 if st.state == "ready" else 1
        if cmd == "updates":
            report = engines.check_updates()
            for pkg in report.packages:
                print(f"catalog: {pkg.id} {pkg.version} is newer than what is installed")
            for u in report.upstream:
                state = u.error or (f"newer upstream release {u.latest}" if u.newer else "up to date")
                print(f"upstream: {u.repo} pinned {u.pinned}: {state}")
            return 0
        if cmd == "remove" and len(args) == 2:
            engines.reload()
            engines.remove(args[0], args[1])
            return 0
    except (SetupError, EngineBusy) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
