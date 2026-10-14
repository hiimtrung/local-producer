"""Generate the default sample image for the TRELLIS.2 Blender add-on: a cute cat, three-quarter view.

Text-to-image with FLUX.2-klein-4B through the GPU server (server/), then background removal with its matting server,
so the add-on gets an RGBA PNG with a real alpha mask. Writes <out>_raw.png and <out>.png.

The prompt is what the add-on's prompt mode sends for "a cute cat", view 3/4, framing on (keep them in sync).
The background is grey: on white, the matting cut out the cat's white belly (CHANGELOG 2026-10-13).

usage: make_sample.py [out_prefix] [seed]   (default: blender/local_producer/samples/cat, seed 7)
       PROMPT=... for another subject; SERVER_TOKEN is sent when set.
"""

import base64
import json
import os
import pathlib
import sys
import time
import urllib.request

SERVER = "http://127.0.0.1:13305"
MATTE = "http://127.0.0.1:8083"
PROMPT = (
    "a cute cat. Full body, standing upright, three-quarter view from the front left, body turned about 45 degrees "
    "so the front and one side are both visible, arms slightly away from the body, the whole character inside the "
    "frame and centered. Stylized 3D cartoon toy figure, soft even studio lighting, plain uniform medium grey "
    "background, no shadow, no text, no logo."
)

PROMPT = os.environ.get("PROMPT", PROMPT)  # other subjects, e.g. test inputs


def post(url, data, ctype, timeout=1800):
    headers = {"Content-Type": ctype}
    if os.environ.get("SERVER_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['SERVER_TOKEN']}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


DEFAULT_OUT = pathlib.Path(__file__).resolve().parents[1] / "blender/local_producer/samples/cat"
out = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_OUT)
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
t = time.time()
body = json.dumps(
    {
        "model": "Flux-2-Klein-4B",
        "prompt": PROMPT,
        "size": "1024x1024",
        "steps": 4,
        "cfg_scale": 1.0,
        "seed": seed,
        "response_format": "b64_json",
    }
).encode()
resp = json.loads(post(f"{SERVER}/v1/images/generations", body, "application/json"))
raw = base64.b64decode(resp["data"][0]["b64_json"])
with open(f"{out}_raw.png", "wb") as f:
    f.write(raw)
print(f"generated in {time.time() - t:.1f} s", flush=True)
t = time.time()
cut = post(f"{MATTE}/matte?model=isnet-general-use", raw, "application/octet-stream")
with open(f"{out}.png", "wb") as f:
    f.write(cut)
print(f"matted in {time.time() - t:.2f} s", flush=True)
