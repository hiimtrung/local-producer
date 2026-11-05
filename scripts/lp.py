"""Management CLI for local-producer server runtime, setup, and operations.

Standard library only: this entrypoint must run before any virtual environment
is created or third-party packages installed.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 12):  # noqa: UP036
    sys.stderr.write("lp needs Python 3.12; run 'uv python install 3.12' or set LP_PYTHON\n")
    sys.exit(1)

import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

# Insert repo server/ into sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.runtime_env import Layout, child_env, data_root  # noqa: E402

__all__ = [
    "Layout",
    "child_env",
    "cmd_root",
    "cmd_setup",
    "cmd_up",
    "data_root",
    "main",
    "port_free",
    "read_runtime",
    "tail",
]

USAGE = """usage: lp <command> [options]

Commands:
  root                 Print data root path
  setup [--migrate]    Set up virtualenv, requirements, and web UI
  up [--foreground] [--no-matte]
                       Start background or foreground supervisor
  down                 Stop supervisor and workers
  status               Check status of running server
  logs [--lines N] [-f] [--jobs]
                       Tail runtime.log or server.log
  exec ARGS...         Run command with server venv and environment
  doctor               Verify system requirements, layout, and engines
"""


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if the specified port is available for binding on host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
        except OSError:
            return False


def is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is currently alive."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def is_healthy(url: str, timeout_s: float = 1.0) -> bool:
    """Check if an HTTP health endpoint responds with 200 OK."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "local-producer-lp"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return bool(resp.status == 200)
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def read_runtime(path: Path) -> dict[str, Any] | None:
    """Read and validate runtime.json state.

    Returns None if missing, corrupted, not a dictionary, or missing
    required fields (url, port, pid, version, started) with correct types.
    """
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    fields: dict[str, type] = {
        "url": str,
        "port": int,
        "pid": int,
        "version": str,
        "started": str,
    }
    for field, expected_type in fields.items():
        if field not in data:
            return None
        val = data[field]
        if expected_type is int:
            if not isinstance(val, int) or isinstance(val, bool):
                return None
        elif not isinstance(val, expected_type):
            return None

    return data


def tail(path: Path, n: int = 10) -> list[str]:
    """Return the last n lines from the file at path.

    Returns an empty list if path does not exist or n <= 0.
    """
    if n <= 0 or not path.is_file():
        return []
    try:
        with open(path, "rb") as f:
            kept = deque(f, maxlen=n)
            return [b.decode("utf-8", errors="replace") for b in kept]
    except OSError:
        return []


def cmd_root(argv: list[str]) -> int:
    """Print the resolved data root path."""
    if argv:
        sys.stderr.write(f"Invalid arguments for root\n{USAGE}")
        return 2
    print(Layout.resolve().root)
    return 0


