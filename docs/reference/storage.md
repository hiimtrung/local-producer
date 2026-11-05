# Native filesystem storage layout

| | |
| :--- | :--- |
| **Status** | Active |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Applies to** | all platforms |

This document defines where local-producer stores runtime data, weights, engine packages, logs, and outputs on the host filesystem, as well as the exact upstream sources and verification hashes for downloaded assets.

## The native data root

All mutable runtime state is contained within a single platform data root resolved by `app.runtime_env.data_root()`:

- **macOS:** `~/Library/Application Support/local-producer`
- **Linux:** `${XDG_DATA_HOME:-~/.local/share}/local-producer`
- **Override:** `$LP_HOME` (highest precedence across all platforms)

The data root is structured into five dedicated subdirectories:

| Directory | Environment variable | Purpose |
| :--- | :--- | :--- |
| `models/` | `MODELS_DIR` | Shared model weights (`flux2/`, `trellis2/`, `rembg/`) and user-added models (`user/<id>/`) |
| `engines/` | `ENGINES_DIR` | Unpacked native engine packages (`<package>/<version>/`) and `active.json` |
| `library/` | `LIBRARY_DIR` | Job outputs (`jobs/<id>/`) and uploaded source images (`uploads/<id>/`) |
| `server/` | `DATA_DIR` | Configuration (`config.json`), runtime discovery (`runtime.json`), and logs (mode `0700`) |
| `venv/` | (internal) | Runtime Python 3.12 virtual environment initialized by `scripts/lp setup` |

## Populating assets

Assets are downloaded and managed via:
- **Web UI:** **Server > Engines** (installs or switches platform engine packages) and **Server > Models** (installs required shared components and recommended models).
- **Blender add-on:** The "Download Models" button.
- **Command line:** `scripts/lp exec make setup` (installs the platform engine runner, followed by shared components and recommended models).

`server/app/model_setup.py` and `server/app/engines/registry.py` fetch entries pinned by exact URL, file size, and SHA256 checksum in `server/catalog/models.json` and `server/catalog/engines.json`.

## Weights (`models/`)

The `models/` directory stores shared model components and user-installed diffusion and flow weights:

| Path | Contents | Source |
| :--- | :--- | :--- |
| `trellis2/` | TRELLIS.2 shared components, f16 GGUF (2.65 GB): `dinov3` (image encoder), `ss_dec`, `shape_dec`, `tex_dec` (decoders) | Hugging Face `ilintar/trellis2-gguf` rev `a57397bd3d351599d9729fc144b3f87c3f87d65b`, files at repo root |
| `flux2/` | FLUX.2-klein shared components: `qwen_3_4b-q8_0.gguf` (text encoder, 4.3 GB), `flux2-vae.safetensors` (bf16, 336 MB) | `Comfy-Org/vae-text-encorder-for-flux-klein-4b` rev `5f526678002e43af5551dadb73ce2e8c91b43afe` (`split_files/text_encoders/qwen_3_4b.safetensors` and `split_files/vae/flux2-vae.safetensors`). Text encoder is converted once to q8_0 via `sd-cli -M convert` and bf16 source is deleted. |
| `user/<id>/` | User-added main models: FLUX.2-klein diffusion weights or TRELLIS.2 flow models (`ss_flow`, `shape_flow_512`, `tex_flow_512`, optional 1024 flows) with `model.json` and `sha256.json`. | Added via the web UI Models page from catalog recommendations, Hugging Face repositories, direct URLs, or manual uploads. |
| `rembg/` | Background removal ONNX models (`isnet-general-use`). | Downloaded automatically by `matte_server.py` on first invocation into `$U2NET_HOME`. |
| `.cache/` | Temporary staging files and downloads in progress (`.part` files). | Deleted automatically following successful download and checksum verification. |

## Engine packages (`engines/`)

Engine packages are unpacked under `engines/<package_id>/<version>/` with metadata stored in `package.json`.
The currently selected engine is recorded in `engines/active.json`.

| Package | Contents | Source |
| :--- | :--- | :--- |
| `rocm-gfx1103` | `sdcpp/`: `sd-cli` and shared libraries built for AMD HIP (gfx1100-1103 code objects); `trellis/`: `trellis-cli` and libraries built for HIP gfx1103; `rocm/`: AMD TheRock ROCm 10.1.0 runtime libraries (HIP, hipBLAS, rocBLAS, LLVM OpenMP). | GitHub `leejet/stable-diffusion.cpp` release `master-964-1d0a58a` (`...-rocm-10.1.0.zip`); GitHub `pwilkin/trellis.cpp` release `v0.8.1` (`trellis-rocm-linux-x64.tar.gz`); `stable.repo.amd.com/rocm/whl-next` wheels (`rocm-sdk-core`, `rocm-sdk-libraries`, `rocm-sdk-device-gfx1103` 10.1.0, unpacked). |
| `metal-arm64` | `sdcpp/`: `sd-cli` and `libstable-diffusion.dylib` (universal binary with Apple silicon Metal support); `trellis/`: `trellis-cli` built locally from pinned source with native Metal ggml acceleration. | GitHub `leejet/stable-diffusion.cpp` release `master-964-1d0a58a` (`...-bin-Darwin-macOS-26.6.2-arm64.zip`); `pwilkin/trellis.cpp` pinned at `v0.8.1` commit `c0bed38` and `pwilkin/ggml` submodule at `f8697b3`, compiled locally via `server/app/engines/build.py`. |
