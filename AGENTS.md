# AGENTS.md — Working conventions for the local-producer project

The project produces science/engineering explainer videos from Obsidian notes, in the language requested for each video (Vietnamese is the first and so far only tested language; TTS, subtitles and on-screen text must not be hard-wired to one language). It is in the **R&D phase**: the native runtime (milestone P1) is settled, the video pipeline is not (see `docs/architecture/overview.md` and `CHANGELOG.md`). The archived spec `docs/archive/local-producer-v2.1.md` (v2.1) describes the old state; its local-LLM and Blender A-roll parts are outdated.

## How to work
- **Contribution rules:** `CONTRIBUTING.md` (setup with `make dev`, `scripts/lp setup`, `make check` before every change, Conventional Commits, small PRs) and `SECURITY.md` (threat model; never weaken a rule without explicit approval). Only source goes into git; weights, engine binaries, results and logs live in the native data root (`docs/reference/storage.md`).
- **R&D: do not hesitate to tear down and redo.** Delete a failed experiment instead of patching it to keep it alive.
- **Every meaningful experiment must be recorded in `CHANGELOG.md`** as soon as it finishes: goal, configuration, numbers, conclusion. Experiment directories may be deleted; the changelog is not.
- **Measure, do not estimate.** Do not put temperatures, speeds or sizes in documents unless they were measured. State the sample size and the noise; if a difference is within the noise, say it cannot be distinguished.
- Keep facts separate from hypotheses: a cause that has not been proven must be written as a hypothesis.
- **Everything in this project directory must be in English, now and in the future:** documents, the changelog, code, comments, identifiers, commit messages, log/error messages, prompts and config files, so any agent can read them. Chat replies to the user may be in Vietnamese, but never write Vietnamese into project files.
- Only exception: video content that must be in the video's own language (narration, on-screen text, TTS test sentences; Vietnamese so far). Examples in documents use English (e.g. the sample `script.json` in `docs/archive/local-producer-v2.1.md`). Keep such strings minimal and add an English gloss next to them.
- Ask before deleting data outside the project directory or doing anything irreversible (deleting downloaded volumes/models that are not part of this project, removing system packages). Inside the project directory you are free to tear down and redo, except the root `.md` files.

## Hardware constraints (measured, see CHANGELOG)
- Second machine (2026-11-03): Apple M4 (4P+6E cores, 10-core GPU), 16 GiB unified memory, macOS 27.2: the native server with the `metal-arm64` engine package (Metal via ggml). GPU memory = the driver's "In use system memory" (`ioreg`), shared with the CPU, so FLUX.2 and TRELLIS.2 compete with everything else in 16 GiB. Measured (CHANGELOG 2026-11-03): FLUX.2 1024^2 / 4 steps ~121-125 s at 8.6 GiB peak, TRELLIS.2 q8 res 512 / 6 steps ~300 s at 2.1 GiB, end to end 9.35 GiB peak; VAE tiles above 256 wash the colours out here too.
- Reference machine: Ryzen 7 PRO 7840U, Radeon 780M (gfx1103, iGPU, uses ~30 GiB GTT), 60 GiB RAM, Ubuntu 26.04. No passwordless sudo.
- **GPU compute: ROCm/HIP for image and 3D generation (decided 2026-10-14), Vulkan for the local LLM (`vulkan-llama-cpp`).** The host has AMD's ROCm 10.1 for gfx1103 (`amdrocm10.1-gfx1103`, `/opt/rocm/core-10.1`; Ubuntu's `rocm` 7.1 was purged; Blender's Cycles HIP device uses it, so an open Blender is a ROCm/KFD client) and **`options amdgpu cwsr_enable=0` in `/etc/modprobe.d/amdgpu-cwsr.conf`, which all HIP work assumes** (check `/sys/module/amdgpu/parameters/cwsr_enable` = 0; the ROCm engine package is not loaded otherwise: `server/app/engines/backends.py`. With CWSR on, gfx1103 HIP jobs failed intermittently (launch failure -> `MES failed to respond` -> GPU reset; PyTorch and sd.cpp alike, 4 of 8 sd.cpp FLUX.2 runs); with it off ~20 consecutive jobs passed with 0 resets (CHANGELOG 2026-10-14). Without CWSR, waves cannot be preempted: watch desktop responsiveness during long jobs. `AMD_SERIALIZE_KERNEL=3` stays set (no measured cost). PyTorch on ROCm (P0-P2, deleted) also needed MIOpen disabled: its first-use conv search timed out the desktop's gfx ring. Vulkan (RADV) cannot run TRELLIS.2 at res 1024 on complex objects (one queue submission > the 2 s `lockup_timeout`); HIP can (res 1024/1536).
- Before and after every GPU benchmark record `journalctl -k -b | grep -c -E 'GPU reset begin|ring .* timeout'`. On this kernel (7.0.0-38) a compute submission longer than `amdgpu.lockup_timeout` (modinfo default: 2000 ms) gets a per-queue ring reset that logs only `ring ... timeout` (not `GPU reset begin`) and shows up in Vulkan as `ErrorDeviceLost`. Run long jobs in the background with logs written to a file; do not run heavy loads in the foreground.
- 30–35B-A3B Q4 models run (~25 tokens/s) but occupy 18–22 GiB of GTT and are not good enough at generating Manim code; prefer a cloud LLM for work that needs quality.

