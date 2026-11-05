"""Tests for scripts/lp and scripts/lp.py."""

import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.runtime_env import Layout, data_root

REPO_ROOT = Path(__file__).resolve().parent.parent
LP_SCRIPT = REPO_ROOT / "scripts" / "lp"
LP_PY = REPO_ROOT / "scripts" / "lp.py"


def load_lp_module() -> Any:
    """Load scripts/lp.py dynamically via importlib."""
    spec = importlib.util.spec_from_file_location("lp", LP_PY)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_lp_via_importlib() -> None:
    module = load_lp_module()
    assert hasattr(module, "main")
    assert hasattr(module, "read_runtime")
    assert hasattr(module, "tail")
    assert hasattr(module, "port_free")


def test_read_runtime(tmp_path: Path) -> None:
    lp = load_lp_module()
    read_fn = lp.read_runtime

    # Missing file
    missing = tmp_path / "runtime.json"
    assert read_fn(missing) is None

    # Corrupt / invalid JSON
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{bad-json", encoding="utf-8")
    assert read_fn(corrupt) is None

    # Valid JSON but not a dictionary
    not_dict = tmp_path / "list.json"
    not_dict.write_text("[1, 2, 3]", encoding="utf-8")
    assert read_fn(not_dict) is None

    # Missing required field
    missing_field = tmp_path / "missing_field.json"
    missing_field.write_text(json.dumps({"url": "http://127.0.0.1:13305", "port": 13305}), encoding="utf-8")
    assert read_fn(missing_field) is None

    # Wrong field type (port is str, pid is bool)
    wrong_type = tmp_path / "wrong_type.json"
    wrong_type.write_text(
        json.dumps(
            {
                "url": "http://127.0.0.1:13305",
                "port": "13305",
                "pid": 1234,
                "version": "0.3.0",
                "started": "2026-11-05T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    assert read_fn(wrong_type) is None

    wrong_type_bool = tmp_path / "wrong_type_bool.json"
    wrong_type_bool.write_text(
        json.dumps(
            {
                "url": "http://127.0.0.1:13305",
                "port": 13305,
                "pid": True,
                "version": "0.3.0",
                "started": "2026-11-05T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    assert read_fn(wrong_type_bool) is None

    # Valid runtime.json
    valid = tmp_path / "valid.json"
    payload = {
        "url": "http://127.0.0.1:13305",
        "port": 13305,
        "pid": 4321,
        "version": "0.3.0",
        "started": "2026-11-05T00:00:00Z",
    }
    valid.write_text(json.dumps(payload), encoding="utf-8")
    result = read_fn(valid)
    assert result == payload


def test_tail(tmp_path: Path) -> None:
    lp = load_lp_module()
    tail_fn = lp.tail

    # Missing file
    assert tail_fn(tmp_path / "missing.log", 5) == []

    # n <= 0
    test_file = tmp_path / "test.log"
    test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
    assert tail_fn(test_file, 0) == []
    assert tail_fn(test_file, -2) == []

    # Shorter file than n
    assert tail_fn(test_file, 10) == ["line1\n", "line2\n", "line3\n"]

    # Longer file than n
    assert tail_fn(test_file, 2) == ["line2\n", "line3\n"]


def test_port_free() -> None:
    lp = load_lp_module()
    port_free_fn = lp.port_free

    # Bind a temporary port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]

    try:
        # While held, port_free must be False
        assert port_free_fn(port) is False
    finally:
        sock.close()

    # After close, port_free must be True
    assert port_free_fn(port) is True


def test_invalid_commands_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    lp = load_lp_module()
    main_fn = lp.main

    # Unknown command
    code = main_fn(["unknown_cmd"])
    assert code == 2
    err = capsys.readouterr().err
    assert "Unknown command" in err

    # Extra arguments to lp up
    code = main_fn(["up", "extra"])
    assert code == 2
    err = capsys.readouterr().err
    assert "Invalid argument for up" in err

    # Extra arguments to root
    code = main_fn(["root", "extra"])
    assert code == 2
    err = capsys.readouterr().err
    assert "Invalid arguments for root" in err

    # No arguments
    code = main_fn([])
    assert code == 2


def test_lp_shell_root_matches_layout(tmp_path: Path) -> None:
    target_root = (tmp_path / "shell_lp_home").resolve()
    env = os.environ.copy()
    env["LP_HOME"] = str(target_root)
    # Ensure LP_PYTHON or python3 can run
    env["LP_PYTHON"] = sys.executable

    res = subprocess.run(
        [str(LP_SCRIPT), "root"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    output = res.stdout.strip()
    assert output == str(target_root)

    # Also test Layout.resolve().root with LP_HOME set
    os.environ["LP_HOME"] = str(target_root)
    try:
        assert Layout.resolve().root == target_root
        assert data_root() == target_root
    finally:
        del os.environ["LP_HOME"]


def test_cmd_status_stale_pid_removes_runtime_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target_root = tmp_path / "lp_home"
    target_root.mkdir()
    server_dir = target_root / "server"
    server_dir.mkdir()
    runtime_json = server_dir / "runtime.json"
    # Choose an impossible / dead PID
    runtime_json.write_text(
        json.dumps(
            {
                "url": "http://127.0.0.1:13305",
                "port": 13305,
                "pid": 9999999,
                "version": "0.3.0",
                "started": "2026-11-05T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("LP_HOME", str(target_root))
    lp = load_lp_module()
    code = lp.main(["status"])
    assert code == 1
    out = capsys.readouterr().out
    assert "stale pid 9999999" in out
    assert not runtime_json.exists()
