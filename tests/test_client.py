"""HTTP client of the Blender add-on (blender/local_producer/client.py) against a local stub server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import client

JOB = "d" * 32
UPLOAD = "e" * 32


@pytest.fixture
def stub(monkeypatch):
    """A local HTTP server that records requests and plays the server's job API: queued, then running, then done."""
    seen = []
    polls = {"n": 0}
    monkeypatch.setattr(client.time, "sleep", lambda s: None)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _reply(self, code, body, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            seen.append({"path": self.path, "headers": dict(self.headers), "body": b""})
            if self.path == f"/v1/jobs/{JOB}":
                polls["n"] += 1
                state = "done" if polls["n"] > 1 else "running"
                self._reply(200, json.dumps({"id": JOB, "state": state, "error": None}).encode())
            elif self.path.endswith("/files/model.glb"):
                self._reply(200, b"glTF-binary", "model/gltf-binary")
            elif self.path.endswith("/files/image.png"):
                self._reply(200, b"PNG", "image/png")
            else:
                self._reply(200, json.dumps({"ready": True, "items": [], "missing_bytes": 0, "download": {}}).encode())

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            seen.append({"path": self.path, "headers": dict(self.headers), "body": body})
            if self.path == "/v1/uploads":
                self._reply(
                    200, json.dumps({"id": UPLOAD, "type": "png", "size": len(body), "name": "image.png"}).encode()
                )
            elif self.path == "/v1/jobs":
                self._reply(202, json.dumps({"id": JOB, "state": "queued", "error": None}).encode())
            else:
                self._reply(503, b'{"detail": "models are missing"}')

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", seen
    srv.shutdown()
    client.auth["token"] = ""


def _job_body(seen):
    return next(json.loads(r["body"]) for r in seen if r["path"] == "/v1/jobs")


def test_request_glb_uploads_the_image_and_queues_a_mesh_job(stub, tmp_path):
    url, seen = stub
    img = tmp_path / "in.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    assert client.request_glb(url, str(img), seed=5, resolution=1024, steps=6) == b"glTF-binary"
    body = _job_body(seen)
    assert body["kind"] == "mesh.generate"
    assert body["params"] == {
        "image": {"upload": UPLOAD}, "matting": "none", "resolution": 1024, "seed": 5, "steps": 6,
    }  # fmt: skip
    assert any(b"fake" in r["body"] for r in seen if r["path"] == "/v1/uploads")


def test_request_edit_sends_the_instruction(stub):
    url, seen = stub
    assert client.request_edit(url, b"\x89PNG", "A-pose", seed=3, steps=4) == b"PNG"
    body = _job_body(seen)
    assert body["kind"] == "image.edit" and body["params"]["preset"] == "custom"
    assert body["params"]["prompt"] == "A-pose" and body["params"]["image"] == {"upload": UPLOAD}


def test_a_failed_job_raises_with_the_server_error(stub, monkeypatch):
    url, _ = stub
    monkeypatch.setattr(client, "job_file", lambda *a, **k: b"")
    real = client._json

    def failing(api_url, path, payload=None, timeout=10, method="POST"):
        job = real(api_url, path, payload, timeout, method)
        return {**job, "state": "failed", "error": "out of memory"} if method == "GET" else job

    monkeypatch.setattr(client, "_json", failing)
    with pytest.raises(RuntimeError, match="image.generate failed: out of memory"):
        client.request_image(url, "a cat")


def test_token_is_sent_as_bearer(stub):
    url, seen = stub
    client.auth["token"] = "s3cret"
    assert client.request_image(url, "a cat") == b"PNG"
    assert seen[-1]["headers"]["Authorization"] == "Bearer s3cret"


def test_no_token_no_header(stub):
    url, seen = stub
    client.setup_status(url)
    assert "Authorization" not in seen[-1]["headers"]


def test_http_error_becomes_runtime_error_with_the_detail(stub):
    url, _ = stub
    with pytest.raises(RuntimeError, match="503.*models are missing"):
        client.start_setup_download(url)


def test_unreachable_server_is_a_runtime_error():
    with pytest.raises(RuntimeError, match="cannot reach"):
        client.setup_status("http://127.0.0.1:9", timeout=2)


def test_library_lists_finished_3d_models_with_their_prompt(monkeypatch):
    img, mesh, failed = "a" * 32, "b" * 32, "c" * 32
    jobs = [
        {"id": failed, "kind": "mesh.generate", "state": "failed", "outputs": [], "created": 3},
        {
            "id": mesh, "kind": "mesh.generate", "state": "done", "outputs": ["model.glb", "input.png"], "created": 2,
            "info": {"faces": 1234, "resolution": 512}, "params": {"image": {"job": img, "file": "image.png"}},
        },
        {"id": img, "kind": "image.generate", "state": "done", "outputs": ["image.png"], "created": 1,
         "info": {"prompt": "a cute cat. Full body, centered"}},
    ]  # fmt: skip
    calls = []

    def fake_call(url, data, ctype, timeout, what, method="POST"):
        calls.append((method, url))
        return json.dumps(jobs).encode() if "/v1/jobs?" in url else b"glTF"

    monkeypatch.setattr(client, "_call", fake_call)
    models = client.library_models("http://x")
    assert [m["id"] for m in models] == [mesh]
    assert models[0]["prompt"] == "a cute cat" and models[0]["faces"] == 1234
    assert client.job_file("http://x", mesh, "model.glb") == b"glTF"
    assert calls[-1] == ("GET", f"http://x/v1/jobs/{mesh}/files/model.glb")
    with pytest.raises(RuntimeError, match="invalid"):
        client.job_file("http://x", "../etc", "model.glb")
