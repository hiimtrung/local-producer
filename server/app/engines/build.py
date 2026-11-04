"""Build steps of an engine package (catalog.BuildSpec): CMake configures and builds the pinned, verified sources on
this machine, the outputs are copied into the package and the sources deleted.

The full compiler output goes to <data>/engine-build.log; the install progress shows one line per phase and, on a
failure, the last lines of the output. A build runs with the server's own environment, no shell, and a time limit.
"""

import os
import platform
import shutil
import subprocess
import time
from collections.abc import Callable

from ..model_setup import SetupError
from ..settings import paths
from .catalog import BuildSpec, PackageSpec

BUILD_TIMEOUT = 3600
Log = Callable[[str], None]


def missing_tools() -> str:
    """Why this machine cannot build a package from source, or "". Checked before anything is downloaded."""
    if shutil.which("cmake") is None:
        hint = "brew install cmake" if platform.system() == "Darwin" else "install cmake"
        return f"building this package needs CMake, which is not on PATH ({hint})"
    if platform.system() == "Darwin":
        # /usr/bin/c++ exists even without the tools (it opens an install dialog), so ask xcode-select instead
        try:
            ok = subprocess.run(["/usr/bin/xcode-select", "-p"], capture_output=True, timeout=10).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        if not ok:
            return "building this package needs the Xcode Command Line Tools (xcode-select --install)"
    elif shutil.which("c++") is None:
        return "building this package needs a C++ compiler (c++ on PATH)"
    return ""


def _run(cmd: list[str], log_path: str, deadline: float) -> list[str]:
    """Run cmd, appending its output to log_path; return the last lines. Raises SetupError on failure."""
    tail: list[str] = []
    with open(log_path, "a") as log:
        log.write(f"$ {' '.join(cmd)}\n")
        log.flush()
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        if p.stdout is None:  # unreachable with stdout=PIPE; narrows the type
            raise SetupError("the build has no output pipe")
        for line in p.stdout:
            log.write(line)
            tail = [*tail, line.rstrip()][-15:]
            if time.time() > deadline:
                p.kill()
                p.wait()
                raise SetupError(f"build timed out after {BUILD_TIMEOUT} s; see {log_path}")
        rc = p.wait()
    if rc != 0:
        raise SetupError(f"build failed (rc={rc}): {' | '.join(tail[-5:])}; full output in {log_path}")
    return tail


def build_one(b: BuildSpec, root: str, log: Log, jobs: int | None = None) -> None:
    src = os.path.join(root, b.source)
    if not os.path.isfile(os.path.join(src, "CMakeLists.txt")):
        raise SetupError(f"build {b.id}: no CMakeLists.txt in {b.source}")
    out = os.path.join(src, "build")
    os.makedirs(paths.data, exist_ok=True)
    log_path = os.path.join(paths.data, "engine-build.log")
    deadline = time.time() + BUILD_TIMEOUT
    log(f"build {b.id}: configure (output in {log_path})")
    _run(["cmake", "-S", src, "-B", out, "-DCMAKE_BUILD_TYPE=Release", *b.cmake_args], log_path, deadline)
    n = str(jobs or os.cpu_count() or 4)
    t0 = time.time()
    log(f"build {b.id}: compile {', '.join(b.targets)} with {n} jobs")
    _run(["cmake", "--build", out, "--target", *b.targets, "-j", n], log_path, deadline)
    log(f"build {b.id}: done in {time.time() - t0:.0f} s")
    for rel_src, rel_dst in b.outputs.items():
        built = os.path.join(out, rel_src)
        if not os.path.isfile(built):
            raise SetupError(f"build {b.id}: {rel_src} was not produced")
        dst = os.path.join(root, rel_dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(built, dst)
        os.chmod(dst, 0o755)  # noqa: S103  the built CLI must be executable


def build_package(spec: PackageSpec, root: str, log: Log, jobs: int | None = None) -> None:
    """Run every build step of spec inside the staged package at root, then delete the sources."""
    for b in spec.build:
        build_one(b, root, log, jobs)
    for b in spec.build:
        shutil.rmtree(os.path.join(root, b.source), ignore_errors=True)
