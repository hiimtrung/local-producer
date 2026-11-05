"""Supervisor process for local-producer services.

Manages the lifecycle of the API server and optional matting server, capturing logs,
performing startup health checks, publishing runtime state (runtime.json), and ensuring
clean process group termination upon shutdown or child failure.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

if __package__ is None or __package__ == "":
    # Add server/ directory to sys.path when invoked directly
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app import __version__
    from app.runtime_env import Layout, child_env
else:
    from . import __version__
    from .runtime_env import Layout, child_env


def iso_timestamp() -> str:
    """Return the current UTC timestamp formatted as ISO-8601 with microsecond precision and Z suffix."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def format_log_line(tag: str, line: str) -> str:
    """Format a line with an ISO-8601 UTC timestamp and the specified service tag."""
    clean = line.rstrip("\r\n")
    return f"{iso_timestamp()} [{tag}] {clean}\n"


def log_line(
    log_file: Path,
    tag: str,
    line: str,
    lock: threading.Lock,
    echo_stderr: bool = False,
) -> None:
    """Append a formatted log entry to the log file and optionally echo to stderr."""
    entry = format_log_line(tag, line)
    with lock:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)
            f.flush()
        if echo_stderr:
            try:
                if hasattr(sys.stderr, "fileno") and os.path.sameopenfile(sys.stderr.fileno(), f.fileno()):
                    return
            except (OSError, ValueError):
                pass
            sys.stderr.write(entry)
            sys.stderr.flush()


def log_supervisor(log_file: Path, message: str, lock: threading.Lock) -> None:
    """Log a supervisor message to runtime.log and echo it to sys.stderr."""
    log_line(log_file, "supervisor", message, lock, echo_stderr=True)


