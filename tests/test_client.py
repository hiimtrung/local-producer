"""HTTP client of the Blender add-on (blender/local_producer/client.py) against a local stub server."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import client


@pytest.fixture
def stub():
    """A local HTTP server that records requests and answers with canned responses."""
    seen = []

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
            self._reply(200, json.dumps({"ready": True, "items": [], "missing_bytes": 0, "download": {}}).encode())

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            seen.append({"path": self.path, "headers": dict(self.headers), "body": body})
            if self.path == "/v1/3d/generations":
                self._reply(200, b"glTF-binary", "model/gltf-binary")
            elif self.path == "/v1/images/generations":
                self._reply(200, json.dumps({"data": [{"b64_json": base64.b64encode(b"PNG").decode()}]}).encode())
            else:
                self._reply(503, b'{"detail": "models are missing"}')

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", seen
    srv.shutdown()
    client.auth["token"] = ""


def test_request_glb_sends_steps_and_skips_auto_bg_removal(stub, tmp_path):
    url, seen = stub
    img = tmp_path / "in.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    assert client.request_glb(url, str(img), seed=5, resolution=1024, steps=6) == b"glTF-binary"
    payload = json.loads(seen[-1]["body"])
    assert payload["steps"] == 6 and payload["resolution"] == 1024 and payload["seed"] == 5
    assert "bg_removal" not in payload
    assert base64.b64decode(payload["image"]).startswith(b"\x89PNG")


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
