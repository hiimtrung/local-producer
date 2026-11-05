"""Tests for supervisor process management, logging, health polling, and clean shutdown."""

from __future__ import annotations

import json
import os
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app.runtime_env import Layout
from app.supervisor import (
    format_log_line,
    log_line,
    pick_port,
    remove_runtime_json_if_matching,
    run_supervisor,
    terminate_process_group,
    write_runtime_json,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX-only supervisor tests")


def test_pick_port_when_free() -> None:
    """Test pick_port returns requested port when it is available."""
    # Find an unused port first
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = int(s.getsockname()[1])

    chosen = pick_port(free_port)
    assert chosen == free_port


def test_pick_port_when_occupied() -> None:
    """Test pick_port falls back to ephemeral port when requested port is bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        occupied_port = int(s.getsockname()[1])

        chosen = pick_port(occupied_port)
        assert chosen != occupied_port
        assert chosen > 0


def test_write_runtime_json_atomicity_and_mode(tmp_path: Path) -> None:
    """Test write_runtime_json writes file atomically with 0600 mode and valid fields."""
    data_dir = tmp_path / "server"
    data_dir.mkdir(parents=True)
    target = write_runtime_json(data_dir, 13305, os.getpid(), "0.3.0")

    assert target == data_dir / "runtime.json"
    assert target.is_file()

    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode == 0o600

    # Ensure no lingering tmp file
    tmp_files = list(data_dir.glob("runtime.json.tmp.*"))
    assert tmp_files == []

    content = json.loads(target.read_text(encoding="utf-8"))
    assert content["url"] == "http://127.0.0.1:13305"
    assert content["port"] == 13305
    assert content["pid"] == os.getpid()
    assert content["version"] == "0.3.0"
    assert "started" in content


def test_remove_runtime_json_if_matching(tmp_path: Path) -> None:
    """Test remove_runtime_json_if_matching deletes file only if pid matches."""
    data_dir = tmp_path / "server"
    data_dir.mkdir(parents=True)
    runtime_file = write_runtime_json(data_dir, 13305, 11111, "0.3.0")

    # Mismatched pid should not delete
    removed = remove_runtime_json_if_matching(runtime_file, 22222)
    assert not removed
    assert runtime_file.is_file()

    # Matching pid deletes
    removed = remove_runtime_json_if_matching(runtime_file, 11111)
    assert removed
    assert not runtime_file.exists()

    # Deleting non-existent file returns False
    assert not remove_runtime_json_if_matching(runtime_file, 11111)


def test_format_log_line() -> None:
    """Test format_log_line formats timestamp, tag, and stripped line."""
    line = format_log_line("api", "hello world\r\n")
    assert line.endswith(" [api] hello world\n")
    # Verify timestamp format (starts with YYYY-MM-DDTHH:MM:SS)
    timestamp_part = line.split(" [api] ")[0]
    assert "T" in timestamp_part
    assert timestamp_part.endswith("Z")


def test_log_line_file_and_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test log_line appends to file and optionally writes to stderr."""
    log_file = tmp_path / "runtime.log"
    lock = threading.Lock()

    log_line(log_file, "matte", "matting progress", lock, echo_stderr=False)
    assert " [matte] matting progress\n" in log_file.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert captured.err == ""

    log_line(log_file, "supervisor", "supervisor alert", lock, echo_stderr=True)
    assert " [supervisor] supervisor alert\n" in log_file.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert " [supervisor] supervisor alert\n" in captured.err


def test_process_group_cleanup() -> None:
    """Test terminating a child process group kills both child and grandchild."""
    # Child script spawns a grandchild sleeper and prints grandchild pid to stdout
    script = (
        "import os, subprocess, sys, time\n"
        "grandchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "sys.stdout.write(f'{grandchild.pid}\\n')\n"
        "sys.stdout.flush()\n"
        "time.sleep(60)\n"
    )

    child = subprocess.Popen(
        [sys.executable, "-c", script],
        start_new_session=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    line = child.stdout.readline().strip()
    grandchild_pid = int(line)

    # Both child and grandchild should be running (os.kill succeeds without error)
    os.kill(child.pid, 0)
    os.kill(grandchild_pid, 0)

    # Terminate the process group
    terminate_process_group(child.pid, timeout_s=5.0)
    child.wait(timeout=2.0)

    # Verify both are gone
    time.sleep(0.1)
    with pytest.raises(ProcessLookupError):
        os.kill(child.pid, 0)

    with pytest.raises(ProcessLookupError):
        os.kill(grandchild_pid, 0)


def test_run_supervisor_lifecycle_and_shutdown(tmp_path: Path) -> None:
    """Test supervisor startup, health check polling, runtime.json creation, and clean shutdown."""
    layout = Layout.resolve(tmp_path / "lp_home")
    layout.ensure()

    # Find free port for dummy server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        test_port = int(s.getsockname()[1])

    # Minimal dummy HTTP server answering 200 on /health
    dummy_server_code = (
        "import http.server, sys\n"
        "class Handler(http.server.BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        if self.path == '/health':\n"
        "            self.send_response(200)\n"
        "            self.end_headers()\n"
        '            self.wfile.write(b\'{"status":"ok"}\')\n'
        "    def log_message(self, format, *args):\n"
        "        sys.stdout.write(format % args + '\\n')\n"
        "        sys.stdout.flush()\n"
        f"server = http.server.HTTPServer(('127.0.0.1', {test_port}), Handler)\n"
        "sys.stdout.write('dummy server running\\n')\n"
        "sys.stdout.flush()\n"
        "server.serve_forever()\n"
    )

    custom_api = [sys.executable, "-c", dummy_server_code]
    stop_event = threading.Event()
    supervisor_result: list[int] = []

    def _worker() -> None:
        rc = run_supervisor(
            port=test_port,
            no_matte=True,
            layout=layout,
            stop_event=stop_event,
            custom_api_cmd=custom_api,
            health_timeout_s=5.0,
            health_interval_s=0.1,
        )
        supervisor_result.append(rc)

    t = threading.Thread(target=_worker)
    t.start()

    # Wait for runtime.json to be written
    runtime_json = layout.data / "runtime.json"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not runtime_json.exists():
        time.sleep(0.05)

    assert runtime_json.exists()
    content = json.loads(runtime_json.read_text(encoding="utf-8"))
    assert content["port"] == test_port
    assert content["url"] == f"http://127.0.0.1:{test_port}"

    # Verify runtime.log contents
    runtime_log = layout.data / "runtime.log"
    log_content = runtime_log.read_text(encoding="utf-8")
    assert "[supervisor]" in log_content
    assert f"ready: http://127.0.0.1:{test_port}" in log_content
    assert "[api]" in log_content
    assert "dummy server running" in log_content

    # Signal stop
    stop_event.set()
    t.join(timeout=5.0)
    assert not t.is_alive()
    assert supervisor_result == [0]

    # After shutdown, runtime.json should be removed
    assert not runtime_json.exists()


def test_run_supervisor_child_premature_exit(tmp_path: Path) -> None:
    """Test supervisor terminates and exits with child error code when child dies prematurely."""
    layout = Layout.resolve(tmp_path / "lp_home")
    layout.ensure()

    failing_api = [sys.executable, "-c", "import sys; sys.exit(42)"]

    rc = run_supervisor(
        port=13305,
        no_matte=True,
        layout=layout,
        custom_api_cmd=failing_api,
        health_timeout_s=5.0,
        health_interval_s=0.1,
    )

    assert rc == 42
    runtime_json = layout.data / "runtime.json"
    assert not runtime_json.exists()

    runtime_log = layout.data / "runtime.log"
    assert runtime_log.exists()
    log_text = runtime_log.read_text(encoding="utf-8")
    assert "API server exited prematurely with code 42" in log_text


def test_run_supervisor_health_timeout(tmp_path: Path) -> None:
    """Test supervisor aborts with code 1 if health check fails to answer before timeout."""
    layout = Layout.resolve(tmp_path / "lp_home")
    layout.ensure()

    # Process sleeps instead of serving /health
    sleeping_api = [sys.executable, "-c", "import time; time.sleep(30)"]

    rc = run_supervisor(
        port=13305,
        no_matte=True,
        layout=layout,
        custom_api_cmd=sleeping_api,
        health_timeout_s=0.3,
        health_interval_s=0.05,
    )

    assert rc == 1
    runtime_json = layout.data / "runtime.json"
    assert not runtime_json.exists()

    runtime_log = layout.data / "runtime.log"
    assert runtime_log.exists()
    log_text = runtime_log.read_text(encoding="utf-8")
    assert "health check timed out after 0 s" in log_text


def _spawn_supervisor_subprocess(tmp_path: Path, test_port: int) -> tuple[subprocess.Popen[str], Layout, Path]:
    lp_home = tmp_path / "lp_home"
    layout = Layout.resolve(lp_home)
    layout.ensure()

    dummy_server_file = tmp_path / "dummy_server.py"
    dummy_server_file.write_text(
        "import http.server, sys\n"
        "class Handler(http.server.BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        if self.path == '/health':\n"
        "            self.send_response(200)\n"
        "            self.end_headers()\n"
        '            self.wfile.write(b\'{"status":"ok"}\')\n'
        "    def log_message(self, format, *args):\n"
        "        sys.stdout.write(format % args + '\\n')\n"
        "        sys.stdout.flush()\n"
        f"server = http.server.HTTPServer(('127.0.0.1', {test_port}), Handler)\n"
        "sys.stdout.write('dummy server running\\n')\n"
        "sys.stdout.flush()\n"
        "server.serve_forever()\n",
        encoding="utf-8",
    )

    runner_file = tmp_path / "run_sup.py"
    runner_file.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "from app.runtime_env import Layout\n"
        "from app.supervisor import run_supervisor\n"
        f"layout = Layout.resolve(Path('{lp_home}'))\n"
        f"cmd = [sys.executable, '{dummy_server_file}']\n"
        f"rc = run_supervisor(\n"
        f"    port={test_port}, no_matte=True, layout=layout, custom_api_cmd=cmd, health_timeout_s=5.0\n"
        f")\n"
        "sys.exit(rc)\n",
        encoding="utf-8",
    )

    server_dir = Path(__file__).resolve().parent.parent / "server"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(server_dir)

    proc = subprocess.Popen(
        [sys.executable, str(runner_file)],
        env=env,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc, layout, layout.data / "runtime.json"


def test_supervisor_subprocess_sigterm_removes_runtime_json(tmp_path: Path) -> None:
    """Test SIGTERM causes supervisor subprocess to exit 0 and remove runtime.json."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        test_port = int(s.getsockname()[1])

    proc, layout, runtime_json = _spawn_supervisor_subprocess(tmp_path, test_port)
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not runtime_json.exists():
            time.sleep(0.05)
        assert runtime_json.exists()

        proc.send_signal(signal.SIGTERM)
        exit_code = proc.wait(timeout=5.0)
        assert exit_code == 0
        assert not runtime_json.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_supervisor_subprocess_sigterm_preserves_overwritten_runtime_json(tmp_path: Path) -> None:
    """Test supervisor does not remove runtime.json if its pid was replaced."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        test_port = int(s.getsockname()[1])

    proc, layout, runtime_json = _spawn_supervisor_subprocess(tmp_path, test_port)
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not runtime_json.exists():
            time.sleep(0.05)
        assert runtime_json.exists()

        # Overwrite runtime.json with different pid
        other_payload = {
            "url": f"http://127.0.0.1:{test_port}",
            "port": test_port,
            "pid": 999999,
            "version": "0.3.0",
            "started": "2026-11-05T00:00:00Z",
        }
        runtime_json.write_text(json.dumps(other_payload), encoding="utf-8")

        proc.send_signal(signal.SIGTERM)
        exit_code = proc.wait(timeout=5.0)
        assert exit_code == 0

        # runtime.json should still exist because pid differed
        assert runtime_json.exists()
        saved = json.loads(runtime_json.read_text(encoding="utf-8"))
        assert saved["pid"] == 999999
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
