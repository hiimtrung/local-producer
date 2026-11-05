# Architecture overview

| | |
| :--- | :--- |
| **Status** | Active |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Applies to** | all platforms |

The local-producer architecture delivers private, self-hosted 3D asset generation directly on consumer hardware.
This document outlines the three structural tiers, execution boundaries, and the native runtime model.

## Three-tier structure

The system is organized into three distinct tiers:

```
┌────────────────────────────────────────────────────────────────────────┐
│ Frontend / Desktop Shell                                               │
│ Web UI (TypeScript, React 18, Lucent) · Blender Add-on · Tauri Shell   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / JSON API (127.0.0.1:13305)
┌───────────────────────────────────▼────────────────────────────────────┐
│ Host Supervisor & Python Service                                       │
│ app.supervisor ──► FastAPI Service (app.main) + Matting (matte_server) │
│ Job queue · Catalog manager · Model store · Environment resolution    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ CLI invocation under sandbox
┌───────────────────────────────────▼────────────────────────────────────┐
│ Native GPU Runners                                                     │
│ Pinned engine binaries: sd-cli (FLUX.2) · trellis-cli (TRELLIS.2)      │
│ Sandboxed: network denied (sandbox-exec on macOS, bwrap on Linux)     │
└────────────────────────────────────────────────────────────────────────┘
```

### 1. Frontend and desktop shell tier

The presentation layer connects users to generation pipelines:

- **Web UI:** A single-page application built with TypeScript, React 18, and the Lucent design system. Served directly by the local API server at `http://127.0.0.1:13305` from static assets in `web/dist`.
- **Blender add-on:** A Python extension (`blender/local_producer/`) allowing artists to generate assets and import textured GLB meshes straight into the Blender 3D viewport.
- **Desktop application shell (planned for desktop packaging):** A lightweight native wrapper providing single-instance enforcement, system tray controls, and lifecycle supervision.

All frontends interact with the exact same HTTP/JSON interface, ensuring consistent behavior across browser and desktop environments.

### 2. Host supervisor and Python service tier

The application core coordinates generation requests, file persistence, and background subprocesses:

- **Supervisor (`server/app/supervisor.py`):** The parent orchestrator managing the API server and the background matting service. It handles port allocation, health polling, clean process group termination on exit, and runtime discovery via `runtime.json`.
- **API service (`server/app/main.py`):** A typed FastAPI application running on Python 3.12. It provides the job queue, routes, settings persistence, and model verification.
- **Matting service (`server/matte_server.py`):** An independent worker serving background removal endpoints on `127.0.0.1:8083` using rembg models.

Detailed specifications for this tier are documented in [Native runtime contract](runtime-contract.md).

### 3. Native GPU runner tier

Heavy compute tasks run out-of-process via native CLI binaries:

- **`sd-cli`:** Native binary from `stable-diffusion.cpp` for FLUX.2 text-to-image and image-to-image pipelines.
- **`trellis-cli`:** Native binary from `trellis.cpp` for turning matted images into textured 3D meshes.

Each runner execution is isolated behind an OS sandbox (`sandbox-exec` on macOS, `bwrap` on Linux) that revokes network socket permissions, preventing network access from engine binaries.

## What runs where

| Component | Execution context | Network binding | Sandbox |
| :--- | :--- | :--- | :--- |
| Web UI | Browser / WebView | Connects to loopback | Browser sandbox |
| Blender add-on | Blender Python process | Connects to loopback | Host process |
| Supervisor | Host Python 3.12 venv | None | Standard user process |
| API Server | Host Python 3.12 child | `127.0.0.1:13305` (or ephemeral) | Standard user process |
| Matting Server | Host Python 3.12 child | `127.0.0.1:8083` | Standard user process |
| Engine CLIs | Subprocess from API | None | Network denied (`sandbox-exec` / `bwrap`) |

## What P1 changed

The P1 native runtime architecture milestone overhauled the runtime environment:

1. **Eliminated container layers:** Replaced container engine abstractions with a single native Python supervisor. This removes filesystem permission complications and image build overhead.
2. **Standardized data root:** Unified file layout under a single OS-appropriate directory tree (`~/Library/Application Support/local-producer` on macOS, `~/.local/share/local-producer` on Linux, or `$LP_HOME`).
3. **Introduced the `scripts/lp` CLI:** Provided a unified management tool for setup, daemon lifecycle, diagnostics, and environment execution.
4. **Enforced network sandboxing:** Sandboxed native engine CLI execution on host systems using native kernel mechanisms without requiring root privileges.
5. **Atomic runtime discovery:** Implemented `runtime.json` generation with mode `0600`, enabling frontends and developer tools to find the active server port and process ID reliably.

Related architectural documents:
- [Native runtime contract](runtime-contract.md)
- [Native security model](security-model.md)
- [Native filesystem storage layout](../reference/storage.md)
- [Security policy](../../SECURITY.md)
