"""Per-stack code that ships with the server (never with a package): checks that must pass before a package's GPU
code may run, and how to read the GPU memory in use. Only ROCm is implemented; CUDA and MLX packages are planned."""

import glob

from .host import Accelerator

CWSR = "/sys/module/amdgpu/parameters/cwsr_enable"


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
    return f"{accelerator} engines are not supported by this server version yet"


def gpu_memory() -> int | None:
    """GTT + VRAM bytes in use on the amdgpu device (whole machine, not only this container), or None."""
    for d in glob.glob("/sys/class/drm/card*/device"):
        try:
            with open(f"{d}/mem_info_gtt_used") as g, open(f"{d}/mem_info_vram_used") as v:
                return int(g.read()) + int(v.read())
        except OSError:
            continue
    return None
