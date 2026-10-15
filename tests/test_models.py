"""User models (server/app/model_store.py, routes/models.py, pipelines/check.py): safe downloads, header checks,
Hugging Face pinning, uploads, tests with the engine, and jobs that pick a model. No network: DNS and HTTP are fakes."""

import functools
import http.server
import json
import struct
import threading

import pytest
from conftest import wait_job
from test_model_setup import FakeOpener, sha

from app import model_store
from app.model_setup import SetupError
from app.model_store import AddModel

GGUF = b"GGUF" + b"\0" * 60
REPO = "leejet/FLUX.2-klein-4B-GGUF"
COMMIT = "3b1f5a9dc3abb32238b053aeb3d823c30afdacbd"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/m.gguf",
        "http://example.org/m.gguf",
        "https://127.0.0.1:8080/m.gguf",
        "http://192.168.1.2/m.gguf",
    ],
)
def test_any_http_link_is_accepted_also_on_this_machine_or_the_lan(url):
    model_store.check_link(url)  # the user's own server, the user's responsibility (SECURITY.md)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.org/m.gguf", "huggingface.co/x/y", "https://"])
def test_other_schemes_are_refused(url):
    with pytest.raises(SetupError, match="http"):
        model_store.check_link(url)


def test_a_model_from_a_server_on_this_machine(server_env, tmp_path):
    """End to end over real HTTP: a plain http server on 127.0.0.1 serves the weights."""
    (tmp_path / "www").mkdir()
    (tmp_path / "www" / "local.gguf").write_bytes(GGUF)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path / "www"))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_port}/local.gguf"
        info = model_store.store.add_from_url(AddModel(family="flux2-klein", title="Local", url=url))
    finally:
        srv.shutdown()
    assert info.source == url and info.size == len(GGUF)


def test_weights_are_checked_by_their_header(tmp_path):
    good = tmp_path / "a.gguf"
    good.write_bytes(GGUF)
    model_store.check_weights(str(good))
    header = b'{"__metadata__":{}}'
    st = tmp_path / "b.safetensors"
    st.write_bytes(struct.pack("<Q", len(header)) + header)
    model_store.check_weights(str(st))
    for name, data in (("c.gguf", b"PK\x03\x04zip"), ("d.safetensors", b"\x80\x04pickle")):
        bad = tmp_path / name
        bad.write_bytes(data)
        with pytest.raises(SetupError, match="not a valid"):
            model_store.check_weights(str(bad))


def hf_fake(files):
    """A fake Hugging Face: the revision and tree APIs plus the resolve URLs of `files` {path: bytes}."""
    tree = [{"type": "file", "path": p, "size": len(d), "lfs": {"oid": sha(d)}} for p, d in files.items()]
    urls = {f"https://huggingface.co/api/models/{REPO}/revision/main": json.dumps({"sha": COMMIT}).encode()}
    folders = {p.rsplit("/", 1)[0] if "/" in p else "" for p in files}
    for folder in folders:
        listing = [e for e in tree if (e["path"].rsplit("/", 1)[0] if "/" in e["path"] else "") == folder]
        urls[f"https://huggingface.co/api/models/{REPO}/tree/{COMMIT}/{folder}".rstrip("/")] = json.dumps(
            listing
        ).encode()
    for p, d in files.items():
        urls[f"https://huggingface.co/{REPO}/resolve/{COMMIT}/{p}"] = d
    return FakeOpener(urls)


def test_a_hugging_face_file_is_pinned_and_verified(server_env, monkeypatch):
    opener = hf_fake({"flux-2-klein-4b-Q4_0.gguf": GGUF})
    req = AddModel(
        family="flux2-klein",
        title="Klein Q4_0",
        url=f"https://huggingface.co/{REPO}/blob/main/flux-2-klein-4b-Q4_0.gguf",
    )
    info = model_store.store.add_from_url(req, opener=opener)
    assert info.source == f"Hugging Face {REPO}@{COMMIT[:12]}/flux-2-klein-4b-Q4_0.gguf"
    assert info.files == {"diffusion": f"user/{info.id}/flux-2-klein-4b-Q4_0.gguf"}
    c, _ = server_env
    listed = {m["id"]: m for m in c.get("/v1/models").json()["models"]}
    assert listed[info.id]["present"] and not listed[info.id]["builtin"]
    assert listed["flux2-klein-4b-q8_0"]["builtin"]


def test_a_tampered_hugging_face_download_is_rejected(server_env, monkeypatch):
    opener = hf_fake({"x.gguf": GGUF})
    opener.files[f"https://huggingface.co/{REPO}/resolve/{COMMIT}/x.gguf"] = b"GGUF" + b"\1" * 60
    req = AddModel(family="flux2-klein", title="X", url=f"https://huggingface.co/{REPO}/resolve/main/x.gguf")
    with pytest.raises(SetupError, match="verification failed"):
        model_store.store.add_from_url(req, opener=opener)
    assert [m.id for m in model_store.store.all() if not m.builtin] == []


