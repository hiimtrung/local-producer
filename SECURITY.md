# Security policy

## Reporting a vulnerability

Please do **not** open a public issue. Use GitHub's private vulnerability reporting (repository > Security >
"Report a vulnerability"). Include what is affected, how to reproduce it and the impact you expect. Maintainers
acknowledge reports within a week and agree a disclosure date with the reporter.

## Supported versions

Only the latest commit on the default branch is supported; the project is in its R&D phase and has no releases yet.

## Threat model and the rules that follow from it

The GPU server (`server/`) executes native code on the GPU and writes downloaded files to disk; the Blender add-on
talks to it over HTTP. The rules below are enforced in code and review; changes that weaken one need a maintainer's
explicit approval in the pull request.

| Risk | Rule | Where |
| :--- | :--- | :--- |
| Remote access to the server | Ports are published on `127.0.0.1` only; there are no user accounts. Optional `SERVER_TOKEN` (Bearer token, constant-time compare) for anything else. Never publish the ports on a LAN or the internet without a reverse proxy that adds TLS and authentication. | `scripts/run-server.sh`, `server/app/` |
| Web UI | Served by the server itself with a strict Content-Security-Policy (`script-src 'self' 'wasm-unsafe-eval'`, no framing, no plugins; `'wasm-unsafe-eval'` was added on 2026-10-15 with the maintainer's approval so model-viewer can compile its bundled meshopt decoder: it permits WebAssembly compilation only, JavaScript `eval` stays blocked); one bundle built from this repository, nothing loads from a CDN. npm packages: exact versions, locked with sha512 integrity hashes (`web/package-lock.json`), installed with `npm ci` and install scripts disabled (`web/.npmrc`); the design system is pinned by SHA256 (`web/vendor/VENDOR.json`); both checked by the tests. The access token is kept in the browser's localStorage and sent only to the same origin. | `server/app/security.py`, `web/` |
| Add-on repository (approved by the maintainer, 2026-10-15) | `/blender/index.json` and the add-on zip are served without the token, like the static UI (the add-on source is public and Blender's repository sync cannot send the UI's token); they expose nothing else. Blender checks the zip against the index's SHA256 and asks the user before adding the repository. | `server/app/routes/addon.py` |
| Malicious requests | Every field is validated (size, range, enum, image type by magic bytes, prompt length, no control characters); bodies are capped (48 MiB); the CLIs are run with argument lists, never a shell; clients cannot pass file paths, and URLs only to add a model (next row): uploads and results are referenced by random ids checked against `^[0-9a-f]{32}$`, result file names against a fixed pattern; uploads are type-checked by magic bytes and pruned. | `server/app/` |
| Tampered downloads | Weights and engine packages (GPU runtime, CLI builds) come only from `server/catalog/models.json` and `server/catalog/engines.json`: fixed release / revision URLs, size and SHA256 per file, https only, host (and every redirect) on the catalog's allowlist (models: Hugging Face; engines: GitHub and `repo.amd.com` for AMD's ROCm runtime wheels, the latter approved by the maintainer on 2026-10-15). A file is used only after its hash matches; a package is unpacked into a staging directory and moved into place as a whole. Packages carry no code that the server imports: only the pinned binaries they run, and they may not set loader variables (`LD_*`, `DYLD_*`, `PATH`, `PYTHON*`). | `server/app/model_setup.py`, `server/app/engines/`, `server/catalog/` |
| User-added models (maintainer decision, 2026-10-15) | `POST /v1/models` takes any http or https link from the client and `PUT /v1/models/upload` a file. The server runs on the user's own machine for that user, so links to that machine or the local network are allowed too and the user is responsible for what a link points to; other schemes (`file:`, `ftp:`, ...) are refused, also after redirects. Cross-site pages cannot trigger an add: the endpoint takes JSON, which needs a CORS preflight the server never grants. Weights only: `.gguf` / `.safetensors`, checked by their header after the download (no pickle formats, nothing imported or executed; only the engine's CLI reads them). Hugging Face files are pinned to the commit the revision pointed at and checked against the size and SHA256 Hugging Face publishes; other links are hashed while they download (recorded, not verified). 64 GiB cap per file, free-space check, staging directory. A model that failed its test run is refused for jobs. Malformed weights can still crash the CLI (a memory-safety bug in a parser is the residual risk; the CLI runs in the rootless, capability-free container). | `server/app/model_store.py`, `server/app/routes/models.py` |
| Malicious archives | Extraction rejects absolute paths, `..`, devices and symlinks that leave their directory (tar `data` filter, equivalent zip checks). | `server/app/model_setup.py` |
| Dependency hijacking | Python packages of the image are installed with `--require-hashes` from the compiled lock file; npm packages with `npm ci` from the integrity-hashed lock file, no install scripts; both base images are pinned by digest; GitHub Actions and pre-commit hooks are pinned to commit SHAs; Dependabot proposes updates. | `server/requirements.txt`, `server/Containerfile`, `.github/`, `.pre-commit-config.yaml` |
| Container escape / privilege | Rootless Podman, `--cap-drop=all`, `no-new-privileges`, non-root user in the image; only the GPU devices are passed through (`/dev/kfd` and `/dev/dri` for ROCm). | `scripts/run-server.sh`, `scripts/lp-env.sh`, `server/Containerfile` |
| Leaked secrets | gitleaks runs in pre-commit and CI; `.env`, keys and certificates are git-ignored. | `.pre-commit-config.yaml`, `.gitignore` |
| Generated code | Containers that run generated code (e.g. LLM-written scene code, planned) always use `--network none`. | `AGENTS.md` |

Model licences: the weights are third-party (`models/README.md` names each source); they are downloaded by each
user and never redistributed by this repository.
