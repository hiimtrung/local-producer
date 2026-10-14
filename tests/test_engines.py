"""Engine packages (server/app/engines/): catalog rules, host detection, install, load / block, reload, remove, API."""

import io
import json
import os
import tarfile
import zipfile

import pytest
from conftest import FAKE_CLI, install_fake_engine
from test_model_setup import FakeOpener, sha

from app.engines import registry
from app.engines.catalog import Catalog, load_catalog
from app.engines.host import HostInfo, amd_targets, gfx_name
from app.model_setup import SetupError

ROCM = HostInfo(os="linux", arch="x86_64", accelerator="rocm", gpu="AMD gfx1103", gpu_targets=["gfx1103"])


# ---------------------------------------------------------------- catalog


def test_the_shipped_catalog_is_valid_and_pinned():
    cat = load_catalog()
    assert cat.packages, "at least the package for the reference machine"
    for p in cat.packages:
        for it in p.items:
            assert it["url"].startswith("https://") and "/latest/" not in it["url"]
        dests = {it["dest"] for it in p.items}
        for r in p.runners.values():  # every runner comes from one of the package's own downloads
            assert r.bin.split("/")[0] in dests
    assert {p.accelerator for p in cat.planned} == {"cuda", "mlx"}


def _catalog(**package_changes):
    raw = json.loads(json.dumps(load_catalog().model_dump()))
    raw["packages"][0].update(package_changes)
    return raw


@pytest.mark.parametrize(
    "changes",
    [
        {"env": {"LD_PRELOAD": "/x.so"}},
        {"env": {"PATH": "/tmp"}},
        {"lib_dirs": ["../../etc"]},
        {"runners": {"sd-cli": {"bin": "/usr/bin/env"}}},
        {"version": "../1"},
    ],
)
def test_catalog_rejects_unsafe_packages(changes):
    with pytest.raises((SetupError, ValueError)):
        Catalog.model_validate(_catalog(**changes))


# ---------------------------------------------------------------- host


@pytest.mark.parametrize(("version", "name"), [(110003, "gfx1103"), (90010, "gfx90a"), (110501, "gfx1151")])
def test_gfx_names(version, name):
    assert gfx_name(version) == name


def test_amd_targets_skip_cpu_nodes(tmp_path):
    for n, version in ((0, 0), (1, 110003)):
        (tmp_path / str(n)).mkdir()
        (tmp_path / str(n) / "properties").write_text(f"simd_count 24\ngfx_target_version {version}\n")
    assert amd_targets(str(tmp_path)) == ["gfx1103"]


def test_platform_mismatch_reasons():
    p = load_catalog().find("rocm-gfx1103").platform
    assert p.mismatch(ROCM) == ""
    assert "gfx1100" in p.mismatch(ROCM.model_copy(update={"gpu_targets": ["gfx1100"]}))
    assert "needs rocm" in p.mismatch(ROCM.model_copy(update={"accelerator": "cuda"}))
    assert "macos" in p.mismatch(ROCM.model_copy(update={"os": "macos", "arch": "arm64"}))


# ---------------------------------------------------------------- registry


@pytest.fixture
def eng(tmp_path, monkeypatch, fake_host):
    from app.settings import paths

    monkeypatch.setattr(paths, "engines", str(tmp_path / "engines"))
    monkeypatch.setattr(paths, "data", str(tmp_path / "data"))
    e = registry.Engines()
    monkeypatch.setattr(registry, "engines", e)
    return e


def test_reload_loads_the_installed_package_and_builds_runner_envs(eng, tmp_path):
    assert eng.reload().state == "none"
    root = install_fake_engine(tmp_path / "engines")
    st = eng.reload()
    assert st.state == "ready" and st.runners == ["sd-cli", "trellis-cli"]
    r = eng.runner("sd-cli")
    assert r.bin == str(root / "sdcpp/sd-cli")
    libs = r.env["LD_LIBRARY_PATH"].split(":")
    assert libs[0] == str(root / "sdcpp") and str(root / "rocm/_rocm_sdk_core/lib") in libs
    assert r.env["AMD_SERIALIZE_KERNEL"] == "3"
    assert json.loads((tmp_path / "engines/active.json").read_text())["version"] == "2026.10.15"
    with pytest.raises(registry.EngineUnavailable):
        eng.runner("blender")


