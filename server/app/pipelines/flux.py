"""FLUX.2-klein-4B via stable-diffusion.cpp (HIP): text-to-image and image edit (reference image)."""

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .. import storage
from ..engines.registry import engines
from ..gpu import run_cli
from ..model_store import MODEL_ID, ModelInfo, store
from ..schemas import JobProgress
from ..settings import MAX_PROMPT_CHARS, config
from .base import BAR_RE, ImageRef, JobContext, Pipeline
from .prompting import Framing, compose, framing_options, resolve_seed


def flux_args(model: ModelInfo) -> list[str]:
    """Built in: q8_0 GGUF diffusion model and text encoder + bf16 VAE: 63 s per 1024^2 image vs 76-80 s from bf16,
    the closest to bf16 of the faster variants (CHANGELOG 2026-10-14 FLUX.2 sweep). A user model replaces the
    diffusion model. Without --vae-tiling the colours wash out. Flash attention in the diffusion model only."""
    return [
        "--diffusion-model", store.path(model, "diffusion"),
        "--llm", store.path(model, "text_encoder"),
        "--vae", store.path(model, "vae"),
        "--vae-tiling", "--flash-attn", "off,diffusion=on", "-v",
    ]  # fmt: skip


def _no_control_chars(v: str) -> str:
    if any(ord(c) < 32 and c not in "\n\t" for c in v):
        raise ValueError("the prompt contains control characters")
    return v


class ImageCommon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int = Field(1024, ge=256, le=2048, multiple_of=16, description="Pixels, multiple of 16")
    height: int = Field(1024, ge=256, le=2048, multiple_of=16, description="Pixels, multiple of 16")
    steps: int | None = Field(None, ge=1, le=50, description="Denoising steps; empty = the server default (4)")
    cfg_scale: float = Field(1.0, ge=0.0, le=30.0, description="Guidance; FLUX.2-klein is distilled for 1.0")
    seed: int = Field(-1, ge=-1, le=2**31 - 1, description="-1 = random")
    model: str | None = Field(
        None, pattern=MODEL_ID, description="A FLUX.2-klein model id (Models page); empty = built in"
    )


class GenerateParams(ImageCommon):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    framing: Framing | None = Field(
        default_factory=Framing, description="Image-to-3D framing appended to the prompt; null = none"
    )
    _check = field_validator("prompt")(_no_control_chars)


class EditParams(ImageCommon):
    image: ImageRef
    preset: Literal["a_pose", "custom"] = Field("a_pose", description="a_pose: arms away from the body for rigging")
    prompt: str = Field("", max_length=MAX_PROMPT_CHARS, description="The edit instruction when preset is custom")
    _check = field_validator("prompt")(_no_control_chars)

    @model_validator(mode="after")
    def prompt_for_custom(self) -> "EditParams":
        if self.preset == "custom" and not self.prompt.strip():
            raise ValueError("a custom edit needs a prompt")
        return self


class GenerateJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["image.generate"]
    params: GenerateParams


class EditJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["image.edit"]
    params: EditParams


def _run_sd(kind: str, prompt: str, params: ImageCommon, ctx: JobContext, ref_path: str | None = None) -> list[str]:
    seed = resolve_seed(params.seed)
    steps = params.steps or config.get().image_steps
    model = store.require("flux2-klein", params.model)
    out = os.path.join(ctx.out_dir, "image.png")
    args = [
        *flux_args(model), "-p", prompt, "-W", str(params.width), "-H", str(params.height),
        "--steps", str(steps), "--cfg-scale", str(params.cfg_scale), "-s", str(seed), "-o", out,
    ]  # fmt: skip
    if ref_path:
        args += ["-r", ref_path]
    ctx.info.prompt, ctx.info.seed, ctx.info.steps, ctx.info.model = prompt, seed, steps, model.id
    ctx.progress.set_stage("Encoding the prompt", 1, 3)
    ctx.progress.denoise_steps = steps
    run_cli(kind, engines.runner("sd-cli"), args, ctx.timeout, on_line=ctx.progress_line, cancel=ctx.cancel)
    return ["image.png"]


class FluxPipeline[P: BaseModel](Pipeline[P]):
    runners = ("sd-cli",)
    model_family = "flux2-klein"

    def parse_progress(self, line: str, progress: JobProgress) -> None:
        """sd-cli prints the same bar for denoising steps (n/steps) and for VAE decode tiles (n/tiles)."""
        m = BAR_RE.search(line)
        if not m:
            return
        done, total = int(m.group(1)), int(m.group(2))
        if total == progress.denoise_steps:
            progress.stage, progress.stage_index = "Denoising", 2
        else:
            progress.stage, progress.stage_index = "Decoding the image", 3
        progress.step, progress.steps = done, total


class ImageGenerate(FluxPipeline[GenerateParams]):
    kind = "image.generate"
    title = "Generate image"
    description = "Text to image with FLUX.2-klein-4B; the framing makes the image suitable for image-to-3D."
    Params = GenerateParams

    def run(self, params: GenerateParams, ctx: JobContext) -> list[str]:
        return _run_sd(self.kind, compose(params.prompt, params.framing), params, ctx)


class ImageEdit(FluxPipeline[EditParams]):
    kind = "image.edit"
    title = "Edit image"
    description = "Change an image with FLUX.2-klein-4B while keeping the subject, e.g. into an A-pose for rigging."
    Params = EditParams

    def run(self, params: EditParams, ctx: JobContext) -> list[str]:
        ref = storage.resolve_image(params.image)
        prompt = framing_options().apose_prompt if params.preset == "a_pose" else params.prompt.strip()
        return _run_sd(self.kind, prompt, params, ctx, ref_path=ref)
