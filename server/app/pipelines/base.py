"""The pipeline contract: one class per capability (text-to-image, image edit, matting, image-to-3D, ...).

To add a capability, write a module in this package with a Pipeline subclass and register it in __init__.py:
  * `kind`        stable id used by the API and the web UI ("image.generate")
  * `title`, `description`   shown in the web UI
  * `Params`      a pydantic model; every field validated, bounded, documented (it becomes the API's JSON schema and
                  the web form's ranges and defaults)
  * a request model `{kind: Literal[...], params: Params}` for the typed job API (POST /v1/jobs)
  * `runners`     the engine runners it starts (e.g. "sd-cli"); jobs are refused while the loaded engine
                  package lacks one (app/engines/)
  * `model_family` the model family its `model` param picks from (app/model_store.py); checked before queueing
  * `run(params, ctx)`        do the work, write result files into ctx.out_dir, return their names
  * `parse_progress(line, progress)`   optional: turn CLI output lines into progress for the UI
Pipelines never build shell strings and never read paths from clients: images come in as references resolved by
storage.resolve_image.
"""

import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

from pydantic import BaseModel, JsonValue

from ..schemas import ApiModel, ImageRef, JobInfo, JobProgress

__all__ = ["BAR_RE", "ImageRef", "JobContext", "Pipeline", "PipelineInfo"]

STAGE_RE = re.compile(r"^\s*\[(\d+)/(\d+)\]\s+(.*)$")  # trellis-cli "[4/7] shape SLAT flow (512)"
FLOW_RE = re.compile(r"\[flow\] \[[#.]*\]\s+(\d+)/(\d+)")  # trellis-cli "[flow] [###.....]  3/8 ..."
BAR_RE = re.compile(r"\|[=> ]*\|\s*(\d+)/(\d+)")  # sd-cli "|=====>    | 2/4 - 10.2s/it"


def _no_line(line: str) -> None:
    return None


@dataclass
class JobContext:
    out_dir: str
    timeout: int
    cancel: threading.Event
    progress: JobProgress = field(default_factory=JobProgress)
    info: JobInfo = field(default_factory=JobInfo)  # facts worth showing with the result (final prompt, seed, faces)
    progress_line: Callable[[str], None] = _no_line  # set by the job runner: feeds parse_progress


class PipelineInfo(ApiModel):
    kind: str
    title: str
    description: str
    uses_gpu: bool
    params: dict[str, JsonValue] = {}  # the Params JSON schema


class Pipeline[P: BaseModel]:
    kind: ClassVar[str] = ""
    title: ClassVar[str] = ""
    description: ClassVar[str] = ""
    uses_gpu: ClassVar[bool] = True
    runners: ClassVar[tuple[str, ...]] = ()
    model_family: ClassVar[str | None] = None
    Params: type[P]

    def run(self, params: P, ctx: JobContext) -> list[str]:  # pragma: no cover - interface
        raise NotImplementedError

    def parse_progress(self, line: str, progress: JobProgress) -> None:
        """Default: understands trellis-cli stages and flow steps and sd-cli progress bars."""
        m = STAGE_RE.match(line)
        if m:
            stage = re.sub(r"\s+/\S+", "", m.group(3)).strip()  # no internal paths in the UI
            progress.set_stage(stage[:1].upper() + stage[1:], int(m.group(1)), int(m.group(2)))
            return
        m = FLOW_RE.search(line) or BAR_RE.search(line)
        if m:
            progress.step, progress.steps = int(m.group(1)), int(m.group(2))

    def validate(self, raw: dict[str, JsonValue]) -> P:
        return self.Params.model_validate(raw)

    def describe(self) -> PipelineInfo:
        return PipelineInfo(
            kind=self.kind,
            title=self.title,
            description=self.description,
            uses_gpu=self.uses_gpu,
            params=self.Params.model_json_schema(),
        )
