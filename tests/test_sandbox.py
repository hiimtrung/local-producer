"""Tests for app.engines.sandbox: macOS sandbox-exec, Linux bwrap probe and isolation."""

import os
import subprocess

import pytest
from conftest import install_fake_engine

from app.engines import registry, sandbox
from app.engines.host import HostInfo

MAC_HOST = HostInfo(os="macos", arch="arm64", accelerator="metal", gpu="Apple M4", gpu_targets=[])
LINUX_HOST = HostInfo(os="linux", arch="x86_64", accelerator="rocm", gpu="AMD gfx1103", gpu_targets=["gfx1103"])
WIN_HOST = HostInfo(os="windows", arch="x86_64", accelerator="cpu", gpu="none", gpu_targets=[])


@pytest.fixture(autouse=True)
def clean_sandbox_cache():
    sandbox.reset_cache()
    yield
    sandbox.reset_cache()


def test_macos_sandbox_available(monkeypatch):
    monkeypatch.setattr(os, "access", lambda path, mode: path == sandbox.SANDBOX_EXEC)
    assert sandbox.problem(MAC_HOST) == ""
    assert sandbox.prefix(MAC_HOST) == (sandbox.SANDBOX_EXEC, "-p", sandbox.SANDBOX_PROFILE)


def test_macos_sandbox_missing(monkeypatch):
    monkeypatch.setattr(os, "access", lambda path, mode: False)
    prob = sandbox.problem(MAC_HOST)
    assert sandbox.SANDBOX_EXEC in prob
    assert "missing or not executable" in prob
    assert "unsandboxed is refused" in prob
    assert sandbox.prefix(MAC_HOST) == ()


def test_linux_bwrap_probe_success(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output=True, timeout=5):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(sandbox.shutil, "which", lambda cmd: "/usr/bin/bwrap" if cmd == "bwrap" else None)
    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)

    assert sandbox.problem(LINUX_HOST) == ""
    assert sandbox.prefix(LINUX_HOST) == sandbox.BWRAP_PREFIX
    # Verify cached on second call
    assert sandbox.problem(LINUX_HOST) == ""
    assert len(calls) == 1
    assert calls[0] == ["bwrap", "--unshare-net", "--dev-bind", "/", "/", "--", "true"]


def test_linux_bwrap_missing(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda cmd: None)
    prob = sandbox.problem(LINUX_HOST)
    assert "apt install bubblewrap" in prob
    assert "running engine CLIs unsandboxed needs written approval" in prob
    assert sandbox.prefix(LINUX_HOST) == ()
    # Check cache
    assert sandbox.problem(LINUX_HOST) == prob


def test_linux_bwrap_probe_nonzero_exit(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda cmd: "/usr/bin/bwrap")
    monkeypatch.setattr(
        sandbox.subprocess,
        "run",
        lambda cmd, capture_output=True, timeout=5: subprocess.CompletedProcess(
            cmd, returncode=1, stdout=b"", stderr=b"error"
        ),
    )
    prob = sandbox.problem(LINUX_HOST)
    assert "bwrap probe failed (rc=1)" in prob
    assert "running engine CLIs unsandboxed needs written approval" in prob
    assert sandbox.prefix(LINUX_HOST) == ()


def test_linux_bwrap_probe_timeout(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda cmd: "/usr/bin/bwrap")

    def fake_run(cmd, capture_output=True, timeout=5):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    prob = sandbox.problem(LINUX_HOST)
    assert "bwrap probe timed out" in prob
    assert "running engine CLIs unsandboxed needs written approval" in prob
    assert sandbox.prefix(LINUX_HOST) == ()


def test_linux_bwrap_probe_oserror(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda cmd: "/usr/bin/bwrap")

    def fake_run(cmd, capture_output=True, timeout=5):
        raise OSError("permission denied")

    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    prob = sandbox.problem(LINUX_HOST)
    assert "bwrap probe failed (permission denied)" in prob
    assert "running engine CLIs unsandboxed needs written approval" in prob
    assert sandbox.prefix(LINUX_HOST) == ()


def test_unsupported_os():
    prob = sandbox.problem(WIN_HOST)
    assert prob == "no engine sandbox is implemented for windows; running engine CLIs unsandboxed is refused"
    assert sandbox.prefix(WIN_HOST) == ()


def test_engines_load_blocked_by_sandbox_problem(tmp_path, monkeypatch):
    from app.settings import paths

    monkeypatch.setattr(paths, "engines", str(tmp_path / "engines"))
    monkeypatch.setattr(paths, "data", str(tmp_path / "data"))

    install_fake_engine(tmp_path / "engines")
    eng = registry.Engines()

    # Preflight and mismatch pass
    monkeypatch.setattr(eng, "host", lambda: LINUX_HOST)
    monkeypatch.setattr(registry.backends, "preflight", lambda accelerator: "")

    # Sandbox problem reports missing bwrap
    expected_prob = "bwrap is missing (apt install bubblewrap); running engine CLIs unsandboxed needs written approval"
    monkeypatch.setattr(sandbox, "problem", lambda h: expected_prob)

    st = eng.load("rocm-gfx1103", "2026.10.15")
    assert st.state == "blocked"
    assert st.problem == expected_prob
    assert eng.status().state == "blocked"
    assert eng.status().problem == expected_prob

    with pytest.raises(registry.EngineUnavailable, match="bwrap is missing"):
        eng.runner("sd-cli")


def test_runner_prefix_wired_to_sandbox(tmp_path, monkeypatch):
    from app.settings import paths

    monkeypatch.setattr(paths, "engines", str(tmp_path / "engines"))
    monkeypatch.setattr(paths, "data", str(tmp_path / "data"))

    install_fake_engine(tmp_path / "engines")
    eng = registry.Engines()

    monkeypatch.setattr(eng, "host", lambda: LINUX_HOST)
    monkeypatch.setattr(registry.backends, "preflight", lambda accelerator: "")
    monkeypatch.setattr(sandbox, "problem", lambda h: "")
    monkeypatch.setattr(eng, "_self_test", lambda spec, root: "")
    monkeypatch.setattr(sandbox, "prefix", lambda h: sandbox.BWRAP_PREFIX)

    st = eng.load("rocm-gfx1103", "2026.10.15")
    assert st.state == "ready"
    runner = eng.runner("sd-cli")
    assert runner.prefix == sandbox.BWRAP_PREFIX
    assert runner.argv[: len(sandbox.BWRAP_PREFIX)] == list(sandbox.BWRAP_PREFIX)
    assert runner.argv[-1] == runner.bin
