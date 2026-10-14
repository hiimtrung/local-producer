# Where the server keeps its data, and where each download comes from

Nothing here is committed: this directory only holds this file (the old `models/` tree moved out on 2026-10-15).
The locations are set in `scripts/lp-env.sh` (shared by `scripts/run-server.sh` and the Makefile), each overridable:

| What | Where | In the container |
| :--- | :--- | :--- |
| Weights (portable across engines) | Podman volume `local-producer-models` | `/models` (`MODELS_DIR`) |
| Engine packages: GPU runtime + CLI builds for this machine | Podman volume `local-producer-engines` | `/engines` (`ENGINES_DIR`) |
| Library: job results (`jobs/<id>/`) and uploads | `~/.local-producer/library` | `/library` (`LIBRARY_DIR`) |
| Server state: `config.json`, `server.log` (jobs, CLI output, GPU memory per job), `container.log` | `~/.local-producer/server` | `/data` (`DATA_DIR`) |

Volumes live in `~/.local/share/containers/storage/volumes/<name>/_data` (`podman volume inspect`), on the same disk as
the home directory here, outside every image layer: rebuilding the image keeps them; `podman volume rm` or
`podman system prune --volumes` deletes them.

**Fill them** with the web UI (Server > Engines, Server > Models), the add-on's "Download Models" button, or
`make setup` (= `make engines` + `make models`). `server/app/model_setup.py` and `server/app/engines/registry.py`
fetch every entry of `server/catalog/models.json` / `server/catalog/engines.json` (pinned URL + size + SHA256), verify
and install it; the two FLUX.2 files are downloaded in bf16 and converted to q8_0 with the loaded engine's `sd-cli`.
`make models-status` / `make models-verify` / `make engines-status` check what is installed. The catalogs are
authoritative; the tables document the sources.

## Weights (models volume)

| Path | Contents | Source |
| :--- | :--- | :--- |
| `trellis2/` | TRELLIS.2 GGUF, the f16 set (~15 GB): `birefnet`, `dinov3`, `ss_flow`, `ss_dec`, `shape_flow_512`, `shape_flow_1024`, `shape_dec`, `tex_flow_512`, `tex_flow_1024`, `tex_dec` (`.gguf`) + `README.md` | Hugging Face `ilintar/trellis2-gguf` rev `a57397bd3d351599d9729fc144b3f87c3f87d65b`, the files at the repo root (not the `q8`/`q4` folders) |
| `flux2/` | `flux-2-klein-4b-q8_0.gguf` (4.2 GB), `qwen_3_4b-q8_0.gguf` (4.3 GB), `flux2-vae.safetensors` (bf16, 336 MB) | `black-forest-labs/FLUX.2-klein-4B` rev `e7b7dc27f91deacad38e78976d1f2b499d76a294` `flux-2-klein-4b.safetensors`; `Comfy-Org/vae-text-encorder-for-flux-klein-4b` rev `5f526678002e43af5551dadb73ce2e8c91b43afe` `split_files/text_encoders/qwen_3_4b.safetensors` and `split_files/vae/flux2-vae.safetensors`. The two big files are converted once to q8_0 (CPU, ~5 s each), then the bf16 originals can be deleted: `sd-cli -M convert -m <file>.safetensors --type q8_0 -o flux2/<name>-q8_0.gguf` (done by `model_setup.py`) |
| `rembg/` | rembg ONNX models (`isnet-general-use`, ...) | downloaded by the matting server on first use |
| `.cache/` | archives and bf16 originals while they download / convert (deleted afterwards; `.part` files resume an interrupted download) | `server/app/model_setup.py` |

## Engine packages (engines volume)

Installed as `<id>/<version>/` with the catalog entry in `package.json`; `active.json` names the one to load at start.

| Package | Contents | Source |
| :--- | :--- | :--- |
| `rocm-gfx1103` | `sdcpp/`: stable-diffusion.cpp `sd-cli` + libs, HIP build with gfx1100-1103 code objects; `trellis/`: trellis.cpp `trellis-cli` + libs, HIP build with gfx1103 code objects; `rocm/`: AMD TheRock ROCm 10.1.0 runtime (HIP, hipBLAS, rocBLAS, LLVM OpenMP) | GitHub `leejet/stable-diffusion.cpp` release `master-964-1d0a58a` (`...-rocm-10.1.0.zip`, contents of `build/bin/`; the zip stores the `.so` symlinks as small text files, recreated as symlinks); GitHub `pwilkin/trellis.cpp` release `v0.8.1` (`trellis-rocm-linux-x64.tar.gz`); `stable.repo.amd.com/rocm/whl-next` wheels `rocm-sdk-core`, `rocm-sdk-libraries`, `rocm-sdk-device-gfx1103` 10.1.0 (unpacked, not pip-installed) |
