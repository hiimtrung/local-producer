"""HTTP client for the local-producer GPU server and matting server. No bpy: unit-tested outside Blender.

All calls raise RuntimeError with a short message on failure. If the server was started with SERVER_TOKEN, put the
token into `auth["token"]` (the add-on copies its "Server Token" preference there before each job).
"""

import json
import time
import urllib.error
import urllib.request
import uuid

REQUEST_TIMEOUT_S = 3600  # res 512 takes ~4-5 min on the Radeon 780M, res 1024 ~19 min (raise for 1536: ~53 min)
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


def _json(api_url, path, payload=None, timeout=10, method="POST"):
    data = None if payload is None else json.dumps(payload).encode()
    return json.loads(_call(api_url.rstrip("/") + path, data, "application/json", timeout, "the server", method))


def _upload(api_url, png_bytes, timeout=60):
    """POST /v1/uploads (multipart); returns the upload id."""
    boundary = uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="image.png"\r\n'
        f"Content-Type: image/png\r\n\r\n".encode()
        + png_bytes
        + f"\r\n--{boundary}--\r\n".encode()
    )
    ctype = f"multipart/form-data; boundary={boundary}"
    reply = _call(api_url.rstrip("/") + "/v1/uploads", body, ctype, timeout, "the server")
    return json.loads(reply)["id"]


def run_job(api_url, kind, params, output, timeout=REQUEST_TIMEOUT_S, poll_s=1.0):
    """Queue a job (POST /v1/jobs), wait until it has finished (GET /v1/jobs/<id>), return the bytes of `output`."""
    job = _json(api_url, "/v1/jobs", {"kind": kind, "params": params})
    deadline = time.monotonic() + timeout
    while job["state"] in ("queued", "running"):
        if time.monotonic() > deadline:
            raise RuntimeError(f"{kind} did not finish within {timeout} s")
        time.sleep(poll_s)
        job = _json(api_url, f"/v1/jobs/{job['id']}", method="GET")
    if job["state"] != "done":
        raise RuntimeError(f"{kind} {job['state']}: {job.get('error') or 'no detail'}")
    return job_file(api_url, job["id"], output)


def request_image(api_url, prompt, seed=7, steps=4, size=1024, timeout=REQUEST_TIMEOUT_S):
    """Text-to-image (pipeline image.generate); returns PNG bytes."""
    params = {"prompt": prompt, "framing": None, "width": size, "height": size, "steps": steps, "seed": seed}
    return run_job(api_url, "image.generate", params, "image.png", timeout)


def request_edit(api_url, png_bytes, prompt, seed=7, steps=4, size=1024, timeout=REQUEST_TIMEOUT_S):
    """Image edit with a free instruction (pipeline image.edit); returns PNG bytes."""
    params = {
        "image": {"upload": _upload(api_url, png_bytes)},
        "preset": "custom",
        "prompt": prompt,
        "width": size,
        "height": size,
        "steps": steps,
        "seed": seed,
    }
    return run_job(api_url, "image.edit", params, "image.png", timeout)


def request_glb(api_url, image_path, seed=1234, resolution=512, matting="none", steps=None, timeout=REQUEST_TIMEOUT_S):
    """Image to textured mesh (pipeline mesh.generate); returns the GLB bytes.

    matting: "none" (the image is used as sent, e.g. already cut out by the matting server) or "auto" (the server
    removes the background unless the image has transparency).
    steps: flow steps per stage (None = the server's default, 8).
    """
    with open(image_path, "rb") as f:
        upload = _upload(api_url, f.read())
    params = {"image": {"upload": upload}, "matting": matting, "resolution": resolution, "seed": seed, "steps": steps}
    return run_job(api_url, "mesh.generate", params, "model.glb", timeout)


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
