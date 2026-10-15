# local-producer

[![CI](https://github.com/hiimtrung/local-producer/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/hiimtrung/local-producer/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)

Science/engineering explainer videos from Obsidian notes, produced on your own machine. Developed and measured on a
Ryzen 7 PRO 7840U with a Radeon 780M iGPU (Linux, rootless Podman). The project is in its R&D phase; see
[Documentation](#documentation).

What works today is the 3D asset path: our own GPU server with a web UI, also driven from a Blender add-on:

```
text -> FLUX.2-klein-4B image (optional A-pose edit) -> background removal (rembg, CPU) -> TRELLIS.2 -> GLB -> Blender
        FLUX.2 (stable-diffusion.cpp) and TRELLIS.2 (trellis.cpp) both on ROCm/HIP, one process per job
```

Measured on the Radeon 780M (details in `CHANGELOG.md`): a 1024² image in ~63 s, an A-pose edit in ~140 s, a mesh at
res 512 in ~4.5 min (res 1024 ~19 min); a whole character in ~8 min (Fast preset ~6 min).

## Layout

| Path | What |
| :--- | :--- |
| `server/app/` | the server (FastAPI, fully typed: `mypy --strict`, every response a pydantic model): `pipelines/` one module per capability (text-to-image, image edit, background removal, image-to-3D) registered in `pipelines/__init__.py`; `jobs.py` the job queue (one GPU job at a time, progress, cancel, history); `routes/` one module per API area; `engines/` the engine packages (machine detection, install, load / reload without a restart, the runners the pipelines start); `model_setup.py` pinned, SHA256-verified downloads; `settings.py` limits and the validated runtime config; `security.py` token, body cap, CSP |
| `server/` | `Containerfile` (build context: the repository root; the image holds no GPU code), `entrypoint.sh`, `matte_server.py` (rembg on `127.0.0.1:8083`), hashed `requirements.txt`; `catalog/models.json` (weights) and `catalog/engines.json` (engine packages per platform), every download pinned by URL, size and SHA256 |
| `web/` | the web UI served by the server at `http://127.0.0.1:13305`: TypeScript (strict) + React 18 + the Lucent design system, built by esbuild into `web/dist` (`make web-build`; the image builds it too). `src/api/types.gen.ts` is generated from the server's models (`make api-types`), `src/ui/` atomic layers (atoms, molecules, organisms, templates), `src/pages/` one component per page registered in `src/app/pages.ts`, `vendor/lucent/` the pinned design system (`VENDOR.json`), `styles/tokens.css` generated from its tokens |
| `blender/local_producer/` | Blender add-on and Blender 4.2+ extension (`blender_manifest.toml`; the server publishes it as an extension repository, so it installs by dragging a link from the web UI into Blender); `prompts.py` is the one source of the prompt framing for add-on, server and web |
| `scripts/` | `run-server.sh`, `lp-env.sh` (where data lives, shared with the Makefile), `smoke_test.py` (end-to-end check), `make_sample.py` (sample image), `gen_tokens_css.py`, `gen_api_types.py` (TypeScript types from the server models) |
| `tests/` | unit tests (no GPU, no network): API with a fake engine package, engines, model setup, prompts, add-on client, web static checks |
| `tools/blmcp/` | installs Blender Lab's MCP server so an agent can drive a running Blender |
| `blender/experiments/` | one-off Blender scripts run over MCP (auto-rig, fight animation, texture reprojection) |
| `models/README.md` | where the server keeps weights, engines, results and logs, and where each download comes from |

## Requirements

- Linux, rootless Podman, ~30 GB free disk, and a GPU with an engine package (`server/catalog/engines.json`). Today:
  AMD gfx1103 with ROCm (tested: Radeon 780M). NVIDIA CUDA (Linux, container) and Apple silicon with MLX (macOS,
  native, since containers cannot reach Metal) are planned; the server core is the same for all of them.
- **ROCm on gfx1103: kernel parameter, once, as root, then reboot** (without it HIP jobs reset the GPU intermittently
  and the server does not load the engine; CHANGELOG 2026-10-14):
  `echo 'options amdgpu cwsr_enable=0' | sudo tee /etc/modprobe.d/amdgpu-cwsr.conf` — check with
  `cat /sys/module/amdgpu/parameters/cwsr_enable` (must print `0`). Revert: delete the file, reboot.
- For development: [uv](https://docs.astral.sh/uv/), Node.js 24 with npm, and GNU make.

## Quick start

```bash
git clone https://github.com/hiimtrung/local-producer.git && cd local-producer
make server-up        # builds the image on first start, then open http://127.0.0.1:13305
```

In the web UI: **Server > Engines** shows what the machine is and installs its engine package (the GPU runtime and
the image / 3D generators, ~1.1 GB download; loaded without a restart), **Server > Models** downloads the shared
components every model of a kind runs with (the FLUX.2-klein text encoder and VAE, the TRELLIS.2 image encoder and
decoders; 7.3 GB on disk) plus a recommended main model for each kind that has none (FLUX.2-klein-4B Q8_0, TRELLIS.2
q8 flow models; ~18 GB on disk in all; it installs the engine first when none is loaded). Other main models (FLUX.2-klein
quantisations, TRELLIS.2 q4 / f16 flow models) come from the suggestions, Hugging Face, another http(s) link or an
upload, and one per kind is the default; **Test** runs a tiny real job with the loaded engine to prove a model works
here, and the Image / 3D pages then offer it. Pinned files are checked against their SHA256. **Image** generates or edits images (zoom and pan the result), **3D model** turns an image into a
textured GLB with an interactive preview, **Library** keeps every result, **Tools** runs the smaller steps, **Server**
shows the status with the Blender add-on (drag its button into Blender to install), the live job log, the models and
the settings. All parameters are on the pages; the server validates them. Without a browser: `make setup` (engine,
then components and recommended models). The server does not start by itself after a reboot: `make server-up`.

Where the data lives (`scripts/lp-env.sh`, each overridable): weights in the Podman volume `local-producer-models`,
engine packages in `local-producer-engines` (both survive image rebuilds; `podman volume rm` or
`podman system prune --volumes` deletes them), results and uploads (the Library) in `~/.local-producer/library`, the
runtime settings and logs in `~/.local-producer/server`.

The Blender add-on **LocalProducer** talks to the same server and queue (Sidebar > LocalProducer: Check Server,
Download Models, generate; the Library panel lists the server's finished 3D models and imports one); set its "Server Log" preference to `~/.local-producer/server/server.log` for live progress.

`make help` lists all tasks; `make smoke` runs an end-to-end check against the running server.

## Documentation

| Document | What |
| :--- | :--- |
| [`AGENTS.md`](AGENTS.md) | working conventions (also for AI coding agents) and the current state of every part |
| [`CHANGELOG.md`](CHANGELOG.md) | the research log: every experiment with its setup, numbers and conclusion |
| [`models/README.md`](models/README.md) | where the server keeps weights, engines, results and logs, and the source of each download |
| [`local-producer.md`](local-producer.md) | the original video-pipeline specification (v2.1, partly superseded) |
| [`spec-v3-gated-pipeline.md`](spec-v3-gated-pipeline.md) | a proposal for the next video pipeline (not built yet) |

## Contributing and security

See `CONTRIBUTING.md` (setup, workflow, style) and `SECURITY.md` (reporting, threat model, rules).

## Licence

GPL-3.0-or-later (`LICENSE`). Third-party components keep their own licences and are downloaded, not redistributed:
TRELLIS.2 (MIT), FLUX.2-klein-4B, stable-diffusion.cpp, trellis.cpp, rembg (see upstream); Blender MCP (GPL-3.0,
installed by `tools/blmcp/install.sh`, not vendored). The web UI bundles React and react-dom (MIT),
model-viewer (Apache-2.0) with three.js (MIT) and lit (BSD-3-Clause) from npm (`web/package-lock.json`); the build
writes their licence texts next to the bundle (`*.LEGAL.txt`).
