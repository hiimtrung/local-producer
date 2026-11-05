# local-producer

[![CI](https://github.com/hiimtrung/local-producer/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/hiimtrung/local-producer/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)

Science/engineering explainer videos from Obsidian notes, produced on your own machine. Native execution on Linux
(tested on a Ryzen 7 PRO 7840U with Radeon 780M iGPU) and macOS (tested on Apple silicon M4). The project is in its
R&D phase; see [Documentation](#documentation).

What works today is the 3D asset path: our self-hosted native GPU server with a web UI, also driven from a Blender add-on:

```
text -> FLUX.2-klein-4B image (optional A-pose edit) -> background removal (rembg, CPU) -> TRELLIS.2 -> GLB -> Blender
        FLUX.2 (stable-diffusion.cpp) and TRELLIS.2 (trellis.cpp) on native GPU runners, one process per job
```

Measured on the Radeon 780M (details in `CHANGELOG.md`): a 1024² image in ~63 s, an A-pose edit in ~140 s, a mesh at
res 512 in ~4.5 min (res 1024 ~19 min); a whole character in ~8 min (Fast preset ~6 min).
Measured on Apple silicon M4 (details in `CHANGELOG.md`): a 1024² image in ~121-125 s at 8.6 GiB peak, TRELLIS.2 q8
res 512 in ~300 s at 2.1 GiB peak.

## Layout

| Path | What |
| :--- | :--- |
| `server/app/` | the server (FastAPI, fully typed: `mypy --strict`, every response a pydantic model): `supervisor.py` process orchestrator; `runtime_env.py` environment and path resolution; `pipelines/` capability modules registered in `pipelines/__init__.py`; `jobs.py` serial GPU queue; `routes/` API endpoint routers; `engines/` platform engine packages, host detection, and sandboxing (`sandbox.py`); `model_setup.py` pinned downloads; `settings.py` limits and validated runtime config; `security.py` body cap, token, and CSP |
| `server/` | `matte_server.py` (rembg on `127.0.0.1:8083`), dependency definitions (`requirements.in`, `requirements.macos.txt`, `requirements.linux.txt`), catalogs (`catalog/models.json` for weights, `catalog/engines.json` for engine packages) |
| `web/` | web UI served at `http://127.0.0.1:13305`: TypeScript (strict) + React 18 + Lucent design system, built by esbuild into `web/dist` (`make web-build`). `src/api/types.gen.ts` generated from server models (`make api-types`), `src/ui/` atomic layers, `src/pages/` page components |
| `blender/local_producer/` | Blender add-on and Blender 4.2+ extension (`blender_manifest.toml`; the server publishes it as an extension repository, installed by dragging a link from the web UI into Blender); `prompts.py` shared prompt framing |
| `scripts/` | `lp` and `lp.py` (native CLI for setup, daemon management, logs, and diagnostics), `lock-requirements.sh`, `check_docs.py`, `smoke_test.py` (end-to-end check), `make_sample.py`, `gen_tokens_css.py`, `gen_api_types.py` |
| `tests/` | unit tests (no GPU, no network): API with fake engines, supervisor lifecycle, sandbox, runtime env, model setup, prompts, add-on client, static checks |
| `tools/blmcp/` | installs Blender Lab's MCP server so an agent can drive a running Blender |
| `blender/experiments/` | one-off Blender scripts run over MCP (auto-rig, fight animation, texture reprojection) |
| `docs/` | the documentation tree: `architecture/` (why it is built this way), `operations/` (how to run and fix it), `development/` (how to work on it), `reference/` (exact paths, configurations, and values), `adr/` (decision records), `analysis/` (dated studies); start at `docs/README.md` |

## Requirements

- **Linux or macOS** with a supported GPU engine package (`server/catalog/engines.json`):
  - **AMD gfx1103 with ROCm** (tested on Radeon 780M). Requires the kernel parameter `cwsr_enable=0` (see below) and Bubblewrap (`bwrap`) for process sandboxing (`sudo apt-get install bubblewrap`).
  - **Apple silicon with Metal** (M1 or later, tested on M4). Engine CLIs run under macOS `sandbox-exec`. Compiling `trellis-cli` on install requires CMake (`brew install cmake`) and the Xcode Command Line Tools (`xcode-select --install`).
- [uv](https://docs.astral.sh/uv/) for Python 3.12 environment management.
- Node.js 24 with npm to build the web UI.
- GNU make and standard POSIX shell tools.
- ~30 GB free disk space for weights and engine packages.

**ROCm on gfx1103: kernel parameter, once, as root, then reboot** (without it HIP jobs reset the GPU intermittently and the server does not load the engine; CHANGELOG 2026-10-14):
```bash
echo 'options amdgpu cwsr_enable=0' | sudo tee /etc/modprobe.d/amdgpu-cwsr.conf
sudo reboot
```
Verify with `cat /sys/module/amdgpu/parameters/cwsr_enable` (must print `0`).

## Quick start

```bash
git clone https://github.com/hiimtrung/local-producer.git && cd local-producer
make dev              # installs dev tools, git hooks, and web packages
scripts/lp setup      # sets up runtime data root, virtualenv, and compiles web UI
scripts/lp up         # starts background supervisor; open http://127.0.0.1:13305
```

In the web UI:
- **Server > Engines:** inspects host hardware and installs the platform engine package (~1.1 GB download; loaded dynamically).
- **Server > Models:** downloads shared components (FLUX.2-klein text encoder and VAE, TRELLIS.2 image encoder and decoders; ~7.3 GB on disk) plus recommended main models (FLUX.2-klein-4B Q8_0, TRELLIS.2 q8 flow models; ~18 GB total).
- **Image:** generates or edits images (zoom and pan results).
- **3D model:** converts images into textured GLB files with an interactive preview.
- **Library:** browse past generation results and uploaded inputs.
- **Tools:** standalone utility pipelines.
- **Server:** system status, live logs, Blender add-on installer, and settings.

To inspect server status or stop services:

```bash
scripts/lp status     # check process and engine status
scripts/lp logs -f    # follow live server logs
scripts/lp down       # cleanly stop the supervisor and all worker processes
```

Where the data lives: all files are kept under a native data root (`~/Library/Application Support/local-producer` on macOS,
`~/.local/share/local-producer` on Linux, overridable via `$LP_HOME`). Subdirectories: `models/` (weights), `engines/`
(runners), `library/` (results and uploads), `server/` (logs and `config.json`), and `venv/` (runtime virtualenv).
See [`docs/reference/storage.md`](docs/reference/storage.md).

The Blender add-on **LocalProducer** communicates with the local server: drag its installation button from the web UI
into Blender.

`make help` lists all make tasks; `make check` runs full verification; `make smoke` runs an end-to-end generation check.

## Documentation

| Document | What |
| :--- | :--- |
| [`docs/README.md`](docs/README.md) | index of the documentation tree; start here |
| [`docs/architecture/overview.md`](docs/architecture/overview.md) | three-tier native architecture and execution boundaries |
| [`docs/operations/run-headless.md`](docs/operations/run-headless.md) | running headlessly with the `scripts/lp` CLI |
| [`docs/reference/storage.md`](docs/reference/storage.md) | native filesystem storage layout and upstream download sources |
| [`docs/adr/`](docs/adr/README.md) | architecture decision records |
| [`docs/analysis/`](docs/analysis/2026-11-desktop-architecture.md) | dated studies: desktop architecture and performance bottlenecks |
| [`docs/archive/`](docs/archive/local-producer-v2.1.md) | archived specifications (v2.1 and v3 proposal), kept for reasoning |
| [`AGENTS.md`](AGENTS.md) | working conventions for contributors and AI agents |
| [`CHANGELOG.md`](CHANGELOG.md) | research and measurement log with exact benchmark numbers |

## Contributing and security

See [`CONTRIBUTING.md`](CONTRIBUTING.md) (setup, workflow, style) and [`SECURITY.md`](SECURITY.md) (reporting, threat model, rules).

## Licence

GPL-3.0-or-later (`LICENSE`). Third-party components retain their upstream licences and are downloaded at run time,
never redistributed in this repository: TRELLIS.2 (MIT), FLUX.2-klein-4B, stable-diffusion.cpp, trellis.cpp, rembg.
The web UI bundles React and react-dom (MIT), model-viewer (Apache-2.0) with three.js (MIT) and lit (BSD-3-Clause)
from npm (`web/package-lock.json`); the build writes licence texts next to the bundle (`*.LEGAL.txt`).
