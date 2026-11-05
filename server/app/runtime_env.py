"""Runtime environment resolution, filesystem layout, and child process environment.

Standard library only: this module is imported by scripts/lp before the server's
virtual environment exists.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def data_root(platform: str | None = None) -> Path:
    """Return the base data root directory according to platform conventions.

    Precedence:
    1. $LP_HOME if set (expanded and resolved).
    2. macOS: ~/Library/Application Support/local-producer.
    3. Linux/other: ${XDG_DATA_HOME:-~/.local/share}/local-producer.
    """
    lp_home = os.environ.get("LP_HOME")
    if lp_home:
        return Path(os.path.expanduser(lp_home)).resolve()

    target_platform = platform if platform is not None else sys.platform
    if target_platform == "darwin":
        return Path("~/Library/Application Support/local-producer").expanduser().resolve()

    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(os.path.expanduser(xdg)).resolve() if xdg else Path("~/.local/share").expanduser().resolve()
    return (base / "local-producer").resolve()


@dataclass(frozen=True)
class Layout:
    """Filesystem layout for server runtime, models, engines, and user data."""

    root: Path
    models: Path
    engines: Path
    library: Path
    data: Path
    venv: Path

    @classmethod
    def resolve(cls, root: Path | None = None) -> Layout:
        """Resolve all directory paths from a specified root or default data_root()."""
        resolved_root = data_root() if root is None else Path(os.path.expanduser(str(root))).resolve()
        return cls(
            root=resolved_root,
            models=resolved_root / "models",
            engines=resolved_root / "engines",
            library=resolved_root / "library",
            data=resolved_root / "server",
            venv=resolved_root / "venv",
        )

    def ensure(self) -> None:
        """Create all layout directories if missing and enforce secure permissions on data."""
        for p in (self.root, self.models, self.engines, self.library, self.data, self.venv):
            p.mkdir(parents=True, exist_ok=True)
        os.chmod(self.data, 0o700)


def thread_count(platform: str | None = None) -> int:
    """Return the physical compute thread count for the platform.

    On macOS, queries `hw.perflevel0.physicalcpu` (performance cores) via sysctl.
    On Linux, queries sched_getaffinity capped at 8 (matching the container baseline).
    Falls back to `os.cpu_count() or 1`. Never returns <= 0.
    """
    target_platform = platform if platform is not None else sys.platform
    if target_platform == "darwin":
        try:
            sysctl_cmd = "/usr/sbin/sysctl" if os.path.exists("/usr/sbin/sysctl") else "sysctl"
            res = subprocess.run(
                [sysctl_cmd, "-n", "hw.perflevel0.physicalcpu"],
                capture_output=True,
                text=True,
                check=True,
                timeout=2,
            )
            count = int(res.stdout.strip())
            if count > 0:
                return count
        except (subprocess.SubprocessError, ValueError, OSError):
            pass
    elif target_platform.startswith("linux"):
        try:
            if hasattr(os, "sched_getaffinity"):
                count = min(8, len(os.sched_getaffinity(0)))
                if count > 0:
                    return count
        except (OSError, ValueError):
            pass

    count = os.cpu_count() or 1
    return max(1, count)


def child_env(layout: Layout, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Produce the child process environment for native server and workers.

    Sets standard local-producer layout paths and performance flags.
    Preserves existing keys such as SERVER_TOKEN.
    """
    env = dict(base) if base is not None else os.environ.copy()
    env["MODELS_DIR"] = str(layout.models)
    env["ENGINES_DIR"] = str(layout.engines)
    env["LIBRARY_DIR"] = str(layout.library)
    env["DATA_DIR"] = str(layout.data)
    env["U2NET_HOME"] = str(layout.models / "rembg")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["OMP_NUM_THREADS"] = str(thread_count())
    env["HOST_MODELS"] = str(layout.models)
    env["HOST_ENGINES"] = str(layout.engines)
    env["HOST_LIBRARY"] = str(layout.library)
    env["HOST_DATA"] = str(layout.data)
    return env