def cmd_setup(argv: list[str]) -> int:
    """Set up the Python virtual environment and build the web UI."""
    migrate = False
    for arg in argv:
        if arg == "--migrate":
            migrate = True
        else:
            sys.stderr.write(f"Invalid argument for setup: {arg}\n{USAGE}")
            return 2

    if migrate:
        old_path = Path("~/.local-producer").expanduser().resolve()
        new_path = Layout.resolve().root
        if new_path.exists() and any(new_path.iterdir()):
            sys.stderr.write(f"Migration refused: destination {new_path} already exists and is not empty\n")
            return 1
        if old_path.exists() and old_path != new_path:
            if new_path.exists() and not any(new_path.iterdir()):
                new_path.rmdir()
            print(f"mv {old_path} {new_path}")
            shutil.move(str(old_path), str(new_path))

    if shutil.which("uv") is None:
        sys.stderr.write("lp setup needs 'uv'; install it from https://docs.astral.sh/uv/\n")
        return 1

    if sys.platform == "darwin":
        lock_file = REPO_ROOT / "server" / "requirements.macos.txt"
        if not lock_file.is_file():
            lock_file = REPO_ROOT / "server" / "requirements-macos.txt"
    else:
        lock_file = REPO_ROOT / "server" / "requirements.linux.txt"
        if not lock_file.is_file():
            lock_file = REPO_ROOT / "server" / "requirements.txt"

    if not lock_file.is_file():
        sys.stderr.write(f"Lock file not found: {lock_file}\n")
        return 1

    layout = Layout.resolve()
    layout.ensure()

    lock_hash = hashlib.sha256(lock_file.read_bytes()).hexdigest()
    stamp_file = layout.venv / ".lock.sha256"
    current_stamp = stamp_file.read_text(encoding="utf-8").strip() if stamp_file.is_file() else ""
    venv_python = layout.venv / "bin" / "python"

    if not venv_python.is_file() or current_stamp != lock_hash:
        print(f"Setting up Python virtual environment in {layout.venv}...")
        res = subprocess.run(["uv", "venv", "--python", "3.12", "--allow-existing", str(layout.venv)])  # noqa: S607
        if res.returncode != 0:
            return res.returncode
        res = subprocess.run(
            ["uv", "pip", "sync", "--python", str(venv_python), "--require-hashes", str(lock_file)]  # noqa: S607
        )
        if res.returncode != 0:
            return res.returncode
        stamp_file.write_text(lock_hash + "\n", encoding="utf-8")

    index_html = REPO_ROOT / "web" / "dist" / "index.html"
    needs_build = not index_html.is_file()
    if not needs_build:
        dist_mtime = index_html.stat().st_mtime
        for sdir in (REPO_ROOT / "web" / "src", REPO_ROOT / "web" / "styles", REPO_ROOT / "web" / "vendor"):
            if sdir.is_dir():
                for p in sdir.rglob("*"):
                    if p.is_file() and p.stat().st_mtime > dist_mtime:
                        needs_build = True
                        break
            if needs_build:
                break

    if needs_build:
        web_dir = REPO_ROOT / "web"
        if not (web_dir / "node_modules").is_dir():
            if shutil.which("npm") is None:
                sys.stderr.write("Node.js with npm is needed to build the web UI\n")
                return 1
            print("Installing web dependencies...")
            res = subprocess.run(["npm", "ci", "--ignore-scripts"], cwd=str(web_dir))  # noqa: S607
            if res.returncode != 0:
                return res.returncode
        if shutil.which("npm") is None:
            sys.stderr.write("Node.js with npm is needed to build the web UI\n")
            return 1
        print("Building web UI...")
        res = subprocess.run(["npm", "run", "build"], cwd=str(web_dir))  # noqa: S607
        if res.returncode != 0:
            return res.returncode

    return 0


def cmd_up(argv: list[str]) -> int:
    """Start the supervisor in background (default) or foreground."""
    foreground = False
    no_matte = False
    for arg in argv:
        if arg == "--foreground":
            foreground = True
        elif arg == "--no-matte":
            no_matte = True
        else:
            sys.stderr.write(f"Invalid argument for up: {arg}\n{USAGE}")
            return 2

    layout = Layout.resolve()
    runtime_json = layout.data / "runtime.json"
    runtime_data = read_runtime(runtime_json)
    if runtime_data is not None and is_pid_alive(runtime_data["pid"]):
        url = runtime_data["url"]
        if is_healthy(f"{url}/health"):
            print(f"already running: {url}")
            return 0

    venv_python = layout.venv / "bin" / "python"
    index_html = REPO_ROOT / "web" / "dist" / "index.html"
    if not venv_python.is_file() or not index_html.is_file():
        code = cmd_setup([])
        if code != 0:
            return code

    cmd = [str(venv_python), "-m", "app.supervisor", "--port", "13305"]
    if no_matte:
        cmd.append("--no-matte")

    if foreground:
        res = subprocess.run(cmd, cwd=str(REPO_ROOT / "server"), env=child_env(layout))
        return res.returncode

    layout.ensure()
    runtime_log = layout.data / "runtime.log"
    with open(runtime_log, "a", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT / "server"),
            env=child_env(layout),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    deadline = time.monotonic() + 180.0
    noted_download = False
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            sys.stderr.write(f"Supervisor exited prematurely with code {proc.returncode}; see {runtime_log}\n")
            for line in tail(runtime_log, 20):
                sys.stderr.write(line)
            return 1

        rt = read_runtime(runtime_json)
        if rt is not None and is_pid_alive(rt["pid"]):
            url = rt["url"]
            if is_healthy(f"{url}/health"):
                print(f"ready: {url}")
                print(f"runtime log: {runtime_log}")
                try:
                    req = urllib.request.Request(f"{url}/v1/system", headers={"User-Agent": "local-producer-lp"})
                    with urllib.request.urlopen(req, timeout=2.0) as resp:
                        sys_data = json.loads(resp.read().decode("utf-8"))
                        engine = sys_data.get("engine", {})
                        engine_info = (
                            f"{engine.get('state', '')} {engine.get('id', '')} "
                            f"{engine.get('version', '')} {engine.get('problem', '')}".strip()
                        )
                        print(f"engine: {engine_info}")
                except (urllib.error.URLError, json.JSONDecodeError, OSError):
                    pass
                return 0

        if not noted_download and not no_matte and is_healthy("http://127.0.0.1:13305/health", timeout_s=0.5):
            print("server up; waiting for the matting model download (first start only, ~180 MB)")
            noted_download = True

        time.sleep(0.5)

    sys.stderr.write(f"Timed out waiting for server to become ready; see {runtime_log}\n")
    for line in tail(runtime_log, 20):
        sys.stderr.write(line)
    return 1


