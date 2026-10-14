"""The models the pipelines can use: the built-in ones (catalog/models.json, pinned) and ones a user adds from
Hugging Face, another public https link, or an upload; each can be tested with the loaded engine.

<models>/user/<id>/model.json   a user model: family, title, source, files, SHA256 per file
<models>/user/<id>/<files>      its weights (one diffusion model file, or a TRELLIS.2 set)
<data>/model-checks.json        the last test of every model: which engine, when, how long, the error if any

A family is a kind of model a pipeline knows how to run with an engine runner: "flux2-klein" (sd-cli: a diffusion
model; the built-in text encoder and VAE go with it) and "trellis2" (trellis-cli: a folder of TRELLIS.2 GGUF files).

Safety rules for user models (SECURITY.md):
  * Weights only: .gguf and .safetensors, checked by their header after the download. No pickle formats
    (.ckpt, .pt, .bin), nothing is ever imported or executed; the files are only read by the engine's CLI.
  * Downloads are https only, and every host (also after redirects) must resolve to public addresses only, so the
    server cannot be used to reach the machine itself or the local network. Hugging Face files are pinned to the
    commit the revision pointed at and verified against the size and SHA256 Hugging Face publishes; other links
    are hashed while they download and the hash is recorded.
  * Size cap per model and a free-space check; downloads go to a staging directory first.
"""

import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import threading
import time
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Iterator
from http.client import HTTPMessage
from typing import IO, Any, Literal

from fastapi import HTTPException
from pydantic import Field

from . import model_setup
from .model_setup import Opener, Progress, SetupError
from .schemas import ApiModel
from .settings import paths

MODEL_ID = r"^[a-z0-9][a-z0-9._-]{0,79}$"
MAX_MODEL_BYTES = 64 * 2**30
WEIGHT_SUFFIXES = (".gguf", ".safetensors")
HF_HOSTS = ["huggingface.co", "hf.co"]
TRELLIS_FILES = (
    "birefnet.gguf", "dinov3.gguf", "ss_flow.gguf", "ss_dec.gguf", "shape_flow_512.gguf", "shape_dec.gguf",
    "tex_flow_512.gguf", "tex_dec.gguf",
)  # fmt: skip
TRELLIS_OPTIONAL = ("shape_flow_1024.gguf", "tex_flow_1024.gguf")  # needed for res 1024 and 1536 only
CHUNK = 1 << 20


class Family(ApiModel):
    id: str
    title: str
    task: Literal["image", "mesh"]
    runner: str
    adds: Literal["file", "folder"] = Field(description="What a user adds: one weights file, or a Hugging Face folder")
    description: str


FAMILIES: dict[str, Family] = {
    f.id: f
    for f in (
        Family(
            id="flux2-klein",
            title="FLUX.2-klein image model",
            task="image",
            runner="sd-cli",
            adds="file",
            description="A FLUX.2-klein diffusion model, .gguf or .safetensors (e.g. another quantisation such as "
            "Q4_0). It runs with the built-in Qwen3-4B text encoder and VAE.",
        ),
        Family(
            id="trellis2",
            title="TRELLIS.2 3D model set",
            task="mesh",
            runner="trellis-cli",
            adds="folder",
            description="A Hugging Face folder with the TRELLIS.2 GGUF files (birefnet, dinov3, ss_flow, ss_dec, "
            "shape_flow_512, shape_dec, tex_flow_512, tex_dec; the _1024 flows for res 1024+).",
        ),
    )
}


class ModelCheck(ApiModel):
    state: Literal["ok", "failed"]
    engine: str = Field(description="The engine package and version it was tested with")
    at: float
    seconds: float | None = None
    message: str = ""
    job: str = ""


class ModelInfo(ApiModel):
    id: str
    family: str
    title: str
    builtin: bool
    source: str
    size: int
    present: bool = Field(True, description="All its files are on disk")
    added_at: float | None = None
    files: dict[str, str] = Field(description="Role -> path relative to the models directory")
    check: ModelCheck | None = None


class Suggestion(ApiModel):
    family: str
    title: str
    url: str
    size: int
    note: str
    added: bool = Field(False, description="A model from this link is already on the server")


class ModelsOverview(ApiModel):
    families: list[Family]
    models: list[ModelInfo]
    suggestions: list[Suggestion]
    adding: model_setup.DownloadProgress


