"""Setup of this machine: the weights (pinned + SHA256-verified, model_setup.py) and, when none is loaded, the engine
package that fits it (app/engines/). `ready` means both are there, so the add-on's one "Download Models" button
still sets up everything."""

import threading
import time

from fastapi import APIRouter, HTTPException

from .. import model_setup
from ..engines.registry import EngineStatus, engines
from ..gpu import log
from ..jobs import manager
from ..schemas import ApiModel, Started

router = APIRouter()
progress = model_setup.Progress()


class VerifyState(ApiModel):
    running: bool = False
    bad: list[str] | None = None  # ids that failed the last verification; None = not verified yet
    checked: float | None = None


class SetupStatus(model_setup.ModelStatus):
    download: model_setup.DownloadProgress
    verify: VerifyState
    models_ready: bool
    engine: EngineStatus
    engine_install: model_setup.DownloadProgress


verify_state = VerifyState()
_verify_lock = threading.Lock()


@router.get("/v1/setup")
def setup_status() -> SetupStatus:
    with _verify_lock:
        verify = verify_state.model_copy()
    models = model_setup.status()
    engine = engines.status()
    install = engines.progress.snapshot()
    rec = engines.recommended()
    missing = models.missing_bytes + (rec.download_size if rec and not engines.ready else 0)
    return SetupStatus(
        ready=models.ready and engine.state == "ready",
        items=models.items,
        missing_bytes=missing,
        download=progress.snapshot(),
        verify=verify,
        models_ready=models.ready,
        engine=engine,
        engine_install=install,
    )


@router.post("/v1/setup/download", status_code=202)
def setup_download() -> Started:
    if progress.snapshot().running or engines.progress.snapshot().running:
        raise HTTPException(409, "a download is already running")
    if manager.busy():
        raise HTTPException(409, "jobs are running or queued; download when they have finished")

    def work() -> None:
        try:
            rec = engines.recommended()
            if not engines.ready and rec is not None:
                progress.log(f"installing the engine package {rec.title}")
                status = engines.install(rec.id)
                progress.log(f"engine: {status.state} {status.problem}".rstrip())
            model_setup.download(progress=progress)
        except Exception as e:  # recorded in progress by download(); keep the thread quiet
            log(f"== setup download failed: {e}")

    progress.update(running=True, error="")
    threading.Thread(target=work, daemon=True).start()
    return Started(started=True)


@router.post("/v1/setup/verify", status_code=202)
def setup_verify() -> Started:
    """Re-hash every installed file against the manifest (a few minutes for ~24 GB)."""
    with _verify_lock:
        if verify_state.running or progress.snapshot().running:
            raise HTTPException(409, "a download or verification is already running")
        verify_state.running, verify_state.bad = True, None

    def work() -> None:
        bad: list[str] | None = None
        try:
            bad = model_setup.verify(log=lambda _line: None)
        finally:
            with _verify_lock:
                verify_state.running, verify_state.bad, verify_state.checked = False, bad, time.time()

    threading.Thread(target=work, daemon=True).start()
    return Started(started=True)


def setup_busy() -> bool:
    return progress.snapshot().running
