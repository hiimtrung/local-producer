"""The job queue: FIFO, one worker (one GPU job at a time), persisted records, progress, cancellation.

A job is a schemas.Job; its state goes queued -> running -> done | failed | cancelled. Records live in
<data>/jobs/<id>/job.json next to the results, so the history survives restarts (a job that was queued or running
when the server stopped is marked failed).
"""

import os
import shutil
import threading
import time
from collections import deque
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from pydantic.main import IncEx

from . import storage
from .gpu import JobCancelled, JobFailed, log
from .pipelines import PIPELINES
from .pipelines.base import JobContext, Pipeline
from .schemas import Job, JobState
from .settings import config, paths

NOT_STORED: dict[str, IncEx | bool] = {"queue_position": True, "progress": {"fraction": True}}


class JobManager:
    def __init__(self) -> None:
        self.lock = threading.Condition()
        self.jobs: dict[str, Job] = {}
        self.queue: deque[str] = deque()
        self.cancels: dict[str, threading.Event] = {}
        self.worker: threading.Thread | None = None
        self.loaded = False

    # ------------------------------------------------------------ persistence

    def load(self) -> None:
        """Read job records from disk once (newest first is the listing order)."""
        with self.lock:
            if self.loaded:
                return
            self.loaded = True
            if not os.path.isdir(paths.jobs):
                return
            for jid in os.listdir(paths.jobs):
                path = os.path.join(paths.jobs, jid, "job.json")
                if not storage.ID_RE.match(jid) or not os.path.isfile(path):
                    continue
                try:
                    with open(path) as f:
                        job = Job.model_validate_json(f.read())
                except (OSError, ValidationError):
                    continue
                if job.active:
                    job.state, job.error = "failed", "the server stopped before the job finished"
                    self._save(job)
                self.jobs[jid] = job

    def _save(self, job: Job) -> None:
        d = storage.job_dir(job.id)
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, "job.json.tmp")
        with open(tmp, "w") as f:
            f.write(job.model_dump_json(exclude=NOT_STORED))
        os.replace(tmp, os.path.join(d, "job.json"))

    # ------------------------------------------------------------ API

    def submit(self, kind: str, params: BaseModel) -> Job:
        """Queue a job; params is the pipeline's validated Params instance."""
        self.load()
        job = Job(
            id=storage.new_id(), kind=kind, state="queued", params=params.model_dump(mode="json"), created=time.time()
        )
        with self.lock:
            self.jobs[job.id] = job
            self.queue.append(job.id)
            self.cancels[job.id] = threading.Event()
            self._save(job)
            if self.worker is None or not self.worker.is_alive():
                self.worker = threading.Thread(target=self._work, daemon=True, name="job-worker")
                self.worker.start()
            self.lock.notify_all()
        storage.prune(paths.jobs, config.get().keep_jobs)
        return self.public(job)

    def public(self, job: Job) -> Job:
        """A snapshot for the API: progress fraction and queue position filled in."""
        with self.lock:
            out = job.model_copy(deep=True)
            out.progress.fraction = out.progress.estimate()
            out.queue_position = (
                self.queue.index(job.id) + 1 if job.state == "queued" and job.id in self.queue else None
            )
        return out

    def get(self, jid: str) -> Job | None:
        self.load()
        with self.lock:
            job = self.jobs.get(jid)
        return self.public(job) if job else None

    def list(self, limit: int = 50) -> list[Job]:
        self.load()
        with self.lock:
            jobs = sorted(self.jobs.values(), key=lambda j: j.created, reverse=True)[:limit]
        return [self.public(j) for j in jobs]

    def cancel(self, jid: str) -> Job | None:
        """Cancel a queued or running job. Returns the job or None."""
        with self.lock:
            job = self.jobs.get(jid)
            if not job:
                return None
            if job.state == "queued":
                self.queue.remove(jid)
                job.state, job.finished = "cancelled", time.time()
                self._save(job)
            elif job.state == "running":
                self.cancels[jid].set()
        return self.public(job)

    def delete(self, jid: str) -> bool:
        """Remove a finished job and its files."""
        with self.lock:
            job = self.jobs.get(jid)
            if not job or job.active:
                return False
            del self.jobs[jid]
        shutil.rmtree(storage.job_dir(jid), ignore_errors=True)
        return True

    def wait(self, jid: str, timeout: float | None = None) -> Job:
        """Block until the job has finished (used by the Lemonade-compatible endpoints)."""
        deadline = None if timeout is None else time.time() + timeout
        with self.lock:
            while self.jobs[jid].active:
                left = None if deadline is None else deadline - time.time()
                if left is not None and left <= 0:
                    break
                self.lock.wait(timeout=left if left is not None else 1.0)
            job = self.jobs[jid]
        return self.public(job)

    def busy(self) -> bool:
        with self.lock:
            return bool(self.queue) or any(j.state == "running" for j in self.jobs.values())

    # ------------------------------------------------------------ worker

    def _work(self) -> None:
        while True:
            with self.lock:
                while not self.queue:
                    self.lock.wait()
                jid = self.queue.popleft()
                job = self.jobs[jid]
                job.state, job.started = "running", time.time()
                self._save(job)
                self.lock.notify_all()
            self._run(job)

    def _run(self, job: Job) -> None:
        pipeline: Pipeline[Any] = PIPELINES[job.kind]
        ctx = JobContext(
            out_dir=storage.job_dir(job.id),
            timeout=config.get().job_timeout_s,
            cancel=self.cancels[job.id],
            progress=job.progress,
            info=job.info,
            progress_line=lambda line: pipeline.parse_progress(line, job.progress),
        )
        outputs: list[str] = []
        error = ""
        state: JobState
        try:
            outputs = pipeline.run(pipeline.validate(job.params), ctx)
            state = "done"
        except JobCancelled:
            state = "cancelled"
        except HTTPException as e:  # e.g. a referenced image vanished
            state, error = "failed", str(e.detail)
        except (JobFailed, OSError, ValueError) as e:
            state, error = "failed", str(e)
        except Exception as e:  # a pipeline bug must not kill the worker
            state, error = "failed", f"internal error: {e}"
            log(f"== job {job.id} internal error: {e!r}")
        with self.lock:
            job.state, job.error, job.outputs, job.finished = state, error, outputs, time.time()
            self._save(job)
            self.lock.notify_all()


manager = JobManager()
