"""The Blender add-on, packed on request from the add-on sources shipped with the server, and published as a Blender
extension repository so it installs by dragging a link into Blender (Blender 4.2+, like extensions.blender.org).

GET /v1/addon                       name, version, download URL and repository URL for the web page
GET /blender/index.json             the extension repository listing (format v1, as `blender --command extension
                                    server-generate` writes it); add it once in Blender, then drops install directly
GET /blender/local_producer-<v>.zip  the package (blender_manifest.toml + the add-on)

Dragging "<zip URL>?repository=<index URL>&blender_version_min=..." into Blender asks to add the repository the first
time (Blender's own trust prompt), then installs. These paths sit outside /v1 like the static UI: the add-on source is
not a secret and Blender's repository sync does not send the web UI's token.
"""

import hashlib
import io
import os
import threading
import tomllib
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import JsonValue

from ..schemas import ApiModel
from ..settings import paths

router = APIRouter()
REPO_PATH = "/blender/index.json"
SKIP_SUFFIXES = (".pyc", "_raw.png")


class AddonInfo(ApiModel):
    id: str
    name: str
    version: str
    blender_version_min: str
    download: str  # absolute path on this server
    repository: str  # absolute path of index.json on this server


def manifest() -> dict[str, JsonValue]:
    """blender_manifest.toml of the shipped add-on."""
    try:
        with open(os.path.join(paths.addon, "blender_manifest.toml"), "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise HTTPException(404, "the add-on sources are not shipped with this server") from None


def _files() -> list[tuple[str, str]]:
    """(path on disk, name in the zip) of every packaged file, sorted, so the archive is reproducible."""
    root = paths.addon
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x != "__pycache__")
        for name in sorted(files):
            if not name.endswith(SKIP_SUFFIXES):
                full = os.path.join(d, name)
                out.append((full, "local_producer/" + os.path.relpath(full, root).replace(os.sep, "/")))
    return out


_cache_lock = threading.Lock()
_cache: tuple[tuple[tuple[str, float, int], ...], bytes] | None = None


def build_zip() -> bytes:
    """The package with fixed timestamps, rebuilt only when a source file changes: Blender checks archive_hash."""
    global _cache
    files = _files()
    key = tuple((name, os.path.getmtime(full), os.path.getsize(full)) for full, name in files)
    with _cache_lock:
        if _cache and _cache[0] == key:
            return _cache[1]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for full, name in files:
                info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(full, "rb") as f:
                    z.writestr(info, f.read())
        _cache = (key, buf.getvalue())
        return _cache[1]


def zip_name(m: dict[str, JsonValue]) -> str:
    return f"{m['id']}-{m['version']}.zip"


@router.get("/v1/addon")
def addon_info() -> AddonInfo:
    m = manifest()
    return AddonInfo(
        id=str(m["id"]),
        name=str(m["name"]),
        version=str(m["version"]),
        blender_version_min=str(m["blender_version_min"]),
        download=f"/blender/{zip_name(m)}",
        repository=REPO_PATH,
    )


@router.get(REPO_PATH)
def extension_index() -> dict[str, JsonValue]:
    m = manifest()
    data = build_zip()
    entry: dict[str, JsonValue] = {k: v for k, v in m.items() if k != "build"}
    entry |= {
        "archive_url": f"./{zip_name(m)}",
        "archive_size": len(data),
        "archive_hash": "sha256:" + hashlib.sha256(data).hexdigest(),
    }
    return {"version": "v1", "blocklist": [], "data": [entry]}


@router.get("/blender/{name}", response_class=Response, responses={200: {"content": {"application/zip": {}}}})
def addon_zip(name: str) -> Response:
    m = manifest()
    if name != zip_name(m):
        raise HTTPException(404, f"no such package; the current one is {zip_name(m)}")
    return Response(
        build_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-cache"},
    )
