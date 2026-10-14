"""Data models shared by the job queue, the pipelines and the routes. Every API response is a pydantic model, so the
OpenAPI schema is complete and the web UI's TypeScript types are generated from it (scripts/gen_api_types.py)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

ID_PATTERN = r"^[0-9a-f]{32}$"
IMAGE_NAME_PATTERN = r"^[a-z0-9_]{1,40}\.(png|jpg|webp)$"

JobState = Literal["queued", "running", "done", "failed", "cancelled"]
ACTIVE_STATES: tuple[JobState, ...] = ("queued", "running")


class ApiModel(BaseModel):
    """Base of every response model: fields with defaults are still always present in a response, so the generated
    TypeScript types mark them required."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class ImageRef(BaseModel):
    """An uploaded image ({"upload": id}) or a result of an earlier job ({"job": id, "file": "image.png"})."""

    model_config = ConfigDict(extra="forbid")
    upload: str | None = Field(None, pattern=ID_PATTERN)
    job: str | None = Field(None, pattern=ID_PATTERN)
    file: str = Field("image.png", pattern=IMAGE_NAME_PATTERN)

    @model_validator(mode="after")
    def exactly_one(self) -> "ImageRef":
        if bool(self.upload) == bool(self.job):
            raise ValueError("give exactly one of upload or job")
        return self


class JobProgress(ApiModel):
    """What a running job is doing, parsed from its CLI output. fraction is filled in when the job is read."""

    model_config = ConfigDict(extra="ignore")
    stage: str | None = None
    stage_index: int | None = None
    stages: int | None = None
    step: int | None = None
    steps: int | None = None
    denoise_steps: int | None = Field(None, description="FLUX: the bar total that means denoising, not VAE tiles")
    fraction: float | None = Field(None, ge=0.0, le=1.0, description="0..1 estimate; null while nothing is known")

    def set_stage(self, stage: str, index: int | None = None, stages: int | None = None) -> None:
        self.stage = stage
        if index is not None:
            self.stage_index = index
        if stages is not None:
            self.stages = stages
        self.step = self.steps = None

    def estimate(self) -> float | None:
        """0..1 from the stage and step counters (None when nothing is known yet)."""
        step = self.step / self.steps if self.steps and self.step is not None else 0.0
        if self.stages and self.stage_index:
            return min(1.0, (self.stage_index - 1 + step) / self.stages)
        if self.steps:
            return step
        return None


class JobInfo(ApiModel):
    """Facts worth showing with a result. A pipeline that reports something new adds a field here."""

    model_config = ConfigDict(extra="ignore")
    prompt: str | None = Field(None, description="The prompt sent to the model (after framing)")
    seed: int | None = None
    steps: int | None = None
    resolution: int | None = None
    matted: bool | None = Field(None, description="The background was removed before image-to-3D")
    faces: int | None = None
    model: str | None = Field(None, description="The model id the job ran with")


class Job(ApiModel):
    """A queued, running or finished job. params are the pipeline's validated parameters (see JobRequest)."""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(pattern=ID_PATTERN)
    kind: str
    state: JobState
    params: dict[str, JsonValue]
    progress: JobProgress = Field(default_factory=JobProgress)
    info: JobInfo = Field(default_factory=JobInfo)
    outputs: list[str] = Field(default_factory=list)
    error: str = ""
    created: float
    started: float | None = None
    finished: float | None = None
    queue_position: int | None = Field(None, description="1 = next; only while queued")

    @property
    def active(self) -> bool:
        return self.state in ACTIVE_STATES


class UploadInfo(ApiModel):
    id: str = Field(pattern=ID_PATTERN)
    type: str
    size: int
    name: str


class Started(ApiModel):
    started: bool
