"""Fetch, verify and install the weights under MODELS_DIR from the pinned catalog/models.json. The download,
verification and extraction helpers here are shared with the engine packages (app/engines/registry.py).

Safety rules (keep them when changing this file):
  * Only https URLs whose host, and the host of every redirect, is one of manifest["allowed_domains"] (or a
    subdomain of one). The API never takes URLs or paths from clients: only the pinned manifest is used.
  * Every download is hashed while it streams into "<dest>.part" and only renamed into place when size and SHA256
    match the manifest; a mismatch deletes the partial file. Interrupted downloads resume from the .part file.
  * Archives are extracted into a temporary directory first; members with absolute paths, "..", devices, or
    symlinks that leave their directory are rejected (tarfile's "data" filter; an equivalent check for zip).
  * Nothing is executed except the loaded engine's sd-cli (for the q8_0 conversion), with an argument list, no shell.
  * Enough free disk space is checked before anything is downloaded.

CLI (inside the server image, the models volume mounted at /models):
  python model_setup.py status            what is installed (fast: existence + size)
  python model_setup.py verify            full SHA256 check of the installed files
  python model_setup.py download          fetch and install whatever is missing
"""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from http.client import HTTPMessage
from typing import IO, Any, Literal, NotRequired, Protocol, TypedDict, cast

from pydantic import Field

from .schemas import ApiModel

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(os.path.dirname(HERE), "catalog", "models.json")  # reviewed file
MODELS = os.environ.get("MODELS_DIR", "/models")
CHUNK = 1 << 20
USER_AGENT = "local-producer-model-setup/1"


class SetupError(RuntimeError):
    pass


class Source(TypedDict):
    url: str
    size: int
    sha256: str


class Upstream(TypedDict):
    """Where newer releases of a pinned component appear (checked by the engines' update check, never installed
    from there: a new version is a reviewed catalog change)."""

    github: str  # owner/repo
    tag: str  # the pinned release tag


class ManifestItem(TypedDict):
    """One thing to install. file: url/size/sha256 of the file itself; archive: of the archive, plus format, check
    (a file that proves the install) and optional strip (zip prefix); convert: source (the bf16 file) and type."""

    id: str
    kind: Literal["file", "archive", "convert"]
    dest: str
    size: int
    url: NotRequired[str]
    sha256: NotRequired[str]
    format: NotRequired[Literal["tar.gz", "zip"]]
    strip: NotRequired[str]
    check: NotRequired[str]
    type: NotRequired[str]
    source: NotRequired[Source]
    upstream: NotRequired[Upstream]


class Manifest(TypedDict):
    version: int
    allowed_domains: list[str]
    items: list[ManifestItem]


ItemState = Literal["ok", "missing", "wrong-size"]
Log = Callable[[str], None]


class ItemStatus(ApiModel):
    id: str
    dest: str
    state: ItemState
    size: int


class ModelStatus(ApiModel):
    ready: bool
    items: list[ItemStatus]
    missing_bytes: int


class DownloadProgress(ApiModel):
    running: bool = False
    item: str = ""
    item_done: int = 0
    item_size: int = 0
    done_items: int = 0
    total_items: int = 0
    error: str = ""
    log: list[str] = Field(default_factory=list)
    started: float = 0.0
    finished: float = 0.0


class Opener(Protocol):
    """urllib's OpenerDirector, or a fake in the tests."""

    def open(self, fullurl: urllib.request.Request, /, *, timeout: float) -> Any: ...


def load_manifest(path: str = MANIFEST) -> Manifest:
    with open(path) as f:
        m = json.load(f)
    validate_manifest(m)
    return cast(Manifest, m)


def validate_manifest(m: Any) -> None:
    """Reject a manifest that could write outside models/ or fetch from unexpected places."""
    if m.get("version") != 1:
        raise SetupError("unsupported manifest version")
    validate_items(m["items"], m["allowed_domains"])