class AddModel(ApiModel):
    family: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    title: str = Field(min_length=1, max_length=80)
    url: str = Field(
        min_length=8,
        max_length=2000,
        description="https link to a weights file; for Hugging Face also a folder (…/tree/<revision>/<folder>)",
    )


# ---------------------------------------------------------------- safe downloads


def check_public_url(url: str) -> None:
    """https, and the host resolves to public addresses only (no loopback, private, link-local or reserved)."""
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or not u.hostname:
        raise SetupError("only https links are accepted")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise SetupError(f"can't resolve {u.hostname}: {e}") from None
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if not addr.is_global:
            raise SetupError(f"{u.hostname} resolves to a non-public address ({addr})")


class _PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage, newurl: str
    ) -> urllib.request.Request | None:
        check_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def public_opener() -> Opener:
    return urllib.request.build_opener(_PublicRedirect())


def _get_json(url: str, opener: Opener) -> Any:
    check_public_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": model_setup.USER_AGENT})
    with opener.open(req, timeout=30) as resp:
        return json.loads(resp.read(8 << 20))


def check_weights(path: str) -> None:
    """The file is GGUF or safetensors by its header (not just its name)."""
    with open(path, "rb") as f:
        head = f.read(16)
    if path.endswith(".gguf") and head[:4] == b"GGUF":
        return
    if path.endswith(".safetensors") and len(head) >= 9:
        header_len = int.from_bytes(head[:8], "little")
        if 2 <= header_len < 100 * 2**20 and head[8:9] == b"{":
            return
    raise SetupError(f"{os.path.basename(path)} is not a valid {os.path.splitext(path)[1]} file")


def fetch_unpinned(url: str, out: str, progress: Callable[[int], None], opener: Opener) -> str:
    """Download a public https link to out (via .part, capped); returns its SHA256."""
    check_public_url(url)
    part = out + ".part"
    h, done = hashlib.sha256(), 0
    req = urllib.request.Request(url, headers={"User-Agent": model_setup.USER_AGENT})
    with opener.open(req, timeout=60) as resp, open(part, "wb") as f:
        length = resp.headers.get("Content-Length") if hasattr(resp, "headers") else None
        if length and length.isdigit() and int(length) > MAX_MODEL_BYTES:
            raise SetupError(f"the file is larger than {MAX_MODEL_BYTES / 2**30:.0f} GiB")
        while b := resp.read(CHUNK):
            f.write(b)
            h.update(b)
            done += len(b)
            if done > MAX_MODEL_BYTES:
                raise SetupError(f"the file is larger than {MAX_MODEL_BYTES / 2**30:.0f} GiB")
            progress(done)
    os.replace(part, out)
    return h.hexdigest()


# ---------------------------------------------------------------- Hugging Face

HF_RE = re.compile(r"^https://(?:huggingface\.co|hf\.co)/([\w.-]+/[\w.-]+)/(resolve|blob|tree)/([^/]+)(?:/(.*))?$")


class HfFile(ApiModel):
    path: str
    size: int
    sha256: str


def hf_files(url: str, opener: Opener) -> tuple[str, str, str, list[HfFile]]:
    """(repo, commit, path, files) for a Hugging Face file or folder URL, pinned to the commit the revision points
    at, with the size and SHA256 Hugging Face publishes for each file."""
    m = HF_RE.match(url.split("?")[0])
    if not m:
        raise SetupError("not a Hugging Face file or folder link (https://huggingface.co/<owner>/<repo>/...)")
    repo, kind, rev, path = m.group(1), m.group(2), urllib.parse.unquote(m.group(3)), (m.group(4) or "").strip("/")
    q = urllib.parse.quote
    commit = str(_get_json(f"https://huggingface.co/api/models/{repo}/revision/{q(rev, safe='')}", opener)["sha"])
    folder = path if kind == "tree" else os.path.dirname(path)
    entries = _get_json(f"https://huggingface.co/api/models/{repo}/tree/{commit}/{q(folder)}".rstrip("/"), opener)
    files = [
        HfFile(path=e["path"], size=int(e["size"]), sha256=str(e["lfs"]["oid"]))
        for e in entries
        if e.get("type") == "file" and e.get("lfs") and str(e["path"]).endswith(WEIGHT_SUFFIXES)
    ]
    if kind != "tree":
        files = [f for f in files if f.path == path]
        if not files:
            raise SetupError(f"{path} is not a .gguf / .safetensors file stored in {repo}")
    return repo, commit, path, files


