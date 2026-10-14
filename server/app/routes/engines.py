"""Engine packages: what this machine is, what is installed and loaded; install, load, reload, remove.

GET  /v1/engines                          EnginesOverview (host, loaded engine, catalog, installed, storage)
POST /v1/engines/reload                   re-detect the machine, re-read the catalog, load the remembered package
GET  /v1/engines/updates                  newer catalog versions; newer upstream releases of pinned components
POST /v1/engines/{id}/install             download + verify + unpack the newest catalog version, then load it (202)
POST /v1/engines/{id}/{version}/install   the same for a given catalog version
POST /v1/engines/{id}/{version}/load      load an installed version (takes effect with the next job)
DELETE /v1/engines/{id}/{version}         remove an installed version (the loaded one is unloaded first)
"""

import threading

from fastapi import APIRouter, HTTPException, Path

from ..engines.catalog import NAME
from ..engines.registry import EngineBusy, EnginesOverview, EngineStatus, UpdateReport, engines
from ..gpu import log
from ..jobs import manager
from ..model_setup import SetupError
from ..schemas import Started
from . import setup

router = APIRouter()


def _name() -> str:
    """A path parameter checked against the catalog's id pattern (a fresh Path per parameter: FastAPI binds each)."""
    return Path(pattern=NAME)  # type: ignore[no-any-return]


@router.get("/v1/engines")
def overview() -> EnginesOverview:
    return engines.overview()


def _idle() -> None:
    if engines.progress.snapshot().running or setup.setup_busy():
        raise HTTPException(409, "an install or download is running")


@router.post("/v1/engines/reload")
def reload() -> EngineStatus:
    _idle()
    return engines.reload()


@router.get("/v1/engines/updates")
def updates() -> UpdateReport:
    """Newer catalog versions for this machine, and whether the pinned components have newer upstream releases
    (asks api.github.com; information only)."""
    return engines.check_updates()


def _install(pid: str, version: str | None) -> Started:
    _idle()
    if manager.busy():
        raise HTTPException(409, "jobs are running or queued; install when they have finished")
    spec = engines.catalog().find(pid, version)
    if spec is None:
        raise HTTPException(404, "unknown engine package or version")
    mismatch = spec.platform.mismatch(engines.host())
    if mismatch:
        raise HTTPException(409, f"{spec.title} does not fit this machine: {mismatch}")

    def work() -> None:
        try:
            engines.install(spec.id, spec.version)
        except Exception as e:  # recorded in the progress by install(); keep the thread quiet
            log(f"== engine install failed: {e}")

    engines.progress.update(running=True, error="")
    threading.Thread(target=work, daemon=True).start()
    return Started(started=True)


@router.post("/v1/engines/{pid}/install", status_code=202)
def install_latest(pid: str = _name()) -> Started:
    return _install(pid, None)


@router.post("/v1/engines/{pid}/{version}/install", status_code=202)
def install(pid: str = _name(), version: str = _name()) -> Started:
    return _install(pid, version)


@router.post("/v1/engines/{pid}/{version}/load")
def load(pid: str = _name(), version: str = _name()) -> EngineStatus:
    _idle()
    try:
        return engines.load(pid, version)
    except SetupError as e:
        raise HTTPException(404, str(e)) from None


@router.delete("/v1/engines/{pid}/{version}", status_code=204)
def remove(pid: str = _name(), version: str = _name()) -> None:
    _idle()
    try:
        engines.remove(pid, version)
    except EngineBusy as e:
        raise HTTPException(409, str(e)) from None
    except SetupError as e:
        raise HTTPException(404, str(e)) from None