def cmd_down(argv: list[str]) -> int:
    """Stop the supervisor and all worker processes."""
    if argv:
        sys.stderr.write(f"Invalid arguments for down\n{USAGE}")
        return 2

    layout = Layout.resolve()
    runtime_json = layout.data / "runtime.json"
    runtime_data = read_runtime(runtime_json)
    if runtime_data is None:
        print("not running")
        return 0

    pid = runtime_data["pid"]
    url = runtime_data["url"]
    if not is_pid_alive(pid):
        print("stale pid removed")
        runtime_json.unlink(missing_ok=True)
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError as e:
        sys.stderr.write(f"Failed to signal supervisor: {e}\n")

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and is_pid_alive(pid):
        time.sleep(0.1)

    if is_pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    health_url = f"{url}/health"
    deadline_health = time.monotonic() + 5.0
    while time.monotonic() < deadline_health and is_healthy(health_url, timeout_s=0.5):
        time.sleep(0.1)

    current_rt = read_runtime(runtime_json)
    if current_rt is not None and current_rt.get("pid") == pid:
        runtime_json.unlink(missing_ok=True)

    print("stopped")
    return 0


def cmd_status(argv: list[str]) -> int:
    """Check the status of the local-producer server."""
    if argv:
        sys.stderr.write(f"Invalid arguments for status\n{USAGE}")
        return 2

    layout = Layout.resolve()
    runtime_json = layout.data / "runtime.json"
    runtime_data = read_runtime(runtime_json)
    if runtime_data is None:
        print("not running")
        return 1

    pid = runtime_data["pid"]
    url = runtime_data["url"]
    if not is_pid_alive(pid):
        print("not running")
        return 1

    if not is_healthy(f"{url}/health", timeout_s=2.0):
        print("not running")
        return 1

    try:
        req = urllib.request.Request(f"{url}/v1/system", headers={"User-Agent": "local-producer-lp"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            sys_data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        sys.stderr.write(f"Failed to query system info: {e}\n")
        return 1

    version = sys_data.get("version", "unknown")
    engine = sys_data.get("engine", {})
    engine_state = engine.get("state", "unknown")
    engine_id = engine.get("id", "none")
    engine_ver = engine.get("version", "")
    engine_prob = engine.get("problem", "")
    models_ready = sys_data.get("models_ready", False)

    print(f"running: {url} (pid {pid})")
    print(f"version: {version}")
    engine_line = f"engine: {engine_state} {engine_id} {engine_ver} {engine_prob}".strip()
    print(engine_line)
    print(f"models ready: {models_ready}")
    return 0


def cmd_logs(argv: list[str]) -> int:
    """Tail runtime.log or server.log."""
    lines = 200
    follow = False
    jobs = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--lines":
            if i + 1 >= len(argv):
                sys.stderr.write(f"Option --lines requires an argument\n{USAGE}")
                return 2
            try:
                lines = int(argv[i + 1])
            except ValueError:
                sys.stderr.write(f"Invalid number for --lines: {argv[i + 1]}\n{USAGE}")
                return 2
            i += 2
        elif arg.startswith("--lines="):
            try:
                lines = int(arg.split("=", 1)[1])
            except ValueError:
                sys.stderr.write(f"Invalid number for --lines\n{USAGE}")
                return 2
            i += 1
        elif arg in ("-f", "--follow"):
            follow = True
            i += 1
        elif arg == "--jobs":
            jobs = True
            i += 1
        else:
            sys.stderr.write(f"Invalid argument for logs: {arg}\n{USAGE}")
            return 2

    layout = Layout.resolve()
    target_log = layout.data / ("server.log" if jobs else "runtime.log")

    if not target_log.is_file():
        if follow:
            try:
                while not target_log.is_file():
                    time.sleep(0.2)
            except KeyboardInterrupt:
                return 0
        else:
            return 0

    log_lines = tail(target_log, n=lines)
    for line in log_lines:
        sys.stdout.write(line)
    sys.stdout.flush()

    if follow:
        try:
            with open(target_log, encoding="utf-8", errors="replace") as f:
                f.seek(0, os.SEEK_END)
                while True:
                    line = f.readline()
                    if line:
                        sys.stdout.write(line)
                        sys.stdout.flush()
                    else:
                        time.sleep(0.2)
        except KeyboardInterrupt:
            return 0

    return 0


def cmd_exec(argv: list[str]) -> int:
    """Execute a command in server/ using the virtualenv python and environment."""
    layout = Layout.resolve()
    venv_python = layout.venv / "bin" / "python"
    if not venv_python.is_file():
        code = cmd_setup([])
        if code != 0:
            return code

    os.chdir(str(REPO_ROOT / "server"))
    python_bin = str(venv_python)
    cmd = [python_bin, *argv]
    os.execvpe(python_bin, cmd, child_env(layout))  # noqa: S606


def cmd_doctor(argv: list[str]) -> int:
    """Check layout dirs, venv Python 3.12, web/dist, engine, models, disk, ports, sandbox."""
    if argv:
        sys.stderr.write(f"Invalid arguments for doctor\n{USAGE}")
        return 2

    failures = 0
    layout = Layout.resolve()

    # 1. Layout check
    try:
        layout.ensure()
        print(f"[ok] layout: {layout.root}")
    except OSError as e:
        print(f"[fail] layout: cannot create layout at {layout.root}: {e}")
        failures += 1

    # 2. Venv check
    venv_python = layout.venv / "bin" / "python"
    if not venv_python.is_file():
        print(f"[fail] venv: Python environment missing at {layout.venv}")
        print("       fix: run 'scripts/lp setup'")
        failures += 1
    else:
        test_py = "import fastapi, uvicorn; import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
        res = subprocess.run([str(venv_python), "-c", test_py], capture_output=True)
        if res.returncode == 0:
            print(f"[ok] venv: Python 3.12 with dependencies ({venv_python})")
        else:
            print(f"[fail] venv: virtual environment at {venv_python} is missing required dependencies")
            print("       fix: run 'scripts/lp setup'")
            failures += 1

    # 3. Web dist check
    index_html = REPO_ROOT / "web" / "dist" / "index.html"
    if index_html.is_file():
        print("[ok] web/dist: built (web/dist/index.html)")
    else:
        print("[fail] web/dist: web UI not built")
        print("       fix: run 'scripts/lp setup'")
        failures += 1

    # 4. Sandbox check
    if sys.platform == "darwin":
        if os.access("/usr/bin/sandbox-exec", os.X_OK):
            print("[ok] sandbox: macOS sandbox-exec available")
        else:
            print("[fail] sandbox: /usr/bin/sandbox-exec missing or not executable")
            failures += 1
    elif sys.platform.startswith("linux"):
        if shutil.which("bwrap") is not None:
            try:
                p = subprocess.run(
                    ["bwrap", "--unshare-net", "--dev-bind", "/", "/", "--", "true"],  # noqa: S607
                    capture_output=True,
                    timeout=5,
                )
                if p.returncode == 0:
                    print("[ok] sandbox: bubblewrap (bwrap) available and functional")
                else:
                    print(f"[fail] sandbox: bwrap probe failed (rc={p.returncode})")
                    print("       fix: verify bubblewrap permissions or install bubblewrap")
                    failures += 1
            except Exception as e:
                print(f"[fail] sandbox: bwrap probe failed ({e})")
                print("       fix: apt install bubblewrap")
                failures += 1
        else:
            print("[fail] sandbox: bwrap is missing (apt install bubblewrap)")
            failures += 1
    else:
        print(f"[fail] sandbox: no sandbox implemented for {sys.platform}")
        failures += 1

    # 5. Engine preflight
    if sys.platform == "darwin":
        if platform.machine() == "arm64":
            print("[ok] engine preflight: Apple silicon (arm64 Metal supported)")
        else:
            print("[warn] engine preflight: Intel Mac detected (Metal GPU engine package requires Apple silicon)")
    elif sys.platform.startswith("linux"):
        cwsr_path = Path("/sys/module/amdgpu/parameters/cwsr_enable")
        if cwsr_path.exists():
            try:
                val = cwsr_path.read_text().strip()
                if val == "0":
                    print("[ok] engine preflight: amdgpu cwsr_enable=0 verified")
                else:
                    print("[fail] engine preflight: /sys/module/amdgpu/parameters/cwsr_enable is not 0")
                    print("       fix: add 'options amdgpu cwsr_enable=0' to /etc/modprobe.d/amdgpu-cwsr.conf")
                    failures += 1
            except OSError as e:
                print(f"[warn] engine preflight: cannot read {cwsr_path}: {e}")
        else:
            print("[ok] engine preflight: Linux host verified")
    else:
        print(f"[warn] engine preflight: unsupported OS {sys.platform}")

    # 6. Models check
    if layout.models.is_dir() and any(layout.models.iterdir()):
        print(f"[ok] models: directory {layout.models} has files")
    else:
        print(f"[warn] models: no models installed in {layout.models}")
        print("       hint: run 'make setup' or download via web UI")

    # 7. Disk space check
    try:
        usage = shutil.disk_usage(layout.root)
        free_gb = usage.free / (1024**3)
        if free_gb < 2.0:
            print(f"[warn] disk space: low disk space ({free_gb:.1f} GB free on {layout.root})")
        else:
            print(f"[ok] disk space: {free_gb:.1f} GB free")
    except OSError as e:
        print(f"[warn] disk space: cannot check disk usage: {e}")

    # 8. Ports check
    running_rt = read_runtime(layout.data / "runtime.json")
    if running_rt is not None and is_pid_alive(running_rt["pid"]) and is_healthy(f"{running_rt['url']}/health"):
        print(f"[ok] ports: server currently active on {running_rt['url']}")
    else:
        p13305 = port_free(13305)
        p8083 = port_free(8083)
        if p13305 and p8083:
            print("[ok] ports: 13305 and 8083 are available")
        else:
            if not p8083:
                print("[fail] ports: matting port 8083 is already in use by another process")
                failures += 1
            if not p13305:
                print("[warn] ports: port 13305 is in use; an ephemeral port will be selected")

    return 1 if failures > 0 else 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch CLI arguments to command handlers."""
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        sys.stderr.write(USAGE)
        return 2

    cmd = argv[0]
    args = argv[1:]

    if cmd == "root":
        return cmd_root(args)
    if cmd == "setup":
        return cmd_setup(args)
    if cmd == "up":
        return cmd_up(args)
    if cmd == "down":
        return cmd_down(args)
    if cmd == "status":
        return cmd_status(args)
    if cmd == "logs":
        return cmd_logs(args)
    if cmd == "exec":
        return cmd_exec(args)
    if cmd == "doctor":
        return cmd_doctor(args)

    sys.stderr.write(f"Unknown command: {cmd}\n{USAGE}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
