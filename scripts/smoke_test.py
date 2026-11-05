"""End-to-end check of the GPU server, the same calls the Blender add-on makes, back to back:
"Make A-pose" edit of an RGBA image (flattened onto the add-on's mid grey) -> matting -> TRELLIS.2.
Writes <out_dir>/apose.png, apose_matted.png, mesh.glb and prints the wall time of each call.

Run on the host with the dev environment (it has Pillow), the server running:
  uv run python scripts/smoke_test.py blender/local_producer/samples/cat.png build/smoke \
      [res] [image_steps] [mesh_steps]
(make smoke does the Fast variant: 512, 3, 6). SERVER_TOKEN is sent when set.
"""

import io
import os
import pathlib
import sys
import tempfile
import time
import urllib.request

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "blender/local_producer"))
import client  # noqa: E402  (the add-on's HTTP client; no bpy)

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


client.auth["token"] = os.environ.get("SERVER_TOKEN", "")


def post(url, data, ctype, timeout=7200):
    headers = {"Content-Type": ctype}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


src, out_dir = sys.argv[1], sys.argv[2]
res = int(sys.argv[3]) if len(sys.argv) > 3 else 512
image_steps = int(sys.argv[4]) if len(sys.argv) > 4 else 4
mesh_steps = int(sys.argv[5]) if len(sys.argv) > 5 else None
os.makedirs(out_dir, exist_ok=True)
img = Image.open(src).convert("RGBA")
bg = Image.new("RGBA", img.size, tuple(round(c * 255) for c in BACKGROUND) + (255,))
buf = io.BytesIO()
Image.alpha_composite(bg, img).convert("RGB").save(buf, "PNG")

t = time.time()
apose = client.request_edit(API, buf.getvalue(), EDIT_PROMPT, seed=7, steps=image_steps, size=1024)
with open(f"{out_dir}/apose.png", "wb") as f:
    f.write(apose)
print(f"edit {time.time() - t:.1f} s", flush=True)

t = time.time()
matted = post(f"{MATTE}/matte?model=isnet-general-use", apose, "application/octet-stream")
with open(f"{out_dir}/apose_matted.png", "wb") as f:
    f.write(matted)
print(f"matte {time.time() - t:.1f} s", flush=True)

t = time.time()
with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
    tmp.write(matted)
    tmp.flush()
    glb = client.request_glb(API, tmp.name, seed=1234, resolution=res, steps=mesh_steps)
with open(f"{out_dir}/mesh.glb", "wb") as f:
    f.write(glb)
print(
    f"trellis res {res} steps {mesh_steps or 'server default'} {time.time() - t:.1f} s, {len(glb) / 2**20:.1f} MiB",
    flush=True,
)