def validate_items(items: Any, domains: list[str]) -> None:
    """The rules every pinned download follows (models and engine packages alike)."""
    ids = set()
    for it in items:
        if it["id"] in ids:
            raise SetupError(f"duplicate id {it['id']}")
        ids.add(it["id"])
        if it["kind"] not in ("file", "archive", "convert"):
            raise SetupError(f"{it['id']}: unknown kind {it['kind']}")
        safe_relpath(it["dest"])
        sources: list[Any] = [it["source"]] if it["kind"] == "convert" else [it]
        for src in sources:
            check_url(src["url"], domains)
            if len(src["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in src["sha256"]):
                raise SetupError(f"{it['id']}: bad sha256")
            if int(src["size"]) <= 0:
                raise SetupError(f"{it['id']}: bad size")
        if it["kind"] == "archive" and it["format"] not in ("tar.gz", "zip"):
            raise SetupError(f"{it['id']}: unknown archive format")
        if it["kind"] == "convert" and it["type"] not in ("q8_0",):
            raise SetupError(f"{it['id']}: unsupported conversion type")


def safe_relpath(rel: str) -> str:
    """A relative path that stays inside its base directory."""
    norm = os.path.normpath(rel)
    if os.path.isabs(rel) or norm.startswith("..") or norm in (".", ""):
        raise SetupError(f"unsafe path {rel!r}")
    return norm


def check_url(url: str, domains: list[str]) -> None:
    u = urllib.parse.urlsplit(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not any(host == d or host.endswith("." + d) for d in domains):
        raise SetupError(f"URL not allowed: {u.scheme}://{host}")


def dest_path(it: ManifestItem) -> str:
    return os.path.join(MODELS, safe_relpath(it["dest"]))


# ---------------------------------------------------------------- status


def item_status(it: ManifestItem) -> ItemState:
    """'ok' (present, right size), 'missing' or 'wrong-size'. Archives: their check file exists."""
    path = dest_path(it)
    if it["kind"] == "archive":
        return "ok" if os.path.isfile(os.path.join(path, it["check"])) else "missing"
    if not os.path.isfile(path):
        return "missing"
    return "ok" if os.path.getsize(path) == int(it["size"]) else "wrong-size"


def status(m: Manifest | None = None) -> ModelStatus:
    m = m or load_manifest()
    items = [ItemStatus(id=it["id"], dest=it["dest"], state=item_status(it), size=int(it["size"])) for it in m["items"]]
    return ModelStatus(
        ready=all(i.state == "ok" for i in items),
        items=items,
        missing_bytes=sum(download_bytes(it) for it in m["items"] if item_status(it) != "ok"),
    )


def download_bytes(it: ManifestItem) -> int:
    return int(it["source"]["size"] if it["kind"] == "convert" else it["size"])


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


def verify(m: Manifest | None = None, log: Log = print) -> list[str]:
    """Full SHA256 of installed files (archives are checked at download time only). Returns the failing ids."""
    m = m or load_manifest()
    bad: list[str] = []
    for it in m["items"]:
        if it["kind"] == "archive":
            continue
        path = dest_path(it)
        if not os.path.isfile(path):
            bad.append(it["id"])
            log(f"missing  {it['dest']}")
            continue
        ok = sha256_file(path) == it["sha256"]
        log(f"{'ok      ' if ok else 'MISMATCH'} {it['dest']}")
        if not ok:
            bad.append(it["id"])
    return bad


# ---------------------------------------------------------------- download


class _AllowlistRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, domains: list[str]) -> None:
        self.domains = domains

    def redirect_request(
        self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage, newurl: str
    ) -> urllib.request.Request | None:
        check_url(newurl, self.domains)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener(domains: list[str]) -> Opener:
    return urllib.request.build_opener(_AllowlistRedirect(domains))


def fetch(
    url: str,
    size: int,
    sha256: str,
    out: str,
    domains: list[str],
    progress: Callable[[int], None] | None = None,
    opener: Opener | None = None,
) -> None:
    """Download url to out (via out + '.part', resuming), verify size and SHA256, then rename."""
    check_url(url, domains)
    part = out + ".part"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    h = hashlib.sha256()
    done = 0
    if os.path.exists(part):
        if os.path.getsize(part) > size:
            os.unlink(part)
        else:
            with open(part, "rb") as f:
                for b in iter(lambda: f.read(CHUNK), b""):
                    h.update(b)
                    done += len(b)
    if done < size:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if done:
            req.add_header("Range", f"bytes={done}-")
        with (opener or _opener(domains)).open(req, timeout=60) as resp:
            if done and resp.status != 206:  # server ignored the range: start over
                h, done = hashlib.sha256(), 0
                mode = "wb"
            else:
                mode = "ab" if done else "wb"
            with open(part, mode) as f:
                while True:
                    b = resp.read(CHUNK)
                    if not b:
                        break
                    f.write(b)
                    h.update(b)
                    done += len(b)
                    if done > size:
                        break
                    if progress:
                        progress(done)
    if done != size or h.hexdigest() != sha256:
        os.unlink(part)
        raise SetupError(
            f"verification failed for {url} (got {done} bytes, expected {size}; sha256 mismatch "
            f"or truncated download); the partial file was deleted, try again"
        )
    os.replace(part, out)


def _extract_tar(archive: str, into: str) -> None:
    with tarfile.open(archive, "r:gz") as t:
        t.extractall(into, filter="data")  # rejects absolute paths, '..', devices and escaping links


def _extract_zip(archive: str, into: str, strip: str = "") -> None:
    """Extract the members under `strip`; symlinks (Unix mode bits) become links to a sibling file only."""
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            name = info.filename
            if not name.startswith(strip) or name.endswith("/"):
                continue
            rel = safe_relpath(name[len(strip) :])
            target = os.path.join(into, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                link = z.read(info).decode()
                if "/" in link or link in ("", ".", ".."):
                    raise SetupError(f"zip symlink {name} -> {link} leaves its directory")
                os.symlink(link, target)
                continue
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            if mode & 0o111:
                os.chmod(target, 0o755)  # noqa: S103  executables and libraries from the verified archive


def _relink_text_symlinks(d: str) -> None:
    """Some release zips store .so symlinks as small regular files holding the target name: turn them into links."""
    for name in os.listdir(d):
        p = os.path.join(d, name)
        if ".so" in name and os.path.isfile(p) and not os.path.islink(p) and os.path.getsize(p) < 64:
            with open(p) as f:
                link = f.read().strip()
            if link and "/" not in link and os.path.exists(os.path.join(d, link)):
                os.unlink(p)
                os.symlink(link, p)


def extract_archive(it: ManifestItem, archive: str, into: str) -> None:
    """Unpack a verified archive item into the directory `into` (created if needed, merged with what is there)."""
    os.makedirs(into, exist_ok=True)
    if it["format"] == "tar.gz":
        _extract_tar(archive, into)
    else:
        _extract_zip(archive, into, it.get("strip", ""))
    _relink_text_symlinks(into)
    if "check" in it:
        if not os.path.isfile(os.path.join(into, it["check"])):
            raise SetupError(f"{it['id']}: {it['check']} not found in the archive")
        os.chmod(os.path.join(into, it["check"]), 0o755)  # noqa: S103  the pinned CLI must be executable


def _install_archive(it: ManifestItem, archive: str) -> None:
    dest = dest_path(it)
    tmp = tempfile.mkdtemp(prefix=".extract-", dir=MODELS)
    try:
        extract_archive(it, archive, tmp)
        os.chmod(tmp, 0o755)  # noqa: S103  mkdtemp makes it 0700; the directory holds the installed files
        if os.path.exists(dest):
            shutil.rmtree(dest)
        os.replace(tmp, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _convert(it: ManifestItem, src: str, log: Log) -> None:
    """q8_0 GGUF from the verified bf16 safetensors with the loaded engine's sd-cli."""
    from .engines.registry import engines  # the engine registry imports this module

    sd = engines.runner("sd-cli")
    out = dest_path(it)
    tmp_out = out + ".converting.gguf"
    cmd = [sd.bin, "-M", "convert", "-m", src, "--type", it["type"], "-o", tmp_out]
    r = subprocess.run(cmd, env=sd.env, capture_output=True, text=True, cwd=tempfile.gettempdir())
    if r.returncode != 0 or not os.path.isfile(tmp_out):
        raise SetupError(f"{it['id']}: conversion failed: {(r.stdout + r.stderr)[-500:]}")
    got = sha256_file(tmp_out)
    if got != it["sha256"]:  # reproducibility check, not a trust boundary: input and converter are both pinned
        log(f"warning: {it['dest']} differs from the reference conversion ({got[:12]}...), installing anyway")
    os.replace(tmp_out, out)


class Progress:
    """Shared, thread-safe progress of a download run (read by the server's status endpoint). echo: also print
    each log line (the CLI)."""

    def __init__(self, echo: Log | None = None) -> None:
        self.lock = threading.Lock()
        self.state = DownloadProgress()
        self.echo = echo

    def update(self, **changes: Any) -> None:
        with self.lock:
            self.state = self.state.model_validate(self.state.model_dump() | changes)

    def log(self, line: str) -> None:
        if self.echo:
            self.echo(line)
        with self.lock:
            self.state.log = [*self.state.log, f"{time.strftime('%H:%M:%S')} {line}"][-50:]

    def snapshot(self) -> DownloadProgress:
        with self.lock:
            return self.state.model_copy(deep=True)


def download(m: Manifest | None = None, progress: Progress | None = None, opener: Opener | None = None) -> None:
    """Install every missing item. Raises SetupError on the first failure (already installed items stay)."""
    m = m or load_manifest()
    p = progress or Progress()
    log = p.log
    todo = [it for it in m["items"] if item_status(it) != "ok"]
    # archives first, conversions last (they run sd-cli on downloaded files)
    todo.sort(key=lambda it: {"archive": 0, "file": 1, "convert": 2}[it["kind"]])
    need = sum(download_bytes(it) + (int(it["size"]) if it["kind"] == "convert" else 0) for it in todo)
    os.makedirs(MODELS, exist_ok=True)
    free = shutil.disk_usage(MODELS).free
    if need > free:
        raise SetupError(
            f"not enough disk space under {MODELS}: need {need / 2**30:.1f} GiB, free {free / 2**30:.1f} GiB"
        )
    p.update(running=True, total_items=len(todo), done_items=0, error="", started=time.time(), finished=0.0)
    log(f"{len(todo)} item(s) to install, {need / 2**30:.1f} GiB of downloads and conversions")
    try:
        for n, it in enumerate(todo):
            src: Source = it["source"] if it["kind"] == "convert" else _own_source(it)
            p.update(item=it["id"], item_done=0, item_size=int(src["size"]))
            log(f"[{n + 1}/{len(todo)}] {it['id']}")

            def cb(done: int) -> None:
                p.update(item_done=done)

            if it["kind"] == "file":
                fetch(src["url"], int(src["size"]), src["sha256"], dest_path(it), m["allowed_domains"], cb, opener)
            else:
                name = os.path.basename(urllib.parse.urlsplit(src["url"]).path)
                local = os.path.join(MODELS, ".cache", name)  # kept across retries so a download can resume
                fetch(src["url"], int(src["size"]), src["sha256"], local, m["allowed_domains"], cb, opener)
                if it["kind"] == "archive":
                    _install_archive(it, local)
                else:
                    log(f"converting to {it['type']} (CPU, a few seconds)")
                    _convert(it, local, log)
                os.unlink(local)
            p.update(done_items=n + 1)
        log("done: all models installed")
    except Exception as e:
        p.update(error=str(e))
        log(f"error: {e}")
        raise
    finally:
        p.update(running=False, finished=time.time())


def _own_source(it: ManifestItem) -> Source:
    return Source(url=it["url"], size=it["size"], sha256=it["sha256"])


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    m = load_manifest()
    if cmd == "status":
        s = status(m)
        for i in s.items:
            print(f"{i.state:<10} {i.dest}")
        print(f"ready: {s.ready}, to download: {s.missing_bytes / 2**30:.1f} GiB")
        return 0 if s.ready else 1
    if cmd == "verify":
        return 1 if verify(m) else 0
    if cmd == "download":
        p = Progress(echo=lambda line: print(line, flush=True))
        stop = threading.Event()

        def show() -> None:
            last = ""
            while not stop.wait(5):
                s = p.snapshot()
                line = f"{s.item}: {s.item_done / 2**20:.0f}/{s.item_size / 2**20:.0f} MiB"
                if line != last:
                    print(line, flush=True)
                    last = line

        threading.Thread(target=show, daemon=True).start()
        try:
            download(m, p)
        except SetupError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        finally:
            stop.set()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
