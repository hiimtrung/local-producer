"""Uploaded inputs and job results on disk. Clients refer to files only by opaque ids, never by path.

<data>/uploads/<id>.<ext>          an uploaded image (type checked by magic bytes)
<data>/jobs/<id>/job.json          a job's record (see jobs.py)
<data>/jobs/<id>/<output files>    its results (names chosen by the pipeline, listed in job.json)
"""

import os
import re
import shutil
import uuid
from typing import Literal

from fastapi import HTTPException

from .schemas import ID_PATTERN, ImageRef, UploadInfo
from .settings import MAX_IMAGE_BYTES, config, paths

ImageKind = Literal["png", "jpg", "webp"]

ID_RE = re.compile(ID_PATTERN)
NAME_RE = re.compile(r"^[a-z0-9_]{1,40}\.(png|jpg|webp|glb)$")
IMAGE_TYPES: dict[str, str] = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
MEDIA_TYPES: dict[str, str] = {**IMAGE_TYPES, "glb": "model/gltf-binary"}


def new_id() -> str:
    return uuid.uuid4().hex


def check_id(value: str, what: str = "id") -> str:
    if not ID_RE.match(value):
        raise HTTPException(400, f"invalid {what}")
    return value


def image_type(data: bytes) -> ImageKind | None:
    """The image type from the magic bytes, else None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return None


def check_image(data: bytes, png_only: bool = False) -> ImageKind:
    if not data:
        raise HTTPException(400, "the image is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, f"the image is larger than {MAX_IMAGE_BYTES // 2**20} MiB")
    kind = image_type(data)
    if kind is None or (png_only and kind != "png"):
        raise HTTPException(400, "the image must be PNG" + ("" if png_only else ", JPEG or WebP"))
    return kind


# ---------------------------------------------------------------- uploads


def save_upload(data: bytes, name: str = "") -> UploadInfo:
    kind = check_image(data)
    os.makedirs(paths.uploads, exist_ok=True)
    uid = new_id()
    with open(os.path.join(paths.uploads, f"{uid}.{kind}"), "wb") as f:
        f.write(data)
    meta = UploadInfo(id=uid, type=IMAGE_TYPES[kind], size=len(data), name=os.path.basename(name)[:120])
    with open(os.path.join(paths.uploads, f"{uid}.json"), "w") as f:
        f.write(meta.model_dump_json())
    prune(paths.uploads, config.get().keep_uploads, files=True)
    return meta


def upload_path(uid: str) -> str:
    check_id(uid, "upload id")
    for ext in IMAGE_TYPES:
        p = os.path.join(paths.uploads, f"{uid}.{ext}")
        if os.path.isfile(p):
            return p
    raise HTTPException(404, "upload not found")


# ---------------------------------------------------------------- job results


def job_dir(jid: str) -> str:
    return os.path.join(paths.jobs, check_id(jid, "job id"))


def job_file(jid: str, name: str) -> str:
    if not NAME_RE.match(name):
        raise HTTPException(400, "invalid file name")
    p = os.path.join(job_dir(jid), name)
    if not os.path.isfile(p):
        raise HTTPException(404, "file not found")
    return p


def resolve_image(ref: ImageRef, png_only: bool = False) -> str:
    """Local path of an image reference; checks that it exists and its type."""
    if ref.upload:
        p = upload_path(ref.upload)
    elif ref.job:
        p = job_file(ref.job, ref.file)
    else:  # ImageRef's validator makes this unreachable
        raise HTTPException(400, "image must be {'upload': id} or {'job': id, 'file': name}")
    with open(p, "rb") as f:
        head = f.read(16)
    kind = image_type(head)
    if kind is None or (png_only and kind != "png"):
        raise HTTPException(400, "the referenced image must be PNG" + ("" if png_only else ", JPEG or WebP"))
    return p


def prune(directory: str, keep: int, files: bool = False) -> None:
    """Keep the newest `keep` entries (uploads: id groups of files; jobs: directories)."""
    if not os.path.isdir(directory):
        return
    if files:
        groups: dict[str, list[str]] = {}
        for name in os.listdir(directory):
            groups.setdefault(name.split(".")[0], []).append(os.path.join(directory, name))
        entries = sorted(groups.values(), key=lambda g: max(os.path.getmtime(p) for p in g), reverse=True)
        for group in entries[keep:]:
            for p in group:
                os.unlink(p)
    else:
        dirs = [os.path.join(directory, d) for d in os.listdir(directory) if ID_RE.match(d)]
        for d in sorted(dirs, key=os.path.getmtime, reverse=True)[keep:]:
            shutil.rmtree(d, ignore_errors=True)
