"""Synchronous endpoints in AMD Lemonade's request format, used by the Blender add-on. Each one queues a job like the
web UI does and waits for it, so the add-on and the web share one queue and one GPU.

POST /v1/images/generations  JSON {prompt, size "WxH", steps, cfg_scale, seed}           -> {"data": [{"b64_json"}]}
POST /v1/images/edits        multipart {image, prompt, size, steps, cfg_scale, seed}      -> {"data": [{"b64_json"}]}
POST /v1/3d/generations      JSON {image (base64 PNG), seed, resolution, bg_removal, steps} -> GLB bytes
"""

import base64
import binascii
import time
from typing import Literal

import anyio
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .. import storage
from ..jobs import manager
from ..schemas import ApiModel, Job
from ..settings import MAX_BODY_BYTES, MAX_IMAGE_BYTES, MAX_PROMPT_CHARS
from .jobs import submit_raw

router = APIRouter()


class ImageData(ApiModel):
    b64_json: str


class ImagesResponse(ApiModel):
    created: int
    data: list[ImageData]


def _size(size: str) -> tuple[int, int]:
    try:
        w, h = (int(x) for x in size.lower().split("x"))
    except ValueError:
        raise HTTPException(400, "size must look like 1024x1024") from None
    return w, h


async def _finish(job: Job) -> Job:
    done = await anyio.to_thread.run_sync(lambda: manager.wait(job.id))
    if done.state != "done":
        raise HTTPException(500, f"{done.kind} {done.state}: {done.error}")
    return done


def _image_response(job: Job) -> ImagesResponse:
    with open(storage.job_file(job.id, "image.png"), "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return ImagesResponse(created=int(time.time()), data=[ImageData(b64_json=data)])


class ImagesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Lemonade fields such as "model" and "response_format"
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    size: str = "1024x1024"
    steps: int = Field(4, ge=1, le=50)
    cfg_scale: float = Field(1.0, ge=0.0, le=30.0)
    seed: int = Field(42, ge=0, le=2**31 - 1)


@router.post("/v1/images/generations")
async def images_generations(req: ImagesRequest) -> ImagesResponse:
    w, h = _size(req.size)
    job = submit_raw(
        "image.generate",
        {"prompt": req.prompt, "framing": None, "width": w, "height": h, "steps": req.steps}
        | {"cfg_scale": req.cfg_scale, "seed": req.seed},
    )
    return _image_response(await _finish(job))


@router.post("/v1/images/edits")
async def images_edits(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    size: str = Form("1024x1024"),
    steps: int = Form(4),
    cfg_scale: float = Form(1.0),
    seed: int = Form(42),
) -> ImagesResponse:
    w, h = _size(size)
    up = storage.save_upload(await image.read(MAX_IMAGE_BYTES + 1), image.filename or "")
    job = submit_raw(
        "image.edit",
        {"image": {"upload": up.id}, "preset": "custom", "prompt": prompt, "width": w, "height": h}
        | {"steps": steps, "cfg_scale": cfg_scale, "seed": seed},
    )
    return _image_response(await _finish(job))


class MeshRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    image: str = Field(min_length=8, max_length=MAX_BODY_BYTES)
    seed: int = Field(42, ge=0, le=2**31 - 1)
    resolution: Literal[512, 1024, 1536] = 512
    bg_removal: Literal["auto", "birefnet", "threshold"] | None = None
    steps: int | None = Field(None, ge=1, le=50)


@router.post("/v1/3d/generations", response_class=Response, responses={200: {"content": {"model/gltf-binary": {}}}})
async def generations_3d(req: MeshRequest) -> Response:
    try:
        png = base64.b64decode(req.image, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "image must be base64") from None
    storage.check_image(png, png_only=True)
    up = storage.save_upload(png, "mesh-input.png")
    # The add-on mattes images itself (local matting server) and sends RGBA; keep the image as sent.
    job = submit_raw(
        "mesh.generate",
        {"image": {"upload": up.id}, "matting": "none", "resolution": req.resolution, "seed": req.seed}
        | {"steps": req.steps},
    )
    done = await _finish(job)
    with open(storage.job_file(done.id, "model.glb"), "rb") as f:
        return Response(f.read(), media_type="model/gltf-binary")
