# 0004. One baseline engine artifact per OS, compatibility decided by a scan

| | |
| :--- | :--- |
| **Status** | Accepted — implementation starts in P2 |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Date** | 2026-11-05 |

## Context

The engine packages are the GPU-facing binaries: stable-diffusion.cpp (`sd-cli`), trellis.cpp (`trellis-cli`) and the
ROCm runtime. Today the Linux package is a pinned upstream build; the macOS package downloads sources and **compiles**
them on the user's machine with CMake and the Xcode Command Line Tools, using `GGML_NATIVE=ON`. That is incompatible
with a desktop app: a user who installs a DMG does not expect to need a compiler, and a binary tuned to the build
machine's CPU is not a safe thing to hand to every Mac.

The obvious alternative — ship one artifact per chip or per GPU — multiplies the build and QA matrix for a gain nobody
has measured. The reference Linux machine is one iGPU (`gfx1103`); the reference Mac is one chip (M4).

## Decision

We publish **one baseline artifact per OS**, built in CI, and decide compatibility at run time by scanning the machine
the way LM Studio does.

- **Artifact**: built without `GGML_NATIVE`, pinned in `server/catalog/engines.json` by URL, size, SHA256 and an
  Ed25519 signature. No chip-tuned variants in v1.
- **Claims**: each catalog item declares what it requires and what it can do — `gfx_targets`, `min_glibc`,
  `min_macos`, `features`, and any known `max_res`.
- **Scan**: `server/app/engines/compat.py` probes GPU, driver, kernel/userspace stack, glibc, OS version, required
  kernel parameters and device access, then returns one verdict per installed package:
  **compatible** (the checks passed, and it says what was detected), **degraded** (runs with a stated limit; jobs above
  the limit are refused with the reason), or **incompatible** (exactly one blocking reason plus a remediation).
- **No guessing**: a field that cannot be read is `unknown`, and `unknown` on a required field is `incompatible`.
- **The verdict is data**: it is written to `preflight.json`, shown on the splash and the Engines page, and repeated
  in job error messages, so a bug report carries it.
- **Tests use recorded fixtures** (ioreg/sysfs dumps from the M4, the 780M and one unsupported machine), not the CI
  machine.

## Consequences

- A clean Mac installs the engine with no CMake, no Xcode Command Line Tools, and no local compile.
- Users on GPU or chip combinations the artifact does not claim get an explanation instead of a crash. This is the
  point: with one artifact, a wrong verdict affects everyone, so the scan is a first-class module with tests.
- The baseline build is possibly slower than the current locally tuned one. That difference must be **measured once**
  (same input, seed and resolution, n >= 3) and recorded in `CHANGELOG.md`. It is not assumed to be zero, and it is
  not a reason to quietly produce a second artifact.
- A baseline binary must run on older Apple silicon (M1/M2/M3), not only on the CI machine's chip. A crash or illegal
  instruction there is a release-blocking bug.
- CI gains a build-and-publish job per OS, and the catalog gains signature fields.

## Alternatives considered

- **Per-chip / per-GPU artifacts**: rejected for v1 — unmeasured gain, multiplied QA matrix, and the scan would still
  be needed to choose between them.
- **Compile on the user's machine (today's macOS path)**: rejected — requires a toolchain the desktop user does not
  have and produces a non-reproducible binary.
- **A Vulkan fallback package for Linux**: deferred — it would run, but res 1024 already exceeds the 2 s GPU lockup
  timeout on Vulkan. The scan already models "degraded with `max_res`", so adding it later is a catalog entry, not new
  code. It waits for a report showing `incompatible` happens in practice.
- **Shipping nothing and telling users to install ROCm themselves**: rejected — that is the container-era assumption
  that engine packages exist to remove.

## What would reopen this

The baseline measurement showing a difference large enough to justify a second artifact, or a pattern of
`incompatible` verdicts on real machines (reports, since there is no telemetry) — the latter would first add the
Vulkan package, and only after that a variant.
