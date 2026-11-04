"""Per-stack code that ships with the server (never with a package): checks that must pass before a package's GPU
code may run, and how to read the GPU memory in use. ROCm and Metal are implemented; CUDA packages are planned."""

import glob
import platform
import re
import subprocess

from .host import Accelerator

CWSR = "/sys/module/amdgpu/parameters/cwsr_enable"
IOREG = "/usr/sbin/ioreg"
# The Apple GPU driver's counters (AGXAccelerator PerformanceStatistics): bytes of unified memory the GPU uses now.
IN_USE_RE = re.compile(r'"In use system memory"=(\d+)')


def cwsr_enable() -> str | None:
    try:
        with open(CWSR) as f:
            return f.read().strip()
    except OSError:
        return None


def preflight(accelerator: Accelerator) -> str:
    """Why a package for this stack must not run on this machine now, or "" when it may."""
    if accelerator == "rocm":
        # With CWSR on, gfx1103 HIP jobs failed intermittently and reset the GPU (CHANGELOG 2026-10-14).
        value = cwsr_enable()
        if value is not None and value != "0":
            return (
                f"amdgpu cwsr_enable is {value}; HIP jobs would reset the GPU intermittently. Set it to 0 (README.md)"
            )
        return ""
    if accelerator == "metal":
        # Containers cannot reach Metal: a Metal package only runs in the native server on Apple silicon.
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            return "Metal engines run only in the native server on Apple silicon (scripts/run-server.sh on macOS)"
        return ""
    return f"{accelerator} engines are not supported by this server version yet"


def apple_gpu_memory(ioreg: str = IOREG) -> int | None:
    """Unified memory the Apple GPU has in use (the driver's "In use system memory"), or None."""
    try:
        out = subprocess.run(
            [ioreg, "-r", "-d", "1", "-c", "IOAccelerator"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = IN_USE_RE.search(out)
    return int(m.group(1)) if m else None


def gpu_memory() -> int | None:
    """GPU memory in use on the whole machine (not only this container), or None: amdgpu GTT + VRAM on Linux, the
    Apple GPU's unified memory on macOS."""
    if platform.system() == "Darwin":
        return apple_gpu_memory()
    for d in glob.glob("/sys/class/drm/card*/device"):
        try:
            with open(f"{d}/mem_info_gtt_used") as g, open(f"{d}/mem_info_vram_used") as v:
                return int(g.read()) + int(v.read())
        except OSError:
            continue
    return None
