"""What this machine is: OS, CPU architecture, and the GPU compute stack an engine package must target.

Inside the container the GPU is visible through the devices passed in (scripts/run-server.sh) and /sys. On macOS the
server runs natively (containers cannot reach Metal) and the GPU is the Apple silicon chip's own.
"""

import glob
import os
import platform
import subprocess
from typing import Literal

from ..schemas import ApiModel

Accelerator = Literal["rocm", "cuda", "metal", "cpu"]
KFD_NODES = "/sys/class/kfd/kfd/topology/nodes"


class HostInfo(ApiModel):
    os: str
    arch: str
    accelerator: Accelerator
    gpu: str
    gpu_targets: list[str]


def gfx_name(version: int) -> str:
    """KFD's gfx_target_version (major*10000 + minor*100 + stepping) as an LLVM target: 110003 -> gfx1103,
    90010 -> gfx90a."""
    major, minor, stepping = version // 10000, version // 100 % 100, version % 100
    return f"gfx{major}{minor}{stepping:x}"


def amd_targets(nodes: str = KFD_NODES) -> list[str]:
    """The gfx targets of the GPU nodes the ROCm driver exposes (CPU nodes report 0)."""
    targets: list[str] = []
    for props in sorted(glob.glob(f"{nodes}/*/properties")):
        try:
            with open(props) as f:
                fields = dict(line.split(maxsplit=1) for line in f if " " in line)
        except OSError:
            continue
        version = int(fields.get("gfx_target_version", "0").strip() or 0)
        if version and gfx_name(version) not in targets:
            targets.append(gfx_name(version))
    return targets


def apple_chip() -> str:
    """The chip's marketing name, e.g. "Apple M4", or "Apple GPU" when sysctl cannot tell."""
    try:
        out = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    return out or "Apple GPU"


def detect() -> HostInfo:
    system = platform.system().lower()
    arch = platform.machine().lower()
    arch = {"amd64": "x86_64", "aarch64": "arm64"}.get(arch, arch)
    if system == "darwin":
        if arch == "arm64":  # every Apple silicon Mac has Metal; Intel Macs are not supported
            return HostInfo(os="macos", arch=arch, accelerator="metal", gpu=apple_chip(), gpu_targets=[])
        return HostInfo(os="macos", arch=arch, accelerator="cpu", gpu="none supported", gpu_targets=[])
    if os.path.exists("/dev/kfd"):
        targets = amd_targets()
        if targets:
            return HostInfo(
                os=system, arch=arch, accelerator="rocm", gpu=f"AMD {', '.join(targets)}", gpu_targets=targets
            )
    if os.path.exists("/dev/nvidiactl") or os.path.exists("/proc/driver/nvidia/version"):
        return HostInfo(os=system, arch=arch, accelerator="cuda", gpu="NVIDIA", gpu_targets=[])
    return HostInfo(os=system, arch=arch, accelerator="cpu", gpu="none found", gpu_targets=[])
