"""Background removal with rembg on the CPU, through the matting server in the same container (127.0.0.1:8083)."""

import os
import urllib.parse
import urllib.request
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .. import storage
from .base import ImageRef, JobContext, Pipeline

MATTE_URL = os.environ.get("MATTE_URL", "http://127.0.0.1:8083")
MatteModel = Literal["isnet-general-use", "u2net", "birefnet-general-lite", "birefnet-general"]


class MatteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image: ImageRef
    model: MatteModel = Field(
        "isnet-general-use", title="Cutout model", description="isnet ~0.6 s; birefnet slower, sometimes cleaner"
    )
    fill_holes: bool = Field(
        True, title="Fill holes", description="Restore enclosed light regions (e.g. a cream belly) the matte cut out"
    )


class MatteJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["image.matte"]
    params: MatteParams


def matte(path: str, model: MatteModel, fill_holes: bool) -> bytes:
    """RGBA PNG bytes of the image with its background removed."""
    with open(path, "rb") as f:
        data = f.read()
    query = urllib.parse.urlencode({"model": model, "fill_holes": str(fill_holes).lower()})
    req = urllib.request.Request(
        f"{MATTE_URL}/matte?{query}", data=data, headers={"Content-Type": "application/octet-stream"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body: bytes = resp.read()
        return body


class RemoveBackground(Pipeline[MatteParams]):
    kind = "image.matte"
    title = "Remove background"
    description = "Cut the subject out (RGBA PNG) with rembg on the CPU."
    Params = MatteParams
    uses_gpu = False

    def run(self, params: MatteParams, ctx: JobContext) -> list[str]:
        out = matte(storage.resolve_image(params.image), params.model, params.fill_holes)
        with open(os.path.join(ctx.out_dir, "image.png"), "wb") as f:
            f.write(out)
        return ["image.png"]
