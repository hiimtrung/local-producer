"""Test a model with the loaded engine: load it and make the smallest real output (a 256^2 image in one step, or an
untextured mesh at res 512 in one step), so "it runs on this machine" is measured, not assumed. The result is
recorded with the engine version (model_store.record_check) and shown on the Models page."""

import os
import shutil
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..engines.registry import engines
from ..gpu import JobCancelled, JobFailed, run_cli
from ..model_store import FAMILIES, MODEL_ID, ModelCheck, store
from ..settings import paths
from .base import JobContext, Pipeline
from .flux import flux_args

CHECK_PROMPT = "a red apple on a wooden table"


class CheckParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(pattern=MODEL_ID, description="The model id to test (Models page)")


class CheckJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["model.check"]
    params: CheckParams


class ModelTest(Pipeline[CheckParams]):
    kind = "model.check"
    title = "Test a model"
    description = "Load a model with the loaded engine and make a tiny output, to prove it runs on this machine."
    Params = CheckParams

    def run(self, params: CheckParams, ctx: JobContext) -> list[str]:
        model = store.get(params.model)
        if model is None:
            raise JobFailed("unknown model")
        if not model.present:
            raise JobFailed(f"{model.title}: files are missing")
        if not next(c for c in store.components_status() if c.family == model.family).ready:
            raise JobFailed(f"{model.title}: the shared components are missing; download them on the Models page")
        family = FAMILIES[model.family]
        runner = engines.runner(family.runner)
        ctx.info.model = model.id
        t0 = time.time()
        try:
            if family.id == "flux2-klein":
                ctx.progress.set_stage("Loading the model and making a 256 px image", 1, 1)
                args = [
                    *flux_args(model), "-p", CHECK_PROMPT, "-W", "256", "-H", "256", "--steps", "1",
                    "--cfg-scale", "1", "-s", "1", "-o", os.path.join(ctx.out_dir, "image.png"),
                ]  # fmt: skip
                run_cli(self.kind, runner, args, ctx.timeout, on_line=ctx.progress_line, cancel=ctx.cancel)
                outputs = ["image.png"]
            else:
                ctx.progress.set_stage("Loading the model and making a draft mesh", 1, 1)
                inp = os.path.join(ctx.out_dir, "input.png")
                shutil.copyfile(os.path.join(paths.addon, "samples", "cat.png"), inp)
                out = os.path.join(ctx.out_dir, "model.glb")
                with store.trellis_dir(model) as models_dir:
                    args = [
                        "--image", inp, "--output", out, "--models", models_dir, "--seed", "1",
                        "--res", "512", "--steps", "1", "--no-texture", "--webp", "off", "--require-gpu",
                    ]  # fmt: skip
                    run_cli(self.kind, runner, args, ctx.timeout, on_line=ctx.progress_line, cancel=ctx.cancel)
                for extra in ("model.ply", "model_base.png"):
                    if os.path.exists(os.path.join(ctx.out_dir, extra)):
                        os.unlink(os.path.join(ctx.out_dir, extra))
                outputs = ["model.glb", "input.png"]
            missing = [o for o in outputs if not os.path.isfile(os.path.join(ctx.out_dir, o))]
            if missing:
                raise JobFailed(f"the engine exited without writing {', '.join(missing)}")
        except JobCancelled:
            raise
        except JobFailed as e:
            store.record_check(
                model.id,
                ModelCheck(
                    state="failed",
                    engine=runner.package,
                    at=time.time(),
                    message=str(e)[:500],
                    job=os.path.basename(ctx.out_dir),
                ),
            )
            raise
        store.record_check(
            model.id,
            ModelCheck(
                state="ok",
                engine=runner.package,
                at=time.time(),
                seconds=round(time.time() - t0, 1),
                job=os.path.basename(ctx.out_dir),
            ),
        )
        return outputs
