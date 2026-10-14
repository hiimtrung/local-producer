"""Shared fixtures: a server app wired to temporary directories and an engine package whose sd-cli / trellis-cli are
fakes."""

import io
import json
import stat
import textwrap
import time

import pytest
from PIL import Image

FAKE_CLI = textwrap.dedent("""\
    #!/usr/bin/env python3
    # Stands in for sd-cli / trellis-cli: records argv, prints progress like the real tools, writes the outputs.
    import json, os, sys, time
    if sys.argv[1:] in (["--version"], ["--help"]):  # the engine self-test
        sys.exit(int(os.environ.get("FAKE_SELF_TEST_RC", "0")))
    with open(os.environ["FAKE_ARGV_LOG"], "a") as f:
        f.write(json.dumps(sys.argv) + "\\n")
    a = sys.argv
    time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
    if "--output" in a:  # trellis-cli
        out = a[a.index("--output") + 1]
        print("[3/6] sparse-structure flow + decode", flush=True)
        print("      [flow] [####....]  4/8   10.0s  ~10s left", flush=True)
        print("  decimate_qem_gpu(target=150000): V 10->5, F 20->1234", flush=True)
        for name, data in ((out, b"glTF"), (out[:-4] + ".ply", b"ply"), (out[:-4] + "_base.png", b"png")):
            open(name, "wb").write(data)
    else:  # sd-cli
        out = a[a.index("-o") + 1]
        print("  |=========>          | 2/4 - 10.0s/it", flush=True)
        open(out, "wb").write(bytes.fromhex(os.environ["FAKE_PNG_HEX"]))
    sys.exit(int(os.environ.get("FAKE_RC", "0")))
""")


def png_bytes(mode="RGB", size=(8, 8)):
    buf = io.BytesIO()
    Image.new(mode, size, (128, 128, 128, 255) if mode == "RGBA" else (128, 128, 128)).save(buf, "PNG")
    return buf.getvalue()


def install_fake_engine(engines_dir, version="2026.10.15"):
    """The catalog's ROCm package as if installed, its runners replaced by FAKE_CLI. Returns its directory."""
    from app.engines.catalog import load_catalog

    spec = load_catalog().find("rocm-gfx1103")
    root = engines_dir / spec.id / version
    for runner in spec.runners.values():
        exe = root / runner.bin
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text(FAKE_CLI)
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    dump = spec.model_dump() | {"version": version}
    (root / "package.json").write_text(json.dumps({"spec": dump, "size": 1, "installed_at": time.time()}))
    return root


def install_fake_builtin_models(models_dir):
    """Placeholder files at every path of catalog/models.json, so the built-in models count as present."""
    from app import model_setup

    for it in model_setup.load_manifest()["items"]:
        p = models_dir / it["dest"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"GGUF")


@pytest.fixture
def fake_host(monkeypatch):
    """This machine as the ROCm package expects it, with the preflight passing."""
    from app.engines import registry
    from app.engines.host import HostInfo

    host = HostInfo(os="linux", arch="x86_64", accelerator="rocm", gpu="AMD gfx1103", gpu_targets=["gfx1103"])
    monkeypatch.setattr(registry, "detect", lambda: host)
    monkeypatch.setattr(registry.backends, "preflight", lambda accelerator: "")
    return host


@pytest.fixture
def server_env(tmp_path, monkeypatch, fake_host):
    """The FastAPI app on tmp dirs with fake CLIs; yields (client, calls) where calls() lists recorded argv."""
    from fastapi.testclient import TestClient

    from app import jobs, model_setup
    from app.engines.registry import engines
    from app.main import create_app
    from app.routes import setup as setup_routes
    from app.settings import config, paths

    models, data, library, engines_dir = (tmp_path / d for d in ("models", "data", "library", "engines"))
    models.mkdir()
    install_fake_builtin_models(models)
    install_fake_engine(engines_dir)
    argv_log = tmp_path / "argv.jsonl"
    monkeypatch.setenv("FAKE_ARGV_LOG", str(argv_log))
    monkeypatch.setenv("FAKE_PNG_HEX", png_bytes().hex())
    monkeypatch.delenv("SERVER_TOKEN", raising=False)
    monkeypatch.setattr(paths, "models", str(models))
    monkeypatch.setattr(paths, "data", str(data))
    monkeypatch.setattr(paths, "library", str(library))
    monkeypatch.setattr(paths, "engines", str(engines_dir))
    monkeypatch.setattr(
        model_setup, "status", lambda m=None: model_setup.ModelStatus(ready=True, items=[], missing_bytes=0)
    )
    web = tmp_path / "web"  # stands in for the built UI (web/dist)
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>test</title>")
    (web / "app.js").write_text("export {};")
    monkeypatch.setenv("WEB_DIR", str(web))
    config.reset_cache()
    m = jobs.manager
    with m.lock:
        m.jobs.clear()
        m.queue.clear()
        m.loaded = False
    setup_routes.progress.update(running=False, error="")
    engines.progress.update(running=False, error="")
    assert engines.reload().state == "ready"

    def calls():
        return [json.loads(x) for x in argv_log.read_text().splitlines()] if argv_log.exists() else []

    yield TestClient(create_app()), calls
    config.reset_cache()


def wait_job(client, jid, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/v1/jobs/{jid}").json()
        if job["state"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {jid} did not finish")