def stream_reader(
    stream: IO[str],
    tag: str,
    log_file: Path,
    lock: threading.Lock,
) -> None:
    """Read lines from a child process output stream and log them with the appropriate tag."""
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            log_line(log_file, tag, line, lock, echo_stderr=False)
    except (ValueError, OSError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def pick_port(requested: int = 13305) -> int:
    """Select an available loopback port for the API server.

    Attempts to bind the requested port on 127.0.0.1. If unavailable (OSError),
    binds to port 0 to let the OS assign an ephemeral port, closes it, and returns that port.

    Note: There is an inherent close-then-bind race window between releasing
    the probed socket and the child process binding it. This is accepted in v1.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", requested))
            return requested
        except OSError:
            pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def write_runtime_json(data_dir: Path, port: int, pid: int, version: str) -> Path:
    """Atomically write runtime.json with mode 0600.

    Writes to a temporary file runtime.json.tmp.{pid}, sets permissions to 0600,
    and replaces runtime.json atomically.
    """
    target = data_dir / "runtime.json"
    tmp = data_dir / f"runtime.json.tmp.{pid}"
    payload = {
        "url": f"http://127.0.0.1:{port}",
        "port": port,
        "pid": pid,
        "version": version,
        "started": datetime.now(UTC).isoformat(),
    }
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    return target


def remove_runtime_json_if_matching(runtime_file: Path, pid: int) -> bool:
    """Remove runtime.json only if it exists and contains the specified supervisor pid.

    Returns True if removed, False otherwise.
    """
    try:
        if not runtime_file.is_file():
            return False
        content = json.loads(runtime_file.read_text(encoding="utf-8"))
        if content.get("pid") == pid:
            runtime_file.unlink(missing_ok=True)
            return True
        return False
    except (OSError, json.JSONDecodeError, ValueError):
        return False


def shutdown_children(children: list[subprocess.Popen[str]], timeout_s: float = 10.0) -> None:
    """Terminate and reap child processes and their process groups."""
    active = [c for c in children if c.poll() is None]
    if not active:
        return

    # Signal all process groups with SIGTERM concurrently
    for child in active:
        try:
            if hasattr(os, "killpg"):
                os.killpg(child.pid, signal.SIGTERM)
            else:
                child.terminate()
        except (ProcessLookupError, OSError):
            pass

    # Wait up to timeout_s for child processes and groups to terminate
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        still_running = False
        for child in active:
            if child.poll() is None:
                still_running = True
                continue
            if hasattr(os, "killpg"):
                try:
                    os.killpg(child.pid, 0)
                    still_running = True
                except ProcessLookupError:
                    pass
                except OSError:
                    pass
        if not still_running:
            break
        time.sleep(0.05)

    # Force kill any remaining processes in groups
    for child in active:
        if hasattr(os, "killpg"):
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
        else:
            if child.poll() is None:
                child.kill()

    # Reap child processes to avoid zombies
    for child in active:
        try:
            child.wait(timeout=1.0)
        except (subprocess.TimeoutExpired, OSError):
            pass


def check_health(url: str, timeout_s: float = 1.0) -> bool:
    """Check an HTTP health endpoint, returning True if it responds 200 OK."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "local-producer-supervisor"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return bool(resp.status == 200)
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def run_supervisor(
    port: int = 13305,
    no_matte: bool = False,
    layout: Layout | None = None,
    server_dir: Path | None = None,
    health_timeout_s: float = 180.0,
    health_interval_s: float = 0.5,
    stop_event: threading.Event | None = None,
    custom_api_cmd: list[str] | None = None,
    custom_matte_cmd: list[str] | None = None,
) -> int:
    """Run the supervisor until shutdown signal or child termination."""
    resolved_layout = layout if layout is not None else Layout.resolve()
    resolved_layout.ensure()
    resolved_server_dir = server_dir if server_dir is not None else Path(__file__).resolve().parent.parent

    runtime_log = resolved_layout.data / "runtime.log"
    runtime_json = resolved_layout.data / "runtime.json"
    log_lock = threading.Lock()
    my_pid = os.getpid()

    log_supervisor(runtime_log, f"starting local-producer supervisor (pid {my_pid})", log_lock)

    selected_port = pick_port(port)
    env = child_env(resolved_layout)

    shutdown_requested = stop_event if stop_event is not None else threading.Event()

    def _sig_handler(signum: int, frame: object) -> None:
        shutdown_requested.set()

    # Install signal handlers on main thread if supported
    prev_handlers: dict[signal.Signals, signal._HANDLER] = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                prev_handlers[sig] = signal.signal(sig, _sig_handler)
            except (ValueError, OSError):
                pass

    all_children: list[subprocess.Popen[str]] = []
    threads: list[threading.Thread] = []

    matte_proc: subprocess.Popen[str] | None = None
    api_proc: subprocess.Popen[str] | None = None

    try:
        # Start matting server first (unless disabled)
        if not no_matte:
            matte_cmd = (
                custom_matte_cmd
                if custom_matte_cmd is not None
                else [sys.executable, "-W", "ignore", "matte_server.py", "--host", "127.0.0.1", "--port", "8083"]
            )
            matte_proc = subprocess.Popen(
                matte_cmd,
                cwd=str(resolved_server_dir),
                env=env,
                start_new_session=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            all_children.append(matte_proc)
            if matte_proc.stdout is not None:
                t_matte = threading.Thread(
                    target=stream_reader,
                    args=(matte_proc.stdout, "matte", runtime_log, log_lock),
                    daemon=True,
                )
                t_matte.start()
                threads.append(t_matte)

        # Start API server
        api_cmd = (
            custom_api_cmd
            if custom_api_cmd is not None
            else [sys.executable, "-m", "app.main", "--host", "127.0.0.1", "--port", str(selected_port)]
        )
        api_proc = subprocess.Popen(
            api_cmd,
            cwd=str(resolved_server_dir),
            env=env,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        all_children.append(api_proc)
        if api_proc.stdout is not None:
            t_api = threading.Thread(
                target=stream_reader,
                args=(api_proc.stdout, "api", runtime_log, log_lock),
                daemon=True,
            )
            t_api.start()
            threads.append(t_api)

        # Health polling
        api_health_url = f"http://127.0.0.1:{selected_port}/health"
        matte_health_url = "http://127.0.0.1:8083/health"
        deadline = time.monotonic() + health_timeout_s
        ready = False

        while time.monotonic() < deadline:
            if shutdown_requested.is_set():
                log_supervisor(runtime_log, "shutting down during startup on signal", log_lock)
                shutdown_children(all_children, timeout_s=10.0)
                remove_runtime_json_if_matching(runtime_json, my_pid)
                return 0

            # Check if any child exited prematurely
            if api_proc.poll() is not None:
                code = api_proc.returncode if api_proc.returncode != 0 else 1
                log_supervisor(
                    runtime_log,
                    f"API server exited prematurely with code {code}; see {runtime_log}",
                    log_lock,
                )
                shutdown_children(all_children, timeout_s=10.0)
                remove_runtime_json_if_matching(runtime_json, my_pid)
                return code

            if matte_proc is not None and matte_proc.poll() is not None:
                code = matte_proc.returncode if matte_proc.returncode != 0 else 1
                log_supervisor(
                    runtime_log,
                    f"matting server exited prematurely with code {code}; see {runtime_log}",
                    log_lock,
                )
                shutdown_children(all_children, timeout_s=10.0)
                remove_runtime_json_if_matching(runtime_json, my_pid)
                return code

            api_ok = check_health(api_health_url)
            matte_ok = True if no_matte else check_health(matte_health_url)

            if api_ok and matte_ok:
                ready = True
                break

            shutdown_requested.wait(health_interval_s)

        if not ready:
            log_supervisor(
                runtime_log,
                f"health check timed out after {int(health_timeout_s)} s; see {runtime_log}",
                log_lock,
            )
            shutdown_children(all_children, timeout_s=10.0)
            remove_runtime_json_if_matching(runtime_json, my_pid)
            return 1

        # Atomically write runtime.json and announce readiness
        write_runtime_json(resolved_layout.data, selected_port, my_pid, __version__)
        log_supervisor(runtime_log, f"ready: http://127.0.0.1:{selected_port} (pid {my_pid})", log_lock)

        # Steady-state supervision
        while not shutdown_requested.is_set():
            if api_proc.poll() is not None:
                code = api_proc.returncode
                log_supervisor(runtime_log, f"API server exited with code {code}", log_lock)
                shutdown_children(all_children, timeout_s=10.0)
                remove_runtime_json_if_matching(runtime_json, my_pid)
                return code

            if matte_proc is not None and matte_proc.poll() is not None:
                code = matte_proc.returncode
                log_supervisor(runtime_log, f"matting server exited with code {code}", log_lock)
                shutdown_children(all_children, timeout_s=10.0)
                remove_runtime_json_if_matching(runtime_json, my_pid)
                return code

            shutdown_requested.wait(0.5)

        log_supervisor(runtime_log, "shutting down on signal", log_lock)
        shutdown_children(all_children, timeout_s=10.0)
        remove_runtime_json_if_matching(runtime_json, my_pid)
        return 0

    finally:
        shutdown_children(all_children, timeout_s=10.0)
        remove_runtime_json_if_matching(runtime_json, my_pid)
        for sig, h in prev_handlers.items():
            try:
                signal.signal(sig, h)
            except (ValueError, OSError):
                pass


def main() -> None:
    """CLI entry point for the supervisor."""
    parser = argparse.ArgumentParser(description="Supervisor process for local-producer services.")
    parser.add_argument("--port", type=int, default=13305, help="API server requested port (default 13305)")
    parser.add_argument("--no-matte", action="store_true", default=False, help="Disable the matting server child")
    args = parser.parse_args()

    exit_code = run_supervisor(port=args.port, no_matte=args.no_matte)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
