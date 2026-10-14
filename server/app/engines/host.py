"""What this machine is: OS, CPU architecture, and the GPU compute stack an engine package must target.

Inside the container the GPU is visible through the devices passed in (scripts/run-server.sh) and /sys.
"""

import glob
import os
import platform
from typing import Literal

from ..schemas import ApiModel

Accelerator = Literal["rocm", "cuda", "mlx", "cpu"]
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


def detect() -> HostInfo:
    system = platform.system().lower()
    arch = platform.machine().lower()
    arch = {"amd64": "x86_64", "aarch64": "arm64"}.get(arch, arch)
    if system == "darwin":
        return HostInfo(
            os="macos", arch=arch, accelerator="mlx" if arch == "arm64" else "cpu", gpu="Apple GPU", gpu_targets=[]
        )
    if os.path.exists("/dev/kfd"):
        targets = amd_targets()
        if targets:
            return HostInfo(
                os=system, arch=arch, accelerator="rocm", gpu=f"AMD {', '.join(targets)}", gpu_targets=targets
            )
    if os.path.exists("/dev/nvidiactl") or os.path.exists("/proc/driver/nvidia/version"):
        return HostInfo(os=system, arch=arch, accelerator="cuda", gpu="NVIDIA", gpu_targets=[])
    return HostInfo(os=system, arch=arch, accelerator="cpu", gpu="none found", gpu_targets=[])
