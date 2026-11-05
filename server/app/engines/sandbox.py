"""Engine process sandboxing (macOS sandbox-exec, Linux bwrap) to isolate engine CLIs from network."""

import os
import shutil
import subprocess

from .host import HostInfo

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
SANDBOX_PROFILE = "(version 1)(allow default)(deny network*)"
BWRAP_PREFIX: tuple[str, ...] = ("bwrap", "--unshare-net", "--dev-bind", "/", "/", "--")

_linux_probe_cache: str | None = None


def reset_cache() -> None:
    """Reset the cached Linux probe result (used in tests)."""
    global _linux_probe_cache
    _linux_probe_cache = None


def problem(host: HostInfo) -> str:
    """Return "" when engine CLIs may run sandboxed on this machine, or an actionable reason why not."""
    global _linux_probe_cache
    if host.os == "macos":
        if not os.access(SANDBOX_EXEC, os.X_OK):
            return f"{SANDBOX_EXEC} is missing or not executable; running engine CLIs unsandboxed is refused"
        return ""
    if host.os == "linux":
        if _linux_probe_cache is not None:
            return _linux_probe_cache
        if shutil.which("bwrap") is None:
            res = "bwrap is missing (apt install bubblewrap); running engine CLIs unsandboxed needs written approval"
            _linux_probe_cache = res
            return res
        try:
            p = subprocess.run(
                ["bwrap", "--unshare-net", "--dev-bind", "/", "/", "--", "true"],  # noqa: S607
                capture_output=True,
                timeout=5,
            )
            if p.returncode == 0:
                res = ""
            else:
                res = f"bwrap probe failed (rc={p.returncode}); running engine CLIs unsandboxed needs written approval"
        except subprocess.TimeoutExpired:
            res = "bwrap probe timed out; running engine CLIs unsandboxed needs written approval"
        except OSError as e:
            res = f"bwrap probe failed ({e}); running engine CLIs unsandboxed needs written approval"
        _linux_probe_cache = res
        return res
    return f"no engine sandbox is implemented for {host.os}; running engine CLIs unsandboxed is refused"


def prefix(host: HostInfo) -> tuple[str, ...]:
    """What every engine CLI is started under on this machine."""
    if host.os == "macos" and os.access(SANDBOX_EXEC, os.X_OK):
        return (SANDBOX_EXEC, "-p", SANDBOX_PROFILE)
    if host.os == "linux":
        return BWRAP_PREFIX if not problem(host) else ()
    return ()