## Pitfalls already hit
- **Blender:** run `-b --gpu-backend vulkan` natively, no X needed; do **not** wrap it in `xvfb-run` (hangs); from 5.x write a PNG sequence instead of FFMPEG.
- **LLM-generated Manim:** when asking for a repair, send back the frame that points into the model's own code and the final exception line, not library internals. Check the duration too, not only that it runs.
- A harness must stop immediately when the LLM service fails; it must not carry on with stale results.

## Current state

The architecture has completed milestone P1 (native runtime, containers removed).
See the canonical architecture documents for full details:

| Topic | Document |
| :--- | :--- |
| Three-tier architecture | [`docs/architecture/overview.md`](docs/architecture/overview.md) |
| Runtime environment and CLI contract | [`docs/architecture/runtime-contract.md`](docs/architecture/runtime-contract.md) |
| Process sandboxing and security model | [`docs/architecture/security-model.md`](docs/architecture/security-model.md) |
| Native data root and storage locations | [`docs/reference/storage.md`](docs/reference/storage.md) |
| P1 implementation plan and acceptance | [`docs/analysis/2026-11-p1-native-runtime.md`](docs/analysis/2026-11-p1-native-runtime.md) |

### Summary of the runtime today
- **Supervisor (`server/app/supervisor.py`):** Starts and supervises the API service (`app.main`, port 13305 or ephemeral fallback) and background matting worker (`matte_server.py`, port 8083) on `127.0.0.1`.
- **Management CLI (`scripts/lp`):** Controls setup, daemon lifecycle, real-time logging, and diagnostics without container tools.
- **Sandboxed engine runners:** Executes `sd-cli` and `trellis-cli` under network-denying sandboxes (`sandbox-exec` on macOS, `bwrap` on Linux).
- **Discovery via `runtime.json`:** Atomically published (mode 0600) upon passing health checks (`url`, `port`, `pid`, `version`, `started`).
- **Serial GPU queue:** Enforces one native GPU process at a time under an async lock to guarantee memory release between steps.

### Assets and tooling
- **Web UI:** Served at `http://127.0.0.1:13305` from `web/dist` (TypeScript strict + React 18 + Lucent design system; `make web-build`).
- **Blender add-on:** `blender/local_producer/` (v0.15.0). Connects to loopback API, imports textured GLB models, and tracks live progress.
- **Test input for 3D runs:** `blender/local_producer/samples/cat.png` (seed 1234, res 512). End-to-end check: `make smoke`.
- **Background removal:** `server/matte_server.py` (`rembg isnet-general-use` on CPU) on `127.0.0.1:8083`.
- **Blender MCP:** `tools/blmcp/` installs Blender Lab's MCP server into `tools/blmcp/.venv` to drive Blender programmatically.
- **Rigging experiments:** FK auto-rigging (`autorig.py`, ~1 s) and fight animation experiments in `blender/experiments/`.
- Removed on 2026-10-12: `tools/hunyuan3d/`, `tools/pixal3d/`, stickman pipelines. Removed on 2026-10-14: AMD Lemonade, PyTorch diffusers.
