"""End-to-end check of the GPU server, the same calls the Blender add-on makes, back to back:
"Make A-pose" edit of an RGBA image (flattened onto the add-on's mid grey) -> matting -> TRELLIS.2.
Writes <out_dir>/apose.png, apose_matted.png, mesh.glb and prints the wall time of each call.

Run on the host with the dev environment (it has Pillow), the server running:
  uv run python scripts/smoke_test.py blender/local_producer/samples/cat.png build/smoke \
      [res] [image_steps] [mesh_steps]
(make smoke does the Fast variant: 512, 3, 6). SERVER_TOKEN is sent when set.
"""

import base64
import io
import json
import os
import sys
import time
import urllib.request
import uuid

from PIL import Image

API, MATTE = "http://127.0.0.1:13305", "http://127.0.0.1:8083"
# Keep in sync with blender/local_producer (APOSE_EDIT + FRAMING_TAIL, EDIT_BACKGROUND).
EDIT_PROMPT = (
    "Change only the pose of this character: both arms stretched down and out to the sides at about 45 "
    "degrees (A-pose), hands or paws far from the body with clear empty space between each arm and the "
    "torso, legs slightly apart. Keep exactly the same character: same body shape and proportions, same "
    "head, same limbs, same colours and markings, same view, same framing. The whole character inside the "
    "frame and centered. Stylized 3D cartoon toy figure, soft even studio lighting, plain uniform medium grey "
    "background, no shadow, no text, no logo."
)
BACKGROUND = (0.53, 0.54, 0.54)


def post(url, data, ctype, timeout=7200):
    headers = {"Content-Type": ctype}
    if os.environ.get("SERVER_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['SERVER_TOKEN']}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


src, out_dir = sys.argv[1], sys.argv[2]
res = int(sys.argv[3]) if len(sys.argv) > 3 else 512
image_steps = sys.argv[4] if len(sys.argv) > 4 else "4"
mesh_steps = int(sys.argv[5]) if len(sys.argv) > 5 else None
os.makedirs(out_dir, exist_ok=True)
img = Image.open(src).convert("RGBA")
bg = Image.new("RGBA", img.size, tuple(round(c * 255) for c in BACKGROUND) + (255,))
buf = io.BytesIO()
Image.alpha_composite(bg, img).convert("RGB").save(buf, "PNG")

t = time.time()
b = uuid.uuid4().hex
fields = {
    "model": "Flux-2-Klein-4B",
    "prompt": EDIT_PROMPT,
    "size": "1024x1024",
    "steps": image_steps,
    "cfg_scale": "1.0",
    "seed": "7",
    "response_format": "b64_json",
}
body = b"".join(
    f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()
)
body += (
    (
        f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="image.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode()
    + buf.getvalue()
    + f"\r\n--{b}--\r\n".encode()
)
apose = base64.b64decode(
    json.loads(post(f"{API}/v1/images/edits", body, f"multipart/form-data; boundary={b}"))["data"][0]["b64_json"]
)
with open(f"{out_dir}/apose.png", "wb") as f:
    f.write(apose)
print(f"edit {time.time() - t:.1f} s", flush=True)

t = time.time()
matted = post(f"{MATTE}/matte?model=isnet-general-use", apose, "application/octet-stream")
with open(f"{out_dir}/apose_matted.png", "wb") as f:
    f.write(matted)
print(f"matte {time.time() - t:.1f} s", flush=True)

t = time.time()
glb = post(
    f"{API}/v1/3d/generations",
    json.dumps(
        {
            "model": "TRELLIS-3D",
            "image": base64.b64encode(matted).decode(),
            "seed": 1234,
            "resolution": res,
            **({"steps": mesh_steps} if mesh_steps else {}),
        }
    ).encode(),
    "application/json",
)
with open(f"{out_dir}/mesh.glb", "wb") as f:
    f.write(glb)
print(
    f"trellis res {res} steps {mesh_steps or 'server default'} {time.time() - t:.1f} s, {len(glb) / 2**20:.1f} MiB",
    flush=True,
)
