"""Server API (server/app) with fake CLIs: jobs, validation, uploads, compat endpoints, auth, config, add-on."""

import base64
import io
import json
import os
import time
import zipfile

import pytest
from conftest import png_bytes, wait_job

from app.pipelines.base import Pipeline
from app.schemas import JobProgress


def upload(client, data=None, name="in.png"):
    r = client.post("/v1/uploads", files={"file": (name, data or png_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def run(client, kind, params):
    r = client.post("/v1/jobs", json={"kind": kind, "params": params})
    assert r.status_code == 202, r.text
    return wait_job(client, r.json()["id"])


# ---------------------------------------------------------------- pipelines and jobs


def test_every_pipeline_has_a_job_request_model():
    from typing import get_args

    from app.pipelines import PIPELINES, JobRequest

    union = JobRequest.model_fields["root"].annotation  # pydantic keeps the union, the discriminator moves to metadata
    requests = {get_args(m.model_fields["kind"].annotation)[0]: m for m in get_args(union)}
    assert set(requests) == set(PIPELINES)
    for kind, model in requests.items():
        assert model.model_fields["params"].annotation is PIPELINES[kind].Params


def test_unknown_kind_is_refused(server_env):
    c, _ = server_env
    assert c.post("/v1/jobs", json={"kind": "rm.rf", "params": {}}).status_code == 422


def test_pipelines_expose_their_parameter_schemas(server_env):
    c, _ = server_env
    kinds = {p["kind"]: p for p in c.get("/v1/pipelines").json()}
    assert set(kinds) == {"image.generate", "image.edit", "image.matte", "mesh.generate", "model.check"}
    assert kinds["mesh.generate"]["params"]["properties"]["resolution"]
    assert kinds["image.matte"]["uses_gpu"] is False


def test_generate_image_composes_the_framing_and_uses_the_default_steps(server_env):
    c, calls = server_env
    job = run(c, "image.generate", {"prompt": "a red retro toaster", "framing": {"subject": "object"}})
    assert job["state"] == "done" and job["outputs"] == ["image.png"]
    argv = calls()[-1]
    prompt = argv[argv.index("-p") + 1]
    assert prompt.startswith("a red retro toaster. A single object") and prompt.endswith("no logo.")
    assert argv[argv.index("--steps") + 1] == "4"
    assert 0 <= job["info"]["seed"] < 2**31 and job["info"]["prompt"] == prompt
    assert job["progress"]["stage"] == "Denoising" and job["progress"]["step"] == 2
    r = c.get(f"/v1/jobs/{job['id']}/files/image.png")
    assert r.status_code == 200 and r.content.startswith(b"\x89PNG")


@pytest.mark.parametrize(
    "params",
    [
        {"prompt": "a cat", "width": 1000},  # not a multiple of 16
        {"prompt": "a cat", "width": 4096},
        {"prompt": "a cat\x00"},
        {"prompt": ""},
        {"prompt": "a cat", "steps": 0},
        {"prompt": "a cat", "unexpected": 1},
        {"prompt": "a cat", "framing": {"subject": "planet"}},
    ],
)
def test_generate_rejects_bad_params_before_queueing(server_env, params):
    c, calls = server_env
    assert c.post("/v1/jobs", json={"kind": "image.generate", "params": params}).status_code == 422
    assert calls() == []


def test_edit_uses_an_earlier_result_as_reference(server_env):
    c, calls = server_env
    first = run(c, "image.generate", {"prompt": "a cat", "framing": None, "seed": 5})
    job = run(c, "image.edit", {"image": {"job": first["id"], "file": "image.png"}, "preset": "a_pose", "seed": 7})
    argv = calls()[-1]
    assert job["state"] == "done"
    assert argv[argv.index("-r") + 1].endswith(f"{first['id']}/image.png")
    assert argv[argv.index("-p") + 1].startswith("Change only the pose")


def test_edit_custom_needs_a_prompt(server_env):
    c, _ = server_env
    uid = upload(c)
    r = c.post("/v1/jobs", json={"kind": "image.edit", "params": {"image": {"upload": uid}, "preset": "custom"}})
    assert r.status_code == 422


def test_mesh_passes_every_option_and_reports_faces(server_env):
    c, calls = server_env
    uid = upload(c, png_bytes("RGBA"))
    params = {"image": {"upload": uid}, "matting": "none", "resolution": 1024, "steps": 6, "seed": 3}
    params.update(texture=False, atlas=2048, structure_guidance=5.5, shape_guidance=3.0, max_tokens=20000)
    job = run(c, "mesh.generate", params)
    assert job["state"] == "done", job
    argv = calls()[-1]
    for flag, value in (("--res", "1024"), ("--steps", "6"), ("--seed", "3"), ("--atlas", "2048")):
        assert argv[argv.index(flag) + 1] == value
    assert argv.count("--steps") == 1 and "--no-texture" in argv
    assert argv[argv.index("--gss") + 1] == "5.5" and argv[argv.index("--max-tokens") + 1] == "20000"
    assert job["info"]["faces"] == 1234 and job["outputs"] == ["model.glb", "input.png"]
    assert c.get(f"/v1/jobs/{job['id']}/files/model.glb").content == b"glTF"


def test_mesh_auto_matting_removes_an_opaque_background(server_env, monkeypatch):
    c, _ = server_env
    called = []
    monkeypatch.setattr("app.pipelines.trellis.matte", lambda path, model, fill: called.append(model) or png_bytes())
    job = run(c, "mesh.generate", {"image": {"upload": upload(c)}, "matting": "auto"})
    assert job["state"] == "done" and called == ["isnet-general-use"] and job["info"]["matted"] is True


def test_missing_reference_is_refused_at_submit(server_env):
    c, _ = server_env
    r = c.post("/v1/jobs", json={"kind": "mesh.generate", "params": {"image": {"upload": "0" * 32}}})
    assert r.status_code == 404


def test_jobs_wait_for_the_models_but_cpu_tools_do_not(server_env, monkeypatch):
    c, _ = server_env
    from app import model_setup

    monkeypatch.setattr(
        model_setup, "status", lambda m=None: model_setup.ModelStatus(ready=False, items=[], missing_bytes=1)
    )
    assert c.post("/v1/jobs", json={"kind": "image.generate", "params": {"prompt": "x"}}).status_code == 503
    monkeypatch.setattr("app.pipelines.matte.matte", lambda *a: png_bytes("RGBA"))
    job = run(c, "image.matte", {"image": {"upload": upload(c)}})
    assert job["state"] == "done"


def test_cancel_a_running_job(server_env, monkeypatch):
    c, _ = server_env
    monkeypatch.setenv("FAKE_SLEEP", "5")
    jid = c.post("/v1/jobs", json={"kind": "image.generate", "params": {"prompt": "x"}}).json()["id"]
    for _ in range(100):
        if c.get(f"/v1/jobs/{jid}").json()["state"] == "running":
            break
        time.sleep(0.05)
    assert c.post(f"/v1/jobs/{jid}/cancel").status_code == 200
    assert wait_job(c, jid)["state"] == "cancelled"


def test_failing_cli_marks_the_job_failed(server_env, monkeypatch):
    c, _ = server_env
    monkeypatch.setenv("FAKE_RC", "3")
    job = run(c, "image.generate", {"prompt": "x"})
    assert job["state"] == "failed" and "rc=3" in job["error"]


def test_delete_a_finished_job(server_env):
    c, _ = server_env
    job = run(c, "image.generate", {"prompt": "x"})
    assert c.delete(f"/v1/jobs/{job['id']}").status_code == 204
    assert c.get(f"/v1/jobs/{job['id']}").status_code == 404


@pytest.mark.parametrize("name", ["../job.json", "job.json", "x.exe", "a/b.png"])
def test_job_files_only_by_safe_names(server_env, name):
    c, _ = server_env
    job = run(c, "image.generate", {"prompt": "x"})
    assert c.get(f"/v1/jobs/{job['id']}/files/{name}").status_code in (400, 404)


def test_uploads_check_the_type(server_env):
    c, _ = server_env
    assert c.post("/v1/uploads", files={"file": ("x.png", b"#!/bin/sh\nrm -rf /")}).status_code == 400
    uid = upload(c)
    assert c.get(f"/v1/uploads/{uid}").content.startswith(b"\x89PNG")
    assert c.get("/v1/uploads/../../etc/passwd").status_code == 404


def test_flux_progress_separates_denoising_from_vae_tiles():
    from app.pipelines.flux import ImageGenerate

    p = JobProgress(denoise_steps=4, stages=3)
    ImageGenerate().parse_progress("  |=====>    | 2/4 - 10.0s/it", p)
    assert p.stage == "Denoising" and p.estimate() == pytest.approx((1 + 0.5) / 3)
    ImageGenerate().parse_progress("  |==>       | 12/49 - 2.6it/s", p)
    assert p.stage == "Decoding the image" and p.steps == 49


def test_progress_parsing():
    p = JobProgress()
    pipeline: Pipeline[JobProgress] = Pipeline()
    pipeline.parse_progress("[4/7] shape SLAT flow (512)", p)
    pipeline.parse_progress("      [flow] [####....]  4/8   10.0s", p)
    assert p.stage == "Shape SLAT flow (512)" and p.step == 4
    assert p.estimate() == pytest.approx((3 + 0.5) / 7)
    pipeline.parse_progress("[1/6] preprocess /data/jobs/abc/input.png (512)", p)
    assert p.stage == "Preprocess (512)"


# ---------------------------------------------------------------- add-on compatible endpoints


def test_compat_text_to_image_returns_b64_png(server_env):
    c, calls = server_env
    r = c.post("/v1/images/generations", json={"prompt": "a cat", "size": "768x1024", "steps": 3, "model": "x"})
    assert r.status_code == 200
    assert base64.b64decode(r.json()["data"][0]["b64_json"]).startswith(b"\x89PNG")
    argv = calls()[-1]
    assert argv[argv.index("-p") + 1] == "a cat"  # the add-on composes its own prompt
    assert argv[argv.index("-W") + 1] == "768"


def test_compat_edit_and_mesh(server_env):
    c, calls = server_env
    r = c.post("/v1/images/edits", data={"prompt": "A-pose", "steps": "3"}, files={"image": ("i.png", png_bytes())})
    assert r.status_code == 200 and "-r" in calls()[-1]
    img = base64.b64encode(png_bytes("RGBA")).decode()
    r = c.post("/v1/3d/generations", json={"image": img, "resolution": 512, "steps": 6, "seed": 1})
    assert r.status_code == 200 and r.content == b"glTF"
    jpeg = io.BytesIO()
    from PIL import Image

    Image.new("RGB", (4, 4)).save(jpeg, "JPEG")
    bad = c.post("/v1/3d/generations", json={"image": base64.b64encode(jpeg.getvalue()).decode()})
    assert bad.status_code == 400


# ---------------------------------------------------------------- security, config, add-on, system


def test_token_protects_the_api_but_not_the_ui(server_env, monkeypatch):
    c, _ = server_env
    monkeypatch.setenv("SERVER_TOKEN", "s3cret")
    assert c.get("/health").status_code == 200
    assert c.get("/").status_code == 200
    assert c.get("/v1/system").status_code == 401
    assert c.get("/v1/system", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/v1/system", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_security_headers_everywhere(server_env):
    c, _ = server_env
    for path in ("/", "/v1/system", "/app.js"):
        csp = c.get(path).headers["content-security-policy"]
        assert "script-src 'self' 'wasm-unsafe-eval';" in csp and "frame-ancestors 'none'" in csp
        assert "unsafe-eval'" not in csp.replace("'wasm-unsafe-eval'", "")  # JavaScript eval stays blocked


def test_oversized_body_is_refused(server_env):
    c, _ = server_env
    r = c.post("/v1/jobs", content=b"{}", headers={"Content-Length": str(48 * 2**20 + 1)})
    assert r.status_code == 413


def test_config_validates_and_persists(server_env, tmp_path):
    c, _ = server_env
    assert c.get("/v1/config").json()["mesh_steps"] == 8
    assert c.put("/v1/config", json={"mesh_resolution": 700}).status_code == 422
    assert c.put("/v1/config", json={"shell": "rm -rf /"}).status_code == 422
    assert c.put("/v1/config", json={"mesh_steps": 6}).json()["mesh_steps"] == 6
    assert json.loads((tmp_path / "data/config.json").read_text())["mesh_steps"] == 6
    assert "mesh_steps" in c.get("/v1/config/schema").json()["properties"]


def test_addon_zip_is_the_package(server_env):
    c, _ = server_env
    info = c.get("/v1/addon").json()
    r = c.get(info["download"])
    assert r.status_code == 200 and info["version"] in r.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "local_producer/__init__.py" in names and "local_producer/blender_manifest.toml" in names
    assert not any(n.endswith(("_raw.png", ".pyc")) for n in names)
    assert c.get(info["download"]).content == r.content  # reproducible: Blender checks the hash


def test_addon_is_an_extension_repository(server_env):
    import hashlib

    c, _ = server_env
    info = c.get("/v1/addon").json()
    index = c.get(info["repository"]).json()
    assert index["version"] == "v1" and len(index["data"]) == 1
    entry = index["data"][0]
    data = c.get(info["download"]).content
    assert entry["archive_url"] == "./" + info["download"].rsplit("/", 1)[1]
    assert entry["archive_hash"] == "sha256:" + hashlib.sha256(data).hexdigest()
    assert entry["archive_size"] == len(data) and entry["license"] == ["SPDX:GPL-3.0-or-later"]
    assert "build" not in entry
    assert c.get("/blender/local_producer-0.0.1.zip").status_code == 404


def test_addon_manifest_version_matches_bl_info():
    import ast
    import pathlib
    import tomllib

    root = pathlib.Path(__file__).resolve().parents[1] / "blender/local_producer"
    version = tomllib.loads((root / "blender_manifest.toml").read_text())["version"]
    tree = ast.parse((root / "__init__.py").read_text())
    bl_info = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "bl_info")
    assert ".".join(map(str, ast.literal_eval(bl_info.value)["version"])) == version


def test_system_and_logs(server_env):
    c, _ = server_env
    run(c, "image.generate", {"prompt": "x"})
    s = c.get("/v1/system").json()
    assert s["models_ready"] is True and s["jobs_running"] == 0
    lines = c.get("/v1/logs?lines=50").json()["lines"]
    assert any("[Info] (Process)" in line for line in lines)
    assert c.get("/v1/prompts/framing").json()["apose_prompt"].startswith("Change only the pose")


def test_logs_follow_by_offset(server_env):
    c, _ = server_env
    from app.settings import paths

    os.unlink(paths.log)  # written when the fixture loaded the engine
    assert c.get("/v1/logs").json() == {"lines": [], "offset": 0, "reset": True}  # no log yet
    os.makedirs(paths.data, exist_ok=True)
    with open(paths.log, "w") as f:
        f.write("earlier\n")
    first = c.get("/v1/logs?lines=5").json()
    assert first["reset"] is True and first["offset"] == os.path.getsize(paths.log)
    with open(paths.log, "a") as f:
        f.write("line one\nline two\npartial")
    more = c.get(f"/v1/logs?since={first['offset']}").json()
    assert more == {"lines": ["line one\n", "line two\n"], "offset": first["offset"] + 18, "reset": False}
    with open(paths.log, "a") as f:
        f.write(" line\n")
    assert c.get(f"/v1/logs?since={more['offset']}").json()["lines"] == ["partial line\n"]
    # a truncated log (or an offset from another server) starts over with a tail
    assert c.get("/v1/logs?since=99999999").json()["reset"] is True
