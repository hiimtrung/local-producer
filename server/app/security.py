"""Request guards and security headers (rules: SECURITY.md).

* SERVER_TOKEN (optional): every /v1/* request needs "Authorization: Bearer <token>" (constant-time compare). The web
  UI's static files and /health stay open so the UI can load and ask for the token.
* Request bodies over MAX_BODY_BYTES are refused before they are read; a model upload (PUT /v1/models/upload) may
  be up to model_store.MAX_MODEL_BYTES and is streamed to disk, capped while it is written.
* Every response carries a strict Content-Security-Policy: scripts only from this origin (the web UI is one bundle
  built from this repository), no framing, no plugins; plus nosniff and no-referrer.
"""

import hmac
import os
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from .model_store import MAX_MODEL_BYTES
from .settings import MAX_BODY_BYTES

CSP = "; ".join(
    [
        "default-src 'self'",
        # 'wasm-unsafe-eval' lets model-viewer compile its bundled meshopt decoder (WebAssembly; model-viewer 4.4
        # instantiates it at load). It allows WebAssembly compilation only: JavaScript eval stays blocked
        # (approved by the maintainer on 2026-10-15, SECURITY.md).
        "script-src 'self' 'wasm-unsafe-eval'",
        "style-src 'self' 'unsafe-inline'",  # React style props and model-viewer's shadow DOM styles
        "img-src 'self' blob: data:",
        "connect-src 'self' blob: data:",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    ]
)
HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
}
OPEN_PATHS = ("/health", "/api/v1/health")


def token_required(path: str) -> bool:
    return (path.startswith("/v1/") or path == "/v1") and path not in OPEN_PATHS


async def guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    token = os.environ.get("SERVER_TOKEN", "")
    if token and token_required(request.url.path):
        sent = request.headers.get("authorization", "")
        if not hmac.compare_digest(sent.encode(), f"Bearer {token}".encode()):
            return _with_headers(JSONResponse({"detail": "missing or wrong token"}, status_code=401))
    length = request.headers.get("content-length")
    cap = MAX_MODEL_BYTES if (request.method, request.url.path) == ("PUT", "/v1/models/upload") else MAX_BODY_BYTES
    if length is not None and (not length.isdigit() or int(length) > cap):
        return _with_headers(JSONResponse({"detail": "request body too large"}, status_code=413))
    response = _with_headers(await call_next(request))
    if not request.url.path.startswith("/v1/"):
        # The UI's files keep fixed names (app.js, app.css): make browsers revalidate (ETag -> 304) so a rebuilt UI
        # shows up on the next load instead of a heuristically cached old one.
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


def _with_headers(response: Response) -> Response:
    for k, v in HEADERS.items():
        response.headers.setdefault(k, v)
    return response