def hf_url(repo: str, commit: str, path: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/{commit}/{urllib.parse.quote(path)}"


# ---------------------------------------------------------------- the store


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or "model"
    return f"{s}-{uuid.uuid4().hex[:6]}"


class ModelStore:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.progress = Progress()

    @property
    def user_dir(self) -> str:
        return os.path.join(paths.models, "user")

    @property
    def checks_file(self) -> str:
        return os.path.join(paths.data, "model-checks.json")

    # ------------------------------------------------------------ listing

    def _checks(self) -> dict[str, ModelCheck]:
        try:
            with open(self.checks_file) as f:
                return {k: ModelCheck.model_validate(v) for k, v in json.load(f).items()}
        except (OSError, ValueError):
            return {}

    def record_check(self, model_id: str, check: ModelCheck) -> None:
        with self.lock:
            checks = self._checks()
            checks[model_id] = check
            os.makedirs(paths.data, exist_ok=True)
            tmp = self.checks_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump({k: v.model_dump() for k, v in checks.items()}, f, indent=2)
            os.replace(tmp, self.checks_file)

    def _builtins(self) -> Iterator[ModelInfo]:
        with open(model_setup.MANIFEST) as f:
            raw = json.load(f)
        sizes = {it["dest"]: int(it["size"]) for it in raw["items"]}
        for m in raw.get("models", []):
            files: dict[str, str] = m["files"]
            rels = [r for r in files.values()]
            members = [d for d in sizes if any(d == r or d.startswith(r.rstrip("/") + "/") for r in rels)]
            yield ModelInfo(
                id=m["id"],
                family=m["family"],
                title=m["title"],
                builtin=True,
                source="Built in (server/catalog/models.json)",
                size=sum(sizes[d] for d in members),
                present=all(os.path.exists(os.path.join(paths.models, d)) for d in members),
                files=files,
            )

    def _user(self) -> Iterator[ModelInfo]:
        if not os.path.isdir(self.user_dir):
            return
        for mid in sorted(os.listdir(self.user_dir)):
            try:
                with open(os.path.join(self.user_dir, mid, "model.json")) as f:
                    info = ModelInfo.model_validate(json.load(f))
            except (OSError, ValueError):
                continue
            if info.id != mid or info.builtin:
                continue
            info.present = all(os.path.exists(os.path.join(paths.models, r)) for r in info.files.values())
            yield info

    def all(self) -> list[ModelInfo]:
        checks = self._checks()
        out = [*self._builtins(), *self._user()]
        for m in out:
            m.check = checks.get(m.id)
        return out

    def get(self, model_id: str) -> ModelInfo | None:
        return next((m for m in self.all() if m.id == model_id), None)

    def suggestions(self, models: list[ModelInfo]) -> list[Suggestion]:
        """catalog/models.json "suggestions", marked when a model from the same Hugging Face file / folder exists."""
        with open(model_setup.MANIFEST) as f:
            raw = json.load(f).get("suggestions", [])
        out = []
        for s in raw:
            sug = Suggestion.model_validate(s)
            m = HF_RE.match(sug.url)
            if m:
                repo, path = m.group(1), (m.group(4) or "").strip("/")
                sug.added = any(x.source.startswith(f"Hugging Face {repo}@") and x.source.endswith(f"/{path}")
                                for x in models)  # fmt: skip
            out.append(sug)
        return out

    def overview(self) -> ModelsOverview:
        models = self.all()
        return ModelsOverview(
            families=list(FAMILIES.values()),
            models=models,
            suggestions=self.suggestions(models),
            adding=self.progress.snapshot(),
        )

    def clear_adding(self) -> None:
        """Forget the last add's error and log (the page's Dismiss)."""
        if not self.progress.snapshot().running:
            self.progress.update(error="", log=[], item="", item_done=0, item_size=0)

    def require(self, family: str, model_id: str | None) -> ModelInfo:
        """The model a job asked for (None = the built-in one of that family), usable now. Raises HTTPException."""
        models = [m for m in self.all() if m.family == family]
        m = (
            next((x for x in models if x.id == model_id), None)
            if model_id
            else next((x for x in models if x.builtin), None)
        )
        if m is None:
            raise HTTPException(400, f"no {FAMILIES[family].title} with id {model_id!r} (Server > Models)")
        if not m.present:
            raise HTTPException(503, f"{m.title}: files are missing; download them on the Models page")
        if m.check is not None and m.check.state == "failed":
            raise HTTPException(409, f"{m.title} failed its test with {m.check.engine}; test it again or pick another")
        return m

    def path(self, m: ModelInfo, role: str) -> str:
        """Absolute path of a model file; a user diffusion model borrows the built-in text encoder and VAE."""
        rel = m.files.get(role)
        if rel is None:
            base = next(x for x in self._builtins() if x.family == m.family)
            rel = base.files[role]
        return os.path.join(paths.models, model_setup.safe_relpath(rel))

    # ------------------------------------------------------------ adding

    def _stage(self, family: str, title: str) -> tuple[str, str]:
        mid = _slug(title)
        os.makedirs(self.user_dir, exist_ok=True)
        staging = os.path.join(self.user_dir, f".adding-{mid}")
        os.makedirs(staging)
        return mid, staging

    def _finish(self, mid: str, staging: str, info: ModelInfo) -> ModelInfo:
        with open(os.path.join(staging, "model.json"), "w") as f:
            f.write(info.model_dump_json(indent=2, exclude={"check", "present"}))
        os.replace(staging, os.path.join(self.user_dir, mid))
        self.progress.log(f"added {info.title} as {mid}")
        return info

    def add_from_url(self, req: AddModel, opener: Opener | None = None) -> ModelInfo:
        """Download a model (blocking; the route runs it in a thread). Raises SetupError."""
        fam = FAMILIES.get(req.family)
        if fam is None:
            raise SetupError(f"unknown model family {req.family}")
        op = opener or public_opener()
        p = self.progress
        p.update(running=True, error="", item=req.title, item_done=0, item_size=0, done_items=0, total_items=1,
                 started=time.time(), finished=0.0)  # fmt: skip
        staging = ""
        try:
            hf = HF_RE.match(req.url.split("?")[0])
            if hf:
                repo, commit, path, found = hf_files(req.url, op)
                plan = self._plan(fam, found)
                source = f"Hugging Face {repo}@{commit[:12]}/{path}"
            else:
                if fam.adds != "file":
                    raise SetupError(f"a {fam.title} is added from a Hugging Face folder link")
                name = os.path.basename(urllib.parse.urlsplit(req.url).path)
                if not name.endswith(WEIGHT_SUFFIXES):
                    raise SetupError("the link must end in .gguf or .safetensors")
                check_public_url(req.url)
                repo = commit = ""
                plan = [HfFile(path=name, size=0, sha256="")]
                source = req.url
            need = sum(f.size for f in plan)
            os.makedirs(paths.models, exist_ok=True)
            if need > shutil.disk_usage(paths.models).free - 2**30:
                raise SetupError(f"not enough free disk space for {need / 2**30:.1f} GiB")
            mid, staging = self._stage(fam.id, req.title)
            p.update(total_items=len(plan))
            files: dict[str, str] = {}
            hashes: dict[str, str] = {}
            for n, f in enumerate(plan):
                base = os.path.basename(f.path)
                out = os.path.join(staging, base)
                p.update(item=base, item_done=0, item_size=f.size)
                p.log(f"[{n + 1}/{len(plan)}] {base}")

                def cb(done: int) -> None:
                    p.update(item_done=done)

                if f.sha256:
                    model_setup.fetch(hf_url(repo, commit, f.path), f.size, f.sha256, out, HF_HOSTS, cb, op)
                    hashes[base] = f.sha256
                else:
                    hashes[base] = fetch_unpinned(req.url, out, cb, op)
                check_weights(out)
                files["diffusion" if fam.adds == "file" else base] = f"user/{mid}/{base}"
                p.update(done_items=n + 1)
            if fam.adds == "folder":
                files = {"dir": f"user/{mid}"}
            info = ModelInfo(
                id=mid, family=fam.id, title=req.title, builtin=False, source=source,
                size=sum(os.path.getsize(os.path.join(staging, b)) for b in hashes), present=True,
                added_at=time.time(), files=files,
            )  # fmt: skip
            info = self._finish(mid, staging, info)
            with open(os.path.join(self.user_dir, mid, "sha256.json"), "w") as fh:
                json.dump(hashes, fh, indent=2)
            return info
        except Exception as e:
            p.update(error=str(e))
            p.log(f"error: {e}")
            raise
        finally:
            if staging:
                shutil.rmtree(staging, ignore_errors=True)
            p.update(running=False, finished=time.time())

    @staticmethod
    def _plan(fam: Family, found: list[HfFile]) -> list[HfFile]:
        if fam.adds == "file":
            if len(found) != 1:
                raise SetupError("link one weights file (…/blob/<revision>/<file>.gguf), not a folder")
            return found
        names = {os.path.basename(f.path): f for f in found}
        missing = [n for n in TRELLIS_FILES if n not in names]
        if missing:
            raise SetupError(f"the folder lacks {', '.join(missing)}")
        return [names[n] for n in (*TRELLIS_FILES, *TRELLIS_OPTIONAL) if n in names]

    def begin_upload(self, family: str, title: str, filename: str) -> "UploadSink":
        """Start storing an uploaded weights file; the caller writes chunks, then finish() or abort()."""
        fam = FAMILIES.get(family)
        if fam is None or fam.adds != "file":
            raise SetupError("uploads are for single-file model families (FLUX.2-klein)")
        name = os.path.basename(filename)
        if not re.fullmatch(r"[\w.-]{1,120}", name) or not name.endswith(WEIGHT_SUFFIXES):
            raise SetupError("the file must be a .gguf or .safetensors file")
        if not 1 <= len(title) <= 80:
            raise SetupError("give the model a title (1-80 characters)")
        mid, staging = self._stage(family, title)
        return UploadSink(self, mid, staging, family, title, name)

    def add_upload(self, family: str, title: str, filename: str, chunks: Iterator[bytes]) -> ModelInfo:
        sink = self.begin_upload(family, title, filename)
        try:
            for b in chunks:
                sink.write(b)
            return sink.finish()
        finally:
            sink.abort()

    def remove(self, model_id: str) -> None:
        m = self.get(model_id)
        if m is None:
            raise SetupError("unknown model")
        if m.builtin:
            raise SetupError("built-in models are managed by the server; remove a model you added")
        shutil.rmtree(os.path.join(self.user_dir, model_setup.safe_relpath(model_id)))
        with self.lock:
            checks = self._checks()
            if checks.pop(model_id, None) is not None:
                with open(self.checks_file, "w") as f:
                    json.dump({k: v.model_dump() for k, v in checks.items()}, f, indent=2)


class UploadSink:
    """One upload in progress: hashed and capped while it is written into the staging directory."""

    def __init__(self, owner: ModelStore, mid: str, staging: str, family: str, title: str, name: str) -> None:
        self.owner, self.mid, self.staging, self.family, self.title, self.name = (
            owner,
            mid,
            staging,
            family,
            title,
            name,
        )
        self.path = os.path.join(staging, name)
        self.file: IO[bytes] | None = open(self.path, "wb")  # noqa: SIM115  closed in finish() / abort()
        self.hash, self.size = hashlib.sha256(), 0

    def write(self, b: bytes) -> None:
        self.size += len(b)
        if self.size > MAX_MODEL_BYTES:
            raise SetupError(f"the file is larger than {MAX_MODEL_BYTES / 2**30:.0f} GiB")
        if self.file is None:
            raise SetupError("the upload was already closed")
        self.file.write(b)
        self.hash.update(b)

    def finish(self) -> ModelInfo:
        if self.file is None:
            raise SetupError("the upload was already closed")
        self.file.close()
        self.file = None
        check_weights(self.path)
        info = ModelInfo(
            id=self.mid, family=self.family, title=self.title, builtin=False, source=f"Upload {self.name}",
            size=self.size, present=True, added_at=time.time(), files={"diffusion": f"user/{self.mid}/{self.name}"},
        )  # fmt: skip
        info = self.owner._finish(self.mid, self.staging, info)
        with open(os.path.join(self.owner.user_dir, self.mid, "sha256.json"), "w") as fh:
            json.dump({self.name: self.hash.hexdigest()}, fh, indent=2)
        return info

    def abort(self) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None
        shutil.rmtree(self.staging, ignore_errors=True)


store = ModelStore()
