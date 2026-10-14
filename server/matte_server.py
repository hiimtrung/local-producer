"""Background-removal (matting) HTTP server: image bytes in, RGBA PNG out (rembg on the CPU, onnxruntime).

Used by the TRELLIS.2 Blender add-on before the GPU server's /v1/3d/generations: trellis.cpp's own BiRefNet was wrong
on RADV
(its custom Vulkan deformable conv; CHANGELOG 2026-10-12) and its CPU fallback takes ~190 s.

POST /matte?model=isnet-general-use&fill_holes=true   body = image file bytes (PNG/JPEG/WebP)  -> image/png (RGBA)
GET  /health

fill_holes (default on): rembg sometimes cuts out a light body part that is enclosed by the object, e.g. a cream
belly on the grey background (it became black on the 3D model, CHANGELOG 2026-10-13). Enclosed holes whose colour
is clearly not the background colour are restored with the input pixels.
"""

import argparse
import io
import logging
import threading
import time

import numpy as np
import numpy.typing as npt
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from PIL import Image, ImageDraw, ImageFilter
from rembg import new_session, remove

Mask = npt.NDArray[np.bool_]

log = logging.getLogger("matte")
app = FastAPI()
_sessions: dict[str, object] = {}
_lock = threading.Lock()
MODELS = ("isnet-general-use", "u2net", "birefnet-general-lite", "birefnet-general")


def _grow(mask: Mask, px: int) -> Mask:
    grown: Mask = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(px))) > 127
    return grown


def restore_holes(
    raw: Image.Image, cut: Image.Image, seal_px: int = 15, min_dist: float = 40.0
) -> tuple[Image.Image, int]:
    """Return (cut, restored_px): enclosed holes in the matte that are not background-coloured become opaque.

    The matte is first closed with a seal_px max filter (thin soft-alpha leaks would connect a hole to the
    outside); background reachable from the image border is real background; every other background region is a
    hole, grown back to the original matte edge. A hole is restored (alpha 255, raw colours) when its mean RGB
    distance to the background colour (median of the border pixels) is above min_dist.
    """
    rgb = np.asarray(raw.convert("RGB"))
    out = np.asarray(cut.convert("RGBA")).copy()
    fg = out[..., 3] > 127
    # .copy(): an image made by fromarray can share a read-only buffer, and floodfill then silently does nothing
    m = Image.fromarray(np.pad(~_grow(fg, seal_px), 1, constant_values=True).astype(np.uint8) * 255).copy()
    ImageDraw.floodfill(m, (0, 0), 0)
    holes = np.asarray(m)[1:-1, 1:-1] == 255
    if not holes.any():
        return cut, 0
    bg = np.median(np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]), 0)
    dist = np.linalg.norm(rgb.astype(np.float32) - bg, axis=2)
    labels = Image.fromarray(holes.astype(np.uint8) * 255).copy()
    restored = 0
    for y, x in zip(*np.nonzero(holes), strict=True):
        if labels.getpixel((int(x), int(y))) != 255:
            continue  # already part of a handled hole
        ImageDraw.floodfill(labels, (int(x), int(y)), 100)
        comp = np.asarray(labels) == 100
        region = _grow(comp, seal_px) & ~fg
        if dist[region].mean() > min_dist:
            out[region, :3] = rgb[region]
            out[region, 3] = 255
            restored += int(region.sum())
        labels = Image.fromarray(np.where(comp, 0, np.asarray(labels)).astype(np.uint8)).copy()
    return Image.fromarray(out), restored


def session(name: str) -> object:
    if name not in _sessions:
        _sessions[name] = new_session(name)
    return _sessions[name]


@app.get("/health")
def health() -> dict[str, object]:
    return {"models": MODELS, "loaded": sorted(_sessions)}


@app.post("/matte")
async def matte(request: Request, model: str = "isnet-general-use", fill_holes: bool = True) -> Response:
    if model not in MODELS:
        raise HTTPException(400, f"model must be one of {MODELS}")
    data = await request.body()
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as e:
        raise HTTPException(400, f"cannot decode image: {e}") from e
    t = time.time()
    with _lock:
        cut = remove(img, session=session(model))
    restored = 0
    if fill_holes:
        cut, restored = restore_holes(img, cut)
    buf = io.BytesIO()
    cut.save(buf, format="PNG")
    log.info("matte %s %dx%d in %.2f s, %d hole px restored", model, img.width, img.height, time.time() - t, restored)
    return Response(buf.getvalue(), media_type="image/png")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8083)
    p.add_argument("--preload", default="isnet-general-use")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.preload:
        session(args.preload)
    uvicorn.run(app, host=args.host, port=args.port)