def test_a_failing_preflight_or_self_test_blocks_the_package(eng, tmp_path, monkeypatch):
    install_fake_engine(tmp_path / "engines")
    monkeypatch.setattr(registry.backends, "preflight", lambda a: "amdgpu cwsr_enable is 1")
    st = eng.reload()
    assert st.state == "blocked" and "cwsr_enable" in st.problem
    with pytest.raises(registry.EngineUnavailable, match="cwsr_enable"):
        eng.runner("sd-cli")
    monkeypatch.setattr(registry.backends, "preflight", lambda a: "")
    monkeypatch.setenv("FAKE_SELF_TEST_RC", "127")
    st = eng.reload()
    assert st.state == "blocked" and "self-test failed (rc=127)" in st.problem


def test_reload_prefers_the_remembered_version(eng, tmp_path):
    install_fake_engine(tmp_path / "engines", "2026.10.01")
    install_fake_engine(tmp_path / "engines", "2026.10.15")
    assert eng.load("rocm-gfx1103", "2026.10.01").state == "ready"
    assert eng.reload().version == "2026.10.01"
    os.unlink(tmp_path / "engines/active.json")
    assert eng.reload().version == "2026.10.15"  # nothing remembered: the newest install
    eng.remove("rocm-gfx1103", "2026.10.01")
    assert [i.version for i in eng.installed()] == ["2026.10.15"]
    eng.remove("rocm-gfx1103", "2026.10.15")  # the loaded one: unloaded, then deleted
    st = eng.status()
    assert st.state == "none" and "was removed" in st.problem
    assert not (tmp_path / "engines/active.json").exists() and eng.installed() == []
    with pytest.raises(registry.EngineUnavailable):
        eng.runner("sd-cli")


def test_removal_waits_for_a_running_job(eng, tmp_path):
    install_fake_engine(tmp_path / "engines")
    eng.reload()
    with registry.gpu_lock, pytest.raises(registry.EngineBusy):
        eng.remove("rocm-gfx1103", "2026.10.15")


@pytest.mark.parametrize(
    ("older", "newer"), [("2026.10.15", "2026.10.15b"), ("2026.9.30", "2026.10.1"), ("1.9", "1.10")]
)
def test_version_order(older, newer):
    from app.engines.catalog import version_key

    assert version_key(older) < version_key(newer)


def test_catalog_versions_and_update_check(eng, tmp_path, monkeypatch):
    raw = _catalog()
    second = json.loads(json.dumps(raw["packages"][0])) | {"version": "2026.11.01"}
    raw["packages"].append(second)
    cat = Catalog.model_validate(raw)
    monkeypatch.setattr(eng, "catalog", lambda: cat)
    assert [p.version for p in cat.versions("rocm-gfx1103")] == ["2026.11.01", "2026.10.15"]
    assert cat.find("rocm-gfx1103").version == "2026.11.01"
    install_fake_engine(tmp_path / "engines")
    eng.reload()
    api = "https://api.github.com/repos/{}/releases/latest"
    releases = {
        api.format("leejet/stable-diffusion.cpp"): json.dumps(
            {"tag_name": "master-990-abc", "html_url": "https://github.com/x"}
        ).encode(),
        api.format("pwilkin/trellis.cpp"): json.dumps({"tag_name": "v0.8.1"}).encode(),
    }
    report = eng.check_updates(opener=FakeOpener(releases))
    assert [p.version for p in report.packages] == ["2026.11.01"]
    by_repo = {u.repo: u for u in report.upstream}
    assert (
        by_repo["leejet/stable-diffusion.cpp"].newer
        and by_repo["leejet/stable-diffusion.cpp"].latest == "master-990-abc"
    )
    assert not by_repo["pwilkin/trellis.cpp"].newer
    overview = eng.overview()
    assert [(p.version, p.latest, p.loaded) for p in overview.packages] == [
        ("2026.11.01", True, False),
        ("2026.10.15", False, True),
    ]