def test_a_trellis_folder_needs_the_whole_set(server_env, monkeypatch):
    files = {f"q8/{n}": GGUF for n in model_store.TRELLIS_FILES}
    url = f"https://huggingface.co/{REPO}/tree/main/q8"
    info = model_store.store.add_from_url(AddModel(family="trellis2", title="T q8", url=url), opener=hf_fake(files))
    assert info.files == {"dir": f"user/{info.id}"}
    del files["q8/dinov3.gguf"]
    with pytest.raises(SetupError, match="lacks dinov3.gguf"):
        model_store.store.add_from_url(AddModel(family="trellis2", title="T", url=url), opener=hf_fake(files))


def test_upload_then_test_then_generate_with_the_model(server_env):
    c, calls = server_env
    r = c.put("/v1/models/upload?family=flux2-klein&title=Mine&filename=mine.gguf", content=GGUF)
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    bad = c.put("/v1/models/upload?family=flux2-klein&title=Bad&filename=bad.gguf", content=b"MZ\x90")
    assert bad.status_code == 422
    assert c.put("/v1/models/upload?family=trellis2&title=T&filename=t.gguf", content=GGUF).status_code == 422

    job = wait_job(c, c.post(f"/v1/models/{mid}/check").json()["id"])
    assert job["state"] == "done" and job["outputs"] == ["image.png"]
    argv = calls()[-1]
    assert argv[argv.index("--diffusion-model") + 1].endswith(f"user/{mid}/mine.gguf")
    assert argv[argv.index("--llm") + 1].endswith("flux2/qwen_3_4b-q8_0.gguf")  # the built-in text encoder
    model = next(m for m in c.get("/v1/models").json()["models"] if m["id"] == mid)
    assert model["check"]["state"] == "ok" and model["check"]["engine"] == "rocm-gfx1103 2026.10.15"

    r = c.post("/v1/jobs", json={"kind": "image.generate", "params": {"prompt": "a cat", "model": mid}})
    job = wait_job(c, r.json()["id"])
    assert job["state"] == "done" and job["info"]["model"] == mid
    assert (
        c.post("/v1/jobs", json={"kind": "image.generate", "params": {"prompt": "a", "model": "nope"}}).status_code
        == 400
    )
    assert c.delete("/v1/models/flux2-klein-4b-q8_0").status_code == 409  # built in
    assert c.delete(f"/v1/models/{mid}").status_code == 204
    assert all(m["id"] != mid for m in c.get("/v1/models").json()["models"])


def test_a_failed_test_is_recorded_and_blocks_jobs(server_env, monkeypatch):
    c, _ = server_env
    mid = c.put("/v1/models/upload?family=flux2-klein&title=Broken&filename=b.gguf", content=GGUF).json()["id"]
    monkeypatch.setenv("FAKE_RC", "3")
    job = wait_job(c, c.post(f"/v1/models/{mid}/check").json()["id"])
    assert job["state"] == "failed"
    check = next(m for m in c.get("/v1/models").json()["models"] if m["id"] == mid)["check"]
    assert check["state"] == "failed" and "rc=3" in check["message"]
    r = c.post("/v1/jobs", json={"kind": "image.generate", "params": {"prompt": "a", "model": mid}})
    assert r.status_code == 409 and "failed its test" in r.json()["detail"]


def test_a_trellis_model_test_makes_a_draft_mesh(server_env):
    c, calls = server_env
    job = wait_job(c, c.post("/v1/models/trellis2-f16/check").json()["id"])
    assert job["state"] == "done" and job["outputs"] == ["model.glb", "input.png"]
    argv = calls()[-1]
    assert argv[argv.index("--steps") + 1] == "1" and "--no-texture" in argv


def test_suggestions_are_marked_once_added_and_errors_can_be_dismissed(server_env, monkeypatch):
    c, _ = server_env
    sug = c.get("/v1/models").json()["suggestions"]
    assert {s["family"] for s in sug} == {"flux2-klein", "trellis2"} and not any(s["added"] for s in sug)
    q4 = next(s for s in sug if s["url"].endswith("flux-2-klein-4b-Q4_0.gguf"))
    path = "flux-2-klein-4b-Q4_0.gguf"
    model_store.store.add_from_url(
        AddModel(family="flux2-klein", title="Q4", url=q4["url"]), opener=hf_fake({path: GGUF})
    )
    sug = {s["url"]: s for s in c.get("/v1/models").json()["suggestions"]}
    assert sug[q4["url"]]["added"] and sum(s["added"] for s in sug.values()) == 1

    with pytest.raises(SetupError):
        model_store.store.add_from_url(AddModel(family="flux2-klein", title="x", url="https://example.org/x.bin"))
    assert ".gguf" in c.get("/v1/models").json()["adding"]["error"]
    assert c.delete("/v1/models/adding").status_code == 204
    assert c.get("/v1/models").json()["adding"]["error"] == ""


def test_a_cross_site_page_cannot_add_a_model(server_env):
    """A form or fetch without a preflight can only send text/plain: refused. The JSON preflight is never granted."""
    c, _ = server_env
    body = '{"family": "flux2-klein", "title": "x", "url": "http://127.0.0.1:9/x.gguf"}'
    r = c.post("/v1/models", content=body, headers={"Content-Type": "text/plain", "Origin": "https://evil.example"})
    assert r.status_code == 422 and "access-control-allow-origin" not in r.headers
    pre = c.options("/v1/models", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in pre.headers
    assert not c.get("/v1/models").json()["adding"]["running"]
