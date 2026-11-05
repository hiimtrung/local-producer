# 0002. One native runtime, no containers

| | |
| :--- | :--- |
| **Status** | Accepted — implementation starts in P1 |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Date** | 2026-11-05 |

## Context

The GPU server grew two runtimes. On Linux it ran in a rootless Podman container: the image pinned Python 3.12 and
`libnuma1 libdrm2 libelf1 libgomp1`, passed `/dev/kfd` and `/dev/dri` through with `keep-groups`, and gave engine
CLIs `--network none`. On macOS it ran natively, because a container cannot reach Metal. That meant two startup
scripts (`run-server.sh`, `run-native.sh`), two environment mechanisms (`lp-env.sh` plus Podman volume mounts versus
plain directories), two sets of Python requirements, and a class of bugs that only appeared on one side.

The container also carried real value: hermetic system libraries, a reproducible Python version, and network
isolation for generated/downloaded binaries. Removing it is only defensible if each of those is replaced by a named
mechanism rather than silently dropped.

## Decision

We run one native runtime on both platforms. There is no container in the desktop product, the development setup, or
CI.

- **Python**: `uv` creates a virtual environment from `python-build-standalone`, pinned by version and hash, so the
  interpreter does not depend on the distro or on Xcode.
- **Layout**: every path comes from one function, `data_root()` — a plain directory tree (`models/`, `engines/`,
  `library/`, `server/`) with the same names on both platforms, no volume indirection.
- **Lifecycle**: one supervisor starts, health-checks, restarts and stops the server and its child CLI processes,
  and writes `<data>/runtime.json` (port, pid, token) for other processes to discover.
- **Engine packages**: still downloaded artifacts, not something the user compiles (see
  [0004](./0004-one-baseline-artifact-and-compat-scan.md)).
- **Isolation**: network isolation for engine CLIs moves from `--network none` to a per-platform sandbox
  (`sandbox-exec` on macOS, `bwrap` then Landlock on Linux), with the policy stated in `SECURITY.md`.
- **Hermeticity**: system library and glibc requirements become an explicit preflight check with a readable verdict,
  and `.deb` dependency metadata on Linux, instead of an image layer.

## Consequences

- One code path, one set of paths, one startup script, one set of requirements to keep working. Bugs stop being
  platform-shaped by construction.
- **The filesystem isolation of the container is gone on both platforms.** Engine CLIs can read and write as the user
  can. This is the honest cost; it is recorded in `SECURITY.md` and mitigated, not hidden.
- **Network isolation must be proven on Linux**, where unprivileged user namespaces are restricted. The fallback order
  and the approval requirement are stated in the architecture analysis; the degraded mode is not silent.
- A user's system libraries become part of the support surface. The preflight must name a missing package instead of
  failing inside a dylib.
- CI must run natively on `ubuntu-24.04` and `macos-14`; a container-based job can no longer prove the product works.

## Alternatives considered

- **Keep the container on Linux, native on macOS**: rejected — it is exactly the duplication this ADR removes, and the
  container cannot be the shipped desktop experience anyway.
- **Container on macOS through a Linux VM**: rejected — the GPU (Metal) is unreachable, so the image path would run on
  the CPU.
- **Conda or system Python instead of `uv`**: rejected — both depend on the machine's state; a pinned standalone
  interpreter is the closest replacement for the container's fixed Python.
- **Flatpak/AppImage as the runtime**: rejected — packaging formats do not provide the process supervision, the data
  root or the engine packages; they only change how files are delivered.

## What would reopen this

A security incident that the per-platform sandbox cannot contain, or Linux distributions where neither `bwrap` nor
Landlock works *and* the degraded mode is refused. Either would justify revisiting a container or a micro-VM for the
engine CLIs only — not for the server.
