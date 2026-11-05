"""Tests for runtime environment resolution, filesystem layout, and child process environment."""

import os
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.runtime_env import Layout, child_env, data_root, thread_count
from app.settings import Paths


def test_lp_home_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom_root = tmp_path / "custom_lp"
    monkeypatch.setenv("LP_HOME", str(custom_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "ignored_xdg"))
    monkeypatch.setattr(sys, "platform", "darwin")

    assert data_root() == custom_root.resolve()

    monkeypatch.setattr(sys, "platform", "linux")
    assert data_root() == custom_root.resolve()


def test_lp_home_tilde_expansion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LP_HOME", "~/custom_lp_test")
    expected = (Path.home() / "custom_lp_test").resolve()
    assert data_root() == expected


def test_macos_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LP_HOME", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")

    expected = (Path.home() / "Library" / "Application Support" / "local-producer").resolve()
    assert data_root() == expected
    assert data_root(platform="darwin") == expected


def test_linux_default_without_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LP_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")

    expected = (Path.home() / ".local" / "share" / "local-producer").resolve()
    assert data_root() == expected
    assert data_root(platform="linux") == expected


def test_linux_default_with_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LP_HOME", raising=False)
    xdg_share = tmp_path / "custom_share"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_share))
    monkeypatch.setattr(sys, "platform", "linux")

    expected = (xdg_share / "local-producer").resolve()
    assert data_root() == expected
    assert data_root(platform="linux") == expected


def test_layout_resolve_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "test_root"
    monkeypatch.setenv("LP_HOME", str(root))

    layout = Layout.resolve()
    assert layout.root == root.resolve()
    assert layout.models == root.resolve() / "models"
    assert layout.engines == root.resolve() / "engines"
    assert layout.library == root.resolve() / "library"
    assert layout.data == root.resolve() / "server"
    assert layout.venv == root.resolve() / "venv"


def test_layout_resolve_explicit_root(tmp_path: Path) -> None:
    root = tmp_path / "explicit"
    layout = Layout.resolve(root)
    assert layout.root == root.resolve()
    assert layout.models == root.resolve() / "models"
    assert layout.engines == root.resolve() / "engines"
    assert layout.library == root.resolve() / "library"
    assert layout.data == root.resolve() / "server"
    assert layout.venv == root.resolve() / "venv"


def test_layout_ensure(tmp_path: Path) -> None:
    root = tmp_path / "ensure_dir"
    layout = Layout.resolve(root)

    assert not layout.root.exists()
    layout.ensure()

    for d in (layout.root, layout.models, layout.engines, layout.library, layout.data, layout.venv):
        assert d.is_dir()

    data_mode = stat.S_IMODE(layout.data.stat().st_mode)
    assert data_mode == 0o700

    # Idempotent call should not fail
    layout.ensure()
    assert stat.S_IMODE(layout.data.stat().st_mode) == 0o700


def test_thread_count_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_run = MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="6\n"))
    monkeypatch.setattr(subprocess, "run", mock_run)

    assert thread_count(platform="darwin") == 6
    assert mock_run.call_count == 1
    call_args = mock_run.call_args[0][0]
    assert call_args[1:] == ["-n", "hw.perflevel0.physicalcpu"]


def test_thread_count_macos_failure_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_err(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.SubprocessError("sysctl failed")

    monkeypatch.setattr(subprocess, "run", raise_err)
    monkeypatch.setattr(os, "cpu_count", lambda: 8)

    assert thread_count(platform="darwin") == 8


def test_thread_count_linux_sched_affinity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "sched_getaffinity", lambda _pid: {0, 1, 2, 3}, raising=False)
    assert thread_count(platform="linux") == 4

    # Capped at 8
    monkeypatch.setattr(os, "sched_getaffinity", lambda _pid: set(range(16)), raising=False)
    assert thread_count(platform="linux") == 8


def test_thread_count_linux_failure_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_err(_pid: int) -> set[int]:
        raise OSError("affinity error")

    monkeypatch.setattr(os, "sched_getaffinity", raise_err, raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 4)

    assert thread_count(platform="linux") == 4


def test_thread_count_fallback_never_zero_or_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "cpu_count", lambda: None)
    assert thread_count(platform="other") == 1

    monkeypatch.setattr(os, "cpu_count", lambda: 0)
    assert thread_count(platform="other") == 1

    monkeypatch.setattr(os, "cpu_count", lambda: -2)
    assert thread_count(platform="other") == 1


def test_child_env(tmp_path: Path) -> None:
    layout = Layout.resolve(tmp_path / "env_root")
    base = {
        "CUSTOM_KEY": "custom_val",
        "SERVER_TOKEN": "secret_token_123",
        "MODELS_DIR": "/old/models",
    }

    env = child_env(layout, base)

    assert env["CUSTOM_KEY"] == "custom_val"
    assert env["SERVER_TOKEN"] == "secret_token_123"
    assert env["MODELS_DIR"] == str(layout.models)
    assert env["ENGINES_DIR"] == str(layout.engines)
    assert env["LIBRARY_DIR"] == str(layout.library)
    assert env["DATA_DIR"] == str(layout.data)
    assert env["U2NET_HOME"] == str(layout.models / "rembg")
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["OMP_NUM_THREADS"] == str(thread_count())
    assert env["HOST_MODELS"] == str(layout.models)
    assert env["HOST_ENGINES"] == str(layout.engines)
    assert env["HOST_LIBRARY"] == str(layout.library)
    assert env["HOST_DATA"] == str(layout.data)


def test_child_env_defaults_to_os_environ(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    layout = Layout.resolve(tmp_path / "env_root")
    monkeypatch.setenv("TEST_INHERITED_KEY", "inherited_val")

    env = child_env(layout)
    assert env["TEST_INHERITED_KEY"] == "inherited_val"
    assert env["MODELS_DIR"] == str(layout.models)


def test_settings_paths_layout_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    test_root = tmp_path / "paths_root"
    monkeypatch.setenv("LP_HOME", str(test_root))
    monkeypatch.delenv("MODELS_DIR", raising=False)
    monkeypatch.delenv("ENGINES_DIR", raising=False)
    monkeypatch.delenv("LIBRARY_DIR", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)

    p = Paths()
    assert p.models == str(test_root / "models")
    assert p.engines == str(test_root / "engines")
    assert p.library == str(test_root / "library")
    assert p.data == str(test_root / "server")
    assert p.runtime == str(test_root / "server" / "runtime.json")
    assert p.runtime_log == str(test_root / "server" / "runtime.log")
    assert p.log == str(test_root / "server" / "server.log")


def test_settings_paths_honours_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELS_DIR", "/override/models")
    monkeypatch.setenv("ENGINES_DIR", "/override/engines")
    monkeypatch.setenv("LIBRARY_DIR", "/override/library")
    monkeypatch.setenv("DATA_DIR", "/override/data")

    p = Paths()
    assert p.models == "/override/models"
    assert p.engines == "/override/engines"
    assert p.library == "/override/library"
    assert p.data == "/override/data"
    assert p.runtime == "/override/data/runtime.json"
    assert p.runtime_log == "/override/data/runtime.log"
    assert p.log == "/override/data/server.log"