def _archive(kind, name, data):
    buf = io.BytesIO()
    if kind == "zip":
        with zipfile.ZipFile(buf, "w") as z:
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o755 << 16
            z.writestr(info, data)
    else:
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_install_downloads_verifies_unpacks_and_loads(eng, tmp_path, monkeypatch):
    cli = FAKE_CLI.encode()
    files = {
        "https://github.com/o/sd/releases/download/v1/sd.zip": _archive("zip", "build/bin/sd-cli", cli),
        "https://github.com/o/tr/releases/download/v1/tr.tar.gz": _archive("tgz", "trellis-cli", cli),
        "https://stable.repo.amd.com/rocm/core.whl": _archive("zip", "_rocm_sdk_core/lib/libamdhip64.so", b"elf"),
    }
    items = [
        {"id": "sd", "kind": "archive", "format": "zip", "strip": "build/bin/", "check": "sd-cli", "dest": "sdcpp"},
        {"id": "tr", "kind": "archive", "format": "tar.gz", "check": "trellis-cli", "dest": "trellis"},
        {"id": "rocm", "kind": "archive", "format": "zip", "dest": "rocm"},
    ]
    for it, (url, data) in zip(items, files.items(), strict=True):
        it.update(url=url, size=len(data), sha256=sha(data))
    cat = Catalog.model_validate(_catalog(items=items))
    eng._catalog = cat
    monkeypatch.setattr(eng, "catalog", lambda: cat)
    st = eng.install("rocm-gfx1103", opener=FakeOpener(files))
    assert st.state == "ready"
    root = tmp_path / "engines/rocm-gfx1103" / cat.packages[0].version
    assert (root / "rocm/_rocm_sdk_core/lib/libamdhip64.so").read_bytes() == b"elf"
    assert os.access(root / "sdcpp/sd-cli", os.X_OK)
    assert not (tmp_path / "engines/.cache").exists() or not os.listdir(tmp_path / "engines/.cache")
    snap = eng.progress.snapshot()
    assert not snap.running and snap.done_items == 3 and snap.error == ""


def test_install_refuses_a_package_for_another_machine(eng, monkeypatch):
    monkeypatch.setattr(eng, "host", lambda: ROCM.model_copy(update={"gpu_targets": ["gfx1100"]}))
    with pytest.raises(SetupError, match="does not fit"):
        eng.install("rocm-gfx1103")


# ---------------------------------------------------------------- API


def test_engines_api_and_jobs_without_an_engine(server_env, tmp_path):
    c, _ = server_env
    o = c.get("/v1/engines").json()
    assert o["engine"]["state"] == "ready" and o["recommended"] == "rocm-gfx1103"
    assert o["installed"][0]["active"] and o["packages"][0]["compatible"]
    assert {s["name"] for s in o["storage"]} == {"Models", "Engines", "Library", "Server state"}
    assert c.get("/v1/system").json()["engine"]["state"] == "ready"
    assert c.post("/v1/engines/rocm-gfx1103/1.0/load").status_code == 404
    assert c.post("/v1/engines/rocm-gfx1103/0.1/install").status_code == 404  # not a catalog version
    assert c.post("/v1/engines/Bad_Id/install").status_code == 422
    assert c.post("/v1/engines/cuda-x/install").status_code == 404

    os.environ["FAKE_SELF_TEST_RC"] = "1"
    try:
        assert c.post("/v1/engines/reload").json()["state"] == "blocked"
    finally:
        del os.environ["FAKE_SELF_TEST_RC"]
    r = c.post("/v1/jobs", json={"kind": "image.generate", "params": {"prompt": "a cat"}})
    assert r.status_code == 503 and "self-test failed" in r.json()["detail"]
    s = c.get("/v1/setup").json()
    assert not s["ready"] and s["models_ready"] and s["engine"]["state"] == "blocked"
    assert c.post("/v1/engines/reload").json()["state"] == "ready"
    assert c.post("/v1/jobs", json={"kind": "image.generate", "params": {"prompt": "a cat"}}).status_code == 202
