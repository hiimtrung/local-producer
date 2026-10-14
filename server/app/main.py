"""Application factory and entry point: `python -m app.main [--host H] [--port P]` (cwd = server/)."""

import argparse
import os

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import __version__, model_setup
from .engines.registry import engines
from .gpu import gib, gpu_mem, log
from .routes import ROUTERS
from .security import guard
from .settings import paths


def create_app() -> FastAPI:
    app = FastAPI(title="local-producer GPU server", version=__version__, docs_url=None, redoc_url=None)
    app.middleware("http")(guard)
    for router in ROUTERS:
        app.include_router(router)
    if os.path.isfile(os.path.join(paths.web, "index.html")):
        app.mount("/", StaticFiles(directory=paths.web, html=True), name="web")
    return app


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="0.0.0.0")  # inside the container; the host publishes 127.0.0.1 only
    p.add_argument("--port", type=int, default=13305)
    args = p.parse_args()
    model_setup.MODELS = paths.models
    ready = model_setup.status().ready
    host = engines.host()
    log(
        f"== server {__version__} start on :{args.port}, {host.os} {host.arch} {host.accelerator} ({host.gpu}), "
        f"models {'ready' if ready else 'MISSING'}, GPU memory in use {gib(gpu_mem())}"
    )
    # A package that fails its checks (e.g. ROCm with cwsr_enable=1) is not loaded: the server still starts, so the
    # web UI can say why, but no GPU job runs.
    engine = engines.reload()
    if engine.state != "ready":
        log(f"== no engine loaded: {engine.problem}")
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
