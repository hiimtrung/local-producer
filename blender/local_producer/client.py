"""HTTP client for the local-producer GPU server and matting server. No bpy: unit-tested outside Blender.

All calls raise RuntimeError with a short message on failure. If the server was started with SERVER_TOKEN, put the
token into `auth["token"]` (the add-on copies its "Server Token" preference there before each job).
"""

import base64
import json
import urllib.error
import urllib.request
import uuid

REQUEST_TIMEOUT_S = 3600  # res 512 takes ~4-5 min on the Radeon 780M, res 1024 ~19 min (raise for 1536: ~53 min)
DEFAULT_MODEL = "TRELLIS-3D"  # ignored by the server; kept for the request format it shares with AMD Lemonade
DEFAULT_IMAGE_MODEL = "Flux-2-Klein-4B"
auth = {"token": ""}


def _headers(ctype):
    h = {"Content-Type": ctype}
    if auth["token"]:
        h["Authorization"] = f"Bearer {auth['token']}"
    return h


def _call(url, data, ctype, timeout, what, method="POST"):
    req = urllib.request.Request(url, data=data, headers=_headers(ctype), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{what} returned {e.code}: {e.read().decode(errors='replace')[:300]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"cannot reach {what} at {url.split('/v1')[0]}: {e.reason}") from e


def request_image(api_url, prompt, model=DEFAULT_IMAGE_MODEL, seed=7, steps=4, size=1024, timeout=REQUEST_TIMEOUT_S):
    """Text-to-image via /v1/images/generations; returns PNG bytes."""
    payload = {
        "model": model,
        "prompt": prompt,
        "size": f"{size}x{size}",
        "steps": steps,
        "cfg_scale": 1.0,
        "seed": seed,
        "response_format": "b64_json",
    }
    body = _call(
        api_url.rstrip("/") + "/v1/images/generations",
        json.dumps(payload).encode(),
        "application/json",
        timeout,
        "the server",
    )
    return base64.b64decode(json.loads(body)["data"][0]["b64_json"])


def request_edit(
    api_url, png_bytes, prompt, model=DEFAULT_IMAGE_MODEL, seed=7, steps=4, size=1024, timeout=REQUEST_TIMEOUT_S
):
    """Image edit via /v1/images/edits (multipart); returns PNG bytes."""
    boundary = uuid.uuid4().hex
    fields = {
        "model": model,
        "prompt": prompt,
        "size": f"{size}x{size}",
        "steps": str(steps),
        "cfg_scale": "1.0",
        "seed": str(seed),
        "response_format": "b64_json",
    }
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="image.png"\r\n'
        f"Content-Type: image/png\r\n\r\n".encode()
        + png_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = _call(
        api_url.rstrip("/") + "/v1/images/edits",
        b"".join(parts),
        f"multipart/form-data; boundary={boundary}",
        timeout,
        "the server",
    )
    return base64.b64decode(json.loads(body)["data"][0]["b64_json"])


def request_glb(
    api_url,
    image_path,
    model=DEFAULT_MODEL,
    seed=1234,
    resolution=512,
    bg_removal="auto",
    steps=None,
    timeout=REQUEST_TIMEOUT_S,
):
    """POST the PNG to /v1/3d/generations and return the GLB bytes.

    bg_removal: "auto" (let the server decide; a real alpha mask is kept), "birefnet" or "threshold".
    steps: flow steps per stage (None = the server's default, 8).
    """
    with open(image_path, "rb") as f:
        image = base64.b64encode(f.read()).decode()
    payload = {"model": model, "image": image, "seed": seed, "resolution": resolution}
    if bg_removal != "auto":
        payload["bg_removal"] = bg_removal
    if steps:
        payload["steps"] = steps
    return _call(
        api_url.rstrip("/") + "/v1/3d/generations",
        json.dumps(payload).encode(),
        "application/json",
        timeout,
        "the server",
    )


def matte_image(matte_url, image_path, model="isnet-general-use", timeout=120):
    """Send the image file to the matting server and return RGBA PNG bytes."""
    with open(image_path, "rb") as f:
        data = f.read()
    return _call(
        f"{matte_url.rstrip('/')}/matte?model={model}", data, "application/octet-stream", timeout, "the matting server"
    )


def setup_status(api_url, timeout=10):
    """GET /v1/setup: {"ready", "items", "missing_bytes", "download": {...progress...}}."""
    return json.loads(
        _call(api_url.rstrip("/") + "/v1/setup", None, "application/json", timeout, "the server", method="GET")
    )


def start_setup_download(api_url, timeout=10):
    """POST /v1/setup/download: the server fetches the pinned models in the background."""
    return json.loads(_call(api_url.rstrip("/") + "/v1/setup/download", b"", "application/json", timeout, "the server"))


def _is_id(value):
    return isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value)


def library_models(api_url, limit=200, timeout=10):
    """The finished 3D models in the server's Library, newest first: [{"id", "created", "label", "faces",
    "resolution", "prompt"}]. The prompt is the one of the image job the mesh was made from, when there is one."""
    jobs = json.loads(
        _call(
            f"{api_url.rstrip('/')}/v1/jobs?limit={int(limit)}", None, "application/json", timeout, "the server", "GET"
        )
    )
    prompts = {j["id"]: (j.get("info") or {}).get("prompt") or "" for j in jobs}
    out = []
    for j in jobs:
        if j.get("kind") != "mesh.generate" or j.get("state") != "done" or "model.glb" not in j.get("outputs", []):
            continue
        if not _is_id(j.get("id")):
            continue
        info = j.get("info") or {}
        source = (j.get("params") or {}).get("image") or {}
        prompt = prompts.get(source.get("job") or "", "")
        out.append(
            {
                "id": j["id"],
                "created": float(j.get("created") or 0),
                "faces": int(info.get("faces") or 0),
                "resolution": int(info.get("resolution") or 0),
                "prompt": prompt.split(".")[0][:80],
                "has_input": "input.png" in j.get("outputs", []),
            }
        )
    return out


def job_file(api_url, job_id, name, timeout=REQUEST_TIMEOUT_S):
    """The bytes of one result file of a job (model.glb, input.png, image.png)."""
    if not _is_id(job_id) or name not in ("model.glb", "input.png", "image.png"):
        raise RuntimeError("invalid job id or file name")
    return _call(f"{api_url.rstrip('/')}/v1/jobs/{job_id}/files/{name}", None, "application/octet-stream", timeout,
                 "the server", "GET")  # fmt: skip
