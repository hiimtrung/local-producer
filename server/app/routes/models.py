"""Models the pipelines can use (app/model_store.py): list, add from a link or an upload, test, remove.

GET    /v1/models                    ModelsOverview: families, built-in and added models with their last test
POST   /v1/models                    AddModel {family, title, url}: download in the background (202)
PUT    /v1/models/upload?family=&title=&filename=   the raw file as the body (streamed to disk) -> ModelInfo
POST   /v1/models/{id}/check         queue a "model.check" job with the loaded engine -> Job
DELETE /v1/models/{id}               remove a model you added
DELETE /v1/models/adding             clear the last add's error
"""

import threading

from fastapi import APIRouter, HTTPException, Path, Query, Request

from ..engines.registry import engines
from ..gpu import log
from ..jobs import manager
from ..model_setup import SetupError
from ..model_store import FAMILIES, MODEL_ID, AddModel, ModelInfo, ModelsOverview, store
from ..pipelines.check import CheckParams
from ..schemas import Job, Started

router = APIRouter()


@router.get("/v1/models")
def overview() -> ModelsOverview:
    return store.overview()


@router.post("/v1/models", status_code=202)
def add(req: AddModel) -> Started:
    if req.family not in FAMILIES:
        raise HTTPException(422, "unknown model family")
    if store.progress.snapshot().running:
        raise HTTPException(409, "a model is already being added")

    def work() -> None:
        try:
            store.add_from_url(req)
        except Exception as e:  # recorded in the progress by add_from_url(); keep the thread quiet
            log(f"== adding a model failed: {e}")

    store.progress.update(running=True, error="", log=[])
    threading.Thread(target=work, daemon=True).start()
    return Started(started=True)


@router.delete("/v1/models/adding", status_code=204)
def dismiss() -> None:
    """Clear the last add's error message."""
    store.clear_adding()


@router.put("/v1/models/upload")
async def upload(
    request: Request,
    family: str = Query(pattern=r"^[a-z0-9-]{1,40}$"),
    title: str = Query(min_length=1, max_length=80),
    filename: str = Query(min_length=1, max_length=120),
) -> ModelInfo:
    try:
        sink = store.begin_upload(family, title, filename)
    except SetupError as e:
        raise HTTPException(422, str(e)) from None
    try:
        async for chunk in request.stream():
            sink.write(chunk)
        return sink.finish()
    except SetupError as e:
        raise HTTPException(422, str(e)) from None
    finally:
        sink.abort()


@router.post("/v1/models/{model_id}/check", status_code=202)
def check(model_id: str = Path(pattern=MODEL_ID)) -> Job:
    m = store.get(model_id)
    if m is None:
        raise HTTPException(404, "unknown model")
    if not m.present:
        raise HTTPException(409, f"{m.title}: files are missing")
    missing = engines.missing((FAMILIES[m.family].runner,))
    if missing:
        raise HTTPException(503, f"{missing} (Server > Engines)")
    return manager.submit("model.check", CheckParams(model=model_id))


@router.delete("/v1/models/{model_id}", status_code=204)
def remove(model_id: str = Path(pattern=MODEL_ID)) -> None:
    if manager.busy():
        raise HTTPException(409, "jobs are running or queued; remove the model when they have finished")
    try:
        store.remove(model_id)
    except SetupError as e:
        raise HTTPException(404 if "unknown" in str(e) else 409, str(e)) from None
