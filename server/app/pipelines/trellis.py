"""TRELLIS.2 image-to-3D via trellis.cpp (HIP): a PBR-textured GLB from one image."""

import io
import os
import re
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from .. import storage
from ..engines.registry import engines
from ..gpu import run_cli
from ..model_store import MODEL_ID, store
from ..settings import config
from .base import ImageRef, JobContext, Pipeline
from .matte import MatteModel, matte
from .prompting import resolve_seed

FACES_RE = re.compile(r"decimate\w*\(.*\):.*F \d+->(\d+)")


class MeshParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image: ImageRef
    matting: Literal["auto", "rembg", "none"] = Field(
        "auto", description="auto: remove the background with rembg unless the image already has transparency"
    )
    matte_model: MatteModel = "isnet-general-use"
    resolution: Literal[512, 1024, 1536] | None = Field(
        None, description="Geometry resolution; 512 ~4.5 min, 1024 ~19 min, 1536 ~53 min (cat sample)"
    )
    steps: int | None = Field(None, ge=1, le=50, description="Flow steps per stage; empty = server default (8)")
    seed: int = Field(1234, ge=-1, le=2**31 - 1, description="-1 = random")
    texture: bool = Field(True, description="Off: geometry only (faster)")
    atlas: Literal[1024, 2048, 4096] | None = Field(None, description="UV atlas size; empty = 1024 @512 / 2048 @1024")
    structure_guidance: float | None = Field(None, ge=0.0, le=20.0, description="--gss; empty = model default")
    shape_guidance: float | None = Field(None, ge=0.0, le=20.0, description="--gsh; empty = model default")
    max_tokens: int | None = Field(
        None, ge=4096, le=49152, description="HR token budget at res 1024+; lower is faster, loses detail"
    )
    model: str | None = Field(
        None, pattern=MODEL_ID, description="A TRELLIS.2 model set id (Models page); empty = built in"
    )


class MeshJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["mesh.generate"]
    params: MeshParams


def _has_transparency(path: str) -> bool:
    with Image.open(path) as img:
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            alpha_min = img.convert("RGBA").getchannel("A").getextrema()[0]
            return isinstance(alpha_min, int | float) and alpha_min < 255  # one band: (min, max) numbers
    return False


def _as_png(path: str) -> bytes:
    with Image.open(path) as img:
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()


class ImageTo3D(Pipeline[MeshParams]):
    kind = "mesh.generate"
    title = "Generate 3D model"
    description = "Image to PBR-textured GLB with TRELLIS.2; the background is removed first when needed."
    Params = MeshParams
    runners = ("trellis-cli",)
    model_family = "trellis2"

    def run(self, params: MeshParams, ctx: JobContext) -> list[str]:
        src = storage.resolve_image(params.image)
        need_matte = params.matting == "rembg" or (params.matting == "auto" and not _has_transparency(src))
        inp = os.path.join(ctx.out_dir, "input.png")
        if need_matte:
            ctx.progress.set_stage("Removing the background")
        with open(inp, "wb") as f:
            f.write(matte(src, params.matte_model, True) if need_matte else _as_png(src))
        cfg = config.get()
        model = store.require("trellis2", params.model)
        res = params.resolution or cfg.mesh_resolution
        steps = params.steps or cfg.mesh_steps
        seed = resolve_seed(params.seed)
        out = os.path.join(ctx.out_dir, "model.glb")
        args = [
            "--image", inp, "--output", out,
            "--models", store.path(model, "dir"), "--seed", str(seed), "--res", str(res),
            "--steps", str(steps), "--webp", "off", "--require-gpu",
        ]  # fmt: skip
        if not params.texture:
            args.append("--no-texture")
        if params.atlas:
            args += ["--atlas", str(params.atlas)]
        if params.structure_guidance is not None:
            args += ["--gss", str(params.structure_guidance)]
        if params.shape_guidance is not None:
            args += ["--gsh", str(params.shape_guidance)]
        if params.max_tokens:
            args += ["--max-tokens", str(params.max_tokens)]
        ctx.info.seed, ctx.info.steps, ctx.info.resolution, ctx.info.matted = seed, steps, res, need_matte
        ctx.info.model = model.id

        def on_line(line: str) -> None:
            m = FACES_RE.search(line)
            if m:
                ctx.info.faces = int(m.group(1))
            ctx.progress_line(line)

        run_cli(f"trellis-{res}", engines.runner("trellis-cli"), args, ctx.timeout, on_line=on_line, cancel=ctx.cancel)
        for extra in ("model.ply", "model_base.png"):  # side outputs trellis-cli writes next to the GLB
            p = os.path.join(ctx.out_dir, extra)
            if os.path.exists(p):
                os.unlink(p)
        return ["model.glb", "input.png"]
