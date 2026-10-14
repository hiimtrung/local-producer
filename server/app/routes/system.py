"""Health, server status and the job log tail."""

import os
from collections import deque

from fastapi import APIRouter, Query
from pydantic import Field

from .. import __version__, model_setup
from ..engines.registry import EngineStatus, engines
from ..gpu import gib, gpu_lock, gpu_mem
from ..jobs import manager
from ..schemas import ApiModel
from ..settings import paths

router = APIRouter()


class Health(ApiModel):
    status: str
    busy: bool
    gpu_memory_in_use: str


class SystemInfo(ApiModel):
    version: str
    gpu_memory_in_use_bytes: int | None
    gpu_busy: bool
    jobs_queued: int
    jobs_running: int
    models_ready: bool
    engine: EngineStatus
    accelerator: str
    gpu: str
    token_required: bool


class LogLines(ApiModel):
    lines: list[str]
    offset: int = Field(description="Byte position after the last returned line; pass it back as `since`.")
    reset: bool = Field(description="True when `lines` is a fresh tail (first call, or the log was truncated).")


@router.get("/health")
@router.get("/api/v1/health")
def health() -> Health:
    return Health(status="ok", busy=gpu_lock.locked(), gpu_memory_in_use=gib(gpu_mem()))


@router.get("/v1/system")
def system() -> SystemInfo:
    jobs = manager.list(limit=500)
    return SystemInfo(
        version=__version__,
        gpu_memory_in_use_bytes=gpu_mem(),
        gpu_busy=gpu_lock.locked(),
        jobs_queued=sum(1 for j in jobs if j.state == "queued"),
        jobs_running=sum(1 for j in jobs if j.state == "running"),
        models_ready=model_setup.status().ready,
        engine=engines.status(),
        accelerator=engines.host().accelerator,
        gpu=engines.host().gpu,
        token_required=bool(os.environ.get("SERVER_TOKEN")),
    )


# Larger catch-ups than this return a fresh tail instead (a client that slept through a long job).
MAX_CATCH_UP = 1 << 20


def tail(path: str, lines: int) -> LogLines:
    with open(path, "rb") as f:
        kept = deque(f, maxlen=lines)
        offset = f.tell()
    return LogLines(lines=[b.decode(errors="replace") for b in kept], offset=offset, reset=True)


@router.get("/v1/logs")
def logs(
    lines: int = Query(200, ge=1, le=2000),
    since: int | None = Query(None, ge=0, description="Return only what was written after this byte offset."),
) -> LogLines:
    """The job log (CLI output, GPU memory per job): the last `lines` lines, or with `since` only the complete
    lines written after that offset, so a client can follow it live by polling with the offset it got back."""
    try:
        size = os.path.getsize(paths.log)
        if since is None or since > size or size - since > MAX_CATCH_UP:
            return tail(paths.log, lines)
        with open(paths.log, "rb") as f:
            f.seek(since)
            chunk = f.read(size - since)
    except OSError:
        return LogLines(lines=[], offset=0, reset=since is None or since > 0)
    # Only whole lines: a line still being written comes with the next poll.
    end = chunk.rfind(b"\n") + 1
    return LogLines(
        lines=[line.decode(errors="replace") for line in chunk[:end].splitlines(keepends=True)],
        offset=since + end,
        reset=False,
    )
