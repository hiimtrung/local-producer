"""Running one GPU CLI process at a time, with its output logged and GPU memory measured before and after.

Every GPU job is its own process (sd-cli / trellis-cli from the loaded engine package, app/engines/), so all its GPU
memory is released when it exits: FLUX.2 is gone before TRELLIS.2 starts (CHANGELOG 2026-10-14). The lock keeps jobs
from overlapping even if a caller bypasses the job queue (the Lemonade-compatible endpoints wait on the same queue).
"""

import os
import subprocess
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from .engines.backends import gpu_memory
from .settings import paths

if TYPE_CHECKING:
    from .engines.registry import Runner

gpu_lock = threading.Lock()
_log_lock = threading.Lock()


class JobFailed(RuntimeError):
    pass


class JobCancelled(RuntimeError):
    pass


def log(line: str) -> None:
    """Append a line to <data>/server.log (the add-on's "Server Log" tails it)."""
    os.makedirs(paths.data, exist_ok=True)
    with _log_lock, open(paths.log, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line.rstrip()}\n")


def gpu_mem() -> int | None:
    """GPU memory in use on the whole machine, or None when this machine has no probe."""
    return gpu_memory()


def gib(n: int | None) -> str:
    return "?" if n is None else f"{n / 2**30:.2f} GiB"


def run_cli(
    kind: str,
    runner: "Runner",
    args: list[str],
    timeout: float,
    on_line: Callable[[str], None] | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Run the engine runner with args under the GPU lock. Streams each output line to the log (Lemonade's
    "[Info] (Process)" format, which the add-on's progress parser strips) and to on_line. Raises JobFailed /
    JobCancelled."""
    with gpu_lock:
        before = gpu_mem()
        cmd = [runner.bin, *args]
        log(f"== job {kind} start ({runner.package}), GPU memory in use {gib(before)}")
        log("   " + " ".join(cmd))
        t0 = time.time()
        p = subprocess.Popen(
            cmd,
            env=runner.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            errors="replace",
        )
        stop = threading.Event()

        def watchdog() -> None:
            while not stop.wait(0.5):
                if (cancel is not None and cancel.is_set()) or time.time() - t0 > timeout:
                    p.kill()
                    return

        threading.Thread(target=watchdog, daemon=True).start()
        tail: list[str] = []
        try:
            if p.stdout is None:  # unreachable with stdout=PIPE; narrows the type
                raise JobFailed("the CLI has no output pipe")
            for raw in p.stdout:
                for line in raw.replace("\r", "\n").split("\n"):
                    if not line.strip():
                        continue
                    log(f"[Info] (Process) {line}")
                    tail = [*tail, line.rstrip()][-20:]
                    if on_line:
                        on_line(line)
            rc = p.wait()
        finally:
            stop.set()
        after = gpu_mem()
        for _ in range(20):  # the driver frees the process' buffers shortly after exit
            if after is None or before is None or after < before + 2**30:
                break
            time.sleep(0.25)
            after = gpu_mem()
        log(
            f"== job {kind} end rc={rc} in {time.time() - t0:.1f} s, GPU memory in use {gib(before)} -> "
            f"{gib(after)} after the process exited"
        )
        if cancel is not None and cancel.is_set():
            raise JobCancelled("cancelled")
        if time.time() - t0 > timeout:
            raise JobFailed(f"timed out after {timeout} s")
        if rc != 0:
            raise JobFailed(f"{kind} failed (rc={rc}): " + " | ".join(tail[-5:]))
