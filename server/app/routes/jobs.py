"""Pipelines, uploads and the asynchronous job API used by the web UI.

POST /v1/uploads                 multipart "file" -> UploadInfo
GET  /v1/uploads/{id}            the uploaded image
GET  /v1/pipelines               every pipeline with its parameter JSON schema
POST /v1/jobs                    JobRequest {"kind", "params"} -> the queued Job (202)
GET  /v1/jobs?limit=             newest first
GET  /v1/jobs/{id}               state, progress, info, outputs
POST /v1/jobs/{id}/cancel        cancel a queued or running job
DELETE /v1/jobs/{id}             delete a finished job and its files
GET  /v1/jobs/{id}/files/{name}  a result file
"""

from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError

from .. import model_setup, storage
from ..engines.registry import engines
from ..jobs import manager
from ..model_store import store
from ..pipelines import PIPELINES, JobRequest
from ..pipelines.base import PipelineInfo
from ..schemas import ImageRef, Job, UploadInfo
from ..settings import MAX_IMAGE_BYTES
from . import setup

router = APIRouter()


def validation_error(e: ValidationError) -> HTTPException:
    return HTTPException(422, e.errors(include_url=False, include_context=False, include_input=False))


def check_refs(params: BaseModel) -> None:
    """Every ImageRef in the params must point at an existing image before the job is queued."""
    for name in type(params).model_fields:
        value = getattr(params, name)
        if isinstance(value, ImageRef):
            storage.resolve_image(value)


def submit(kind: str, params: BaseModel) -> Job:
    """Queue validated params for a pipeline once its engine runners and the models are there and every referenced
    image exists."""
    pipeline = PIPELINES[kind]
    missing = engines.missing(pipeline.runners)
    if missing:
        raise HTTPException(503, f"{missing} (Server > Engines)")
    if pipeline.uses_gpu:
        if setup.setup_busy():
            raise HTTPException(503, "models are being downloaded; try again when the download has finished")
        if not model_setup.status().ready:
            raise HTTPException(503, "models are missing: download them first (Models page or POST /v1/setup/download)")
    if pipeline.model_family:
        store.require(pipeline.model_family, getattr(params, "model", None))
    check_refs(params)
    return manager.submit(kind, params)


def submit_raw(kind: str, raw: dict[str, Any]) -> Job:
    """submit() for params built in code (the compat endpoints); invalid values become a 422."""
    try:
        params = PIPELINES[kind].Params.model_validate(raw)
    except ValidationError as e:
        raise validation_error(e) from None
    return submit(kind, params)


@router.get("/v1/pipelines")
def pipelines() -> list[PipelineInfo]:
    return [p.describe() for p in PIPELINES.values()]


@router.post("/v1/uploads")
async def upload(file: UploadFile = File(...)) -> UploadInfo:
    data = await file.read(MAX_IMAGE_BYTES + 1)
    return storage.save_upload(data, file.filename or "")


@router.get("/v1/uploads/{uid}", response_class=FileResponse)
def get_upload(uid: str) -> FileResponse:
    p = storage.upload_path(uid)
    return FileResponse(p, media_type=storage.IMAGE_TYPES[p.rsplit(".", 1)[1]])


@router.post("/v1/jobs", status_code=202)
def create_job(body: JobRequest) -> Job:
    return submit(body.root.kind, body.root.params)


@router.get("/v1/jobs")
def list_jobs(limit: int = Query(50, ge=1, le=500)) -> list[Job]:
    return manager.list(limit)


@router.get("/v1/jobs/{jid}")
def get_job(jid: str) -> Job:
    job = manager.get(storage.check_id(jid, "job id"))
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.post("/v1/jobs/{jid}/cancel")
def cancel_job(jid: str) -> Job:
    job = manager.cancel(storage.check_id(jid, "job id"))
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.delete("/v1/jobs/{jid}", status_code=204)
def delete_job(jid: str) -> None:
    if not manager.delete(storage.check_id(jid, "job id")):
        raise HTTPException(409, "only finished jobs can be deleted")


@router.get("/v1/jobs/{jid}/files/{name}", response_class=FileResponse)
def job_file(jid: str, name: str) -> FileResponse:
    p = storage.job_file(jid, name)
    return FileResponse(p, media_type=storage.MEDIA_TYPES[name.rsplit(".", 1)[1]], filename=name)
