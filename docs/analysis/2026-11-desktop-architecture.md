# local-producer — one runtime contract, shipped as a desktop app (Tauri)

| | |
| :--- | :--- |
| **Status** | Decided. Roadmap in progress; the decisions are recorded as ADRs 0002–0005. |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Date** | 2026-11-04, decisions closed 2026-11-05 |
| **Machine used for facts** | Mac mini M4 (4P+6E, 10-core GPU, 16 GiB unified), macOS 27.2. No runtime installed here (`~/.local-producer` does not exist). |
| **Related** | [`2026-11-performance-bottlenecks.md`](./2026-11-performance-bottlenecks.md) (ranked GPU/UI bottlenecks). This plan does not change it; P1–P2 here make its A/B measurements easier to compare across machines. |
| **Project rules followed** | `AGENTS.md`: measure, do not estimate; facts separated from hypotheses; English in all files; experiments recorded in `CHANGELOG.md`. |

## 0. Decisions taken (user, 2026-11-04)

| # | Decision | Consequence |
| :--- | :--- | :--- |
| 1 | **Tauri v2**, WebKitGTK risk accepted for Linux later | No Electron fallback work now; the WebGL/GLB risk is measured, not designed around |
| 2 | **No Windows** | No engine package, no CI target, splash says so explicitly |
| 3 | **v1 desktop = macOS arm64 only**; **Linux runs the same native runtime — no containers at all** | The container path (`server/Containerfile`, `server/entrypoint.sh`, `scripts/run-server.sh`, hadolint, Podman storage) is deleted, not kept as an alternative. One Python mechanism, one supervisor, one directory layout, one engine-package mechanism on both OSes |
| 4 | **Default onboarding profile = Fast** | First run offers Q4_0 FLUX.2 + TRELLIS.2 q4 (~13.4 GB), not the 18.4 GB set |
| 5 | **The Blender add-on may be changed** | Add-on reads `runtime.json` (port + token) instead of a hard-coded `127.0.0.1:13305` |
| 6 | **Linux desktop ships `.deb` first** | `.deb` declares the WebKitGTK/GTK dependencies explicitly; AppImage stays a fallback, not the primary format |
| 7 | **One baseline artifact per OS, no chip-tuned variants**; compatibility is decided by a runtime scan, LM Studio style | `metal-arm64` is built without `GGML_NATIVE`; `rocm-gfx1103` keeps its multi-target code objects. The app probes GPU, driver, kernel/userspace stack, glibc and macOS version, then says "compatible" or why not — instead of shipping N artifacts and hoping |

**Also resolved 2026-11-04 (recommendations accepted).** Loopback only, no LAN exposure. No resident `sd-server` in v1 (re-decide after the image-path measurements in P3; the catalog keeps the `resident_server` flag so it is a switch, not a rewrite). Linux sandbox order: `bwrap` → Landlock → *degraded with a log*, and the `SECURITY.md` change must be approved in writing before P6 ships. No Vulkan fallback package until a user report shows it is needed. Weight licences are checked before P5. Nothing is left undecided; §8 lists what still has to be *measured*.

**Confirmed scope (user, 2026-11-04).** macOS arm64 is the only *desktop* target in v1. Linux is not "the container version": it runs exactly the same native runtime (uv-managed Python, `app.supervisor`, plain directories, engine packages downloaded per platform), headless. Containers are removed from the project rather than kept as a second execution architecture. The Linux desktop package (Tauri + WebKitGTK) remains a later phase (§9 P6); it reuses the shell, it is not a rewrite.

Why this is the cleaner split: what stays different between the two OSes is then only the GPU stack (ROCm vs Metal), the engine artifacts, and the kernel/OS checks — all already behind `app/engines/` (`host.py`, `backends.py`, `catalog.py`). Everything above that line is one code path.

---

## 1. Goal and non-goals

**Goal.** A user downloads one file, opens it, and gets a working app: preflight checks, pinned engine/model downloads with resume and signature checks, the existing web UI, the GPU jobs, and a Blender add-on that finds the app automatically. No terminal, no Xcode, no Node, no uv, no Podman.

**Non-goals for v1.**

- Windows, Intel Macs, remote/multi-user hosting.
- Shipping model weights or GPU runtimes inside the installer (ROCm installed is 5.2 GB; models 13.4–27.9 GB — they must stay downloads).
- Rewriting the web UI, the API, the pipelines or the job/Library format.
- Changing the user-facing features; this is a packaging and consistency project.

---

## 2. Facts: what is inconsistent today

Measured/verified in the repository on 2026-11-04.

| Aspect | Linux (container) | macOS (native) | Forced by the OS? |
| :--- | :--- | :--- | :--- |
| Data location | 2 Podman volumes (`local-producer-models`, `-engines`) + 2 host dirs | 4 plain dirs `~/.local-producer/*` | No |
| Process supervisor | `server/entrypoint.sh` (bash, `--rm` container) | `scripts/run-native.sh _supervise` (nohup + pidfile) | No |
| Stop / status | `podman stop` | pidfile + `kill_tree` | No |
| Startup log | `container.log` (`tee` in the container) | `native.log` | No |
| Python env | `/opt/venv`, `requirements.txt` (x86_64-linux) | `~/.local-producer/venv`, `requirements-macos.txt` (aarch64-darwin) | Partly (platform hashes) |
| Lock-file sync | — | manual recipe written in the file header (`grep -oE '^...' > /tmp/pins.txt`, `MACOSX_DEPLOYMENT_TARGET=14.0`, re-paste header) | No |
| Runtime env | `ENV ... OMP_NUM_THREADS=8` in `server/Containerfile` | written a second time in `lp_native_env()` (`hw.perflevel0.physicalcpu` → 4) | No |
| Engine package | downloaded binary artifact | downloads sources and **compiles** with CMake + Xcode CLT (`build.py`, `GGML_NATIVE=ON`) | Partly |
| Isolation | container: cap-drop, no-new-privileges, userns | runs as the user; only engine CLIs under `sandbox-exec` (network denied) | No |
| `make` | one fresh container per target | host venv | No |
| CI | 6 jobs, all `ubuntu-24.04` | **none** | No |

The last row is the most expensive: the macOS path and `requirements-macos.txt` are never checked by CI, so drift surfaces only when a Mac user runs `make` — the same class of failure the last dependency wave produced.

Sizes computed from `server/catalog/models.json` today (exact sums of the pinned `size` fields, decimal GB):

| Profile | Contents | Download size |
| :--- | :--- | ---: |
| Shared components (always) | Qwen3-4B q8_0 4.27 + FLUX.2 VAE 0.34 + TRELLIS.2 dinov3/decoders 2.65 | **7.26 GB** |
| **Fast** (v1 default) | + FLUX.2-klein Q4_0 2.46 + TRELLIS.2 q4 3.65 | **13.37 GB** |
| Quality / current default | + FLUX.2-klein Q8_0 4.30 + TRELLIS.2 q8 6.88 | **18.44 GB** |
| Full | + FLUX.2-klein F16 7.75 + TRELLIS.2 f16 12.93 | **27.95 GB** |

Engine package on top: `rocm-gfx1103` is 5.2 GB installed (measured); `metal-arm64` is a 35 MB sd.cpp zip plus a locally built `trellis-cli` (size not yet measured — to measure in P2).

### 2.1 What the container provides today, and its native replacement

Every row must be answered before the container can be deleted; the ROCm runtime, the Linux sandbox and the glibc/system-lib check are the real risk of this plan.

| Provided by the container today | Native replacement | Status |
| :--- | :--- | :--- |
| Python 3.12 + hashed wheels (`requirements.txt`, x86_64-linux) | `uv` venv with python-build-standalone 3.12 + `requirements.linux.txt` — the mechanism macOS already uses | Designed; same code as the current macOS path |
| System libs `libnuma1 libdrm2 libelf1 libgomp1` (apt in the image) | Preflight: look each one up with `ldconfig -p` / `ctypes.util.find_library`; print the per-distro package name when missing | To verify on the reference machine and on a clean Ubuntu |
| `/dev/kfd` + `/dev/dri` via `--device ... --group-add keep-groups` | File permissions plus the user's membership in `render`/`video` | To verify |
| ROCm userspace runtime (10.1.0) | The engine package already ships it unpacked (`rocm/`, 5.2 GB installed) with `Runner.env` supplying library paths | **Largest unknown: must be measured natively** |
| glibc 2.39 from the Ubuntu 24.04 base | Preflight `os.confstr("CS_GNU_LIBC_VERSION")` ≥ 2.39 (the pinned ROCm binaries), block with a clear message otherwise | To verify |
| Network + filesystem isolation of engine CLIs | Linux: `bubblewrap --unshare-net` or Landlock ABI ≥ 4 (kernel ≥ 6.7; the reference machine is on 7.0) around the same `Runner.prefix` hook that `sandbox-exec` uses on macOS; documented fallback if unprivileged user namespaces are restricted | To design + measure; **SECURITY.md change needs explicit approval** |
| UID mapping so files are owned by the user (`--userns=keep-id`) | Files are written by the user's own process | Solved by construction |
| Image rebuild, volume lifecycle, `hadolint` | Deleted | Solved by construction |

### 2.2 Deleted by this plan

- `server/Containerfile`, `.containerignore`, `server/entrypoint.sh`, `scripts/run-server.sh`
- The Podman-specific half of `scripts/lp-env.sh` (`lp_volumes`, `lp_mounts`, `lp_mountpoint`, `lp_gpu`) and every named volume
- The hadolint CI job; Podman from `README.md`, `CONTRIBUTING.md` and the dev setup
- `server/requirements.txt` → `server/requirements.linux.txt` (same pins, same hashes, renamed for symmetry)
- The rootless-Podman pitfalls in `AGENTS.md` (`podman unshare rm -rf`, container-owned files, `PYTHONDONTWRITEBYTECODE` inside images) become obsolete

That removes a whole class of bugs (uid-owned files, image rebuilds, volume lifecycle, two env definitions) and replaces them with one mechanism that is already exercised on macOS — at the cost of the isolation guarantees above, which are re-established or explicitly accepted in `SECURITY.md`.

---

## 3. Target architecture

Three tiers, one shared core. The desktop app becomes the canonical runtime; the headless server (either OS) is the same core started by `lp up`; `make` stays the developer path. No containers anywhere.

```
        ┌───────────── pinned assets: URL + size + SHA256 + Ed25519 signature ─────────────┐
        │  engine packages (per GPU stack)          models (Fast / Quality / Full)         │
        └───────────────┬───────────────────────────────────────┬──────────────────────────┘
                        │ download at run time (resume, verify)  │ opt-in, resumable
   ┌────────────────────▼───────────────────────────────────────▼──────────────────────────┐
   │  desktop shell (Tauri v2, Rust)                                                       │
   │  splash + preflight · single instance · tray · quit guard · updater                   │
   │  └── sidecar: bundled Python 3.12 + server/app + web/dist + catalog                   │
   │        └── app.supervisor ──► API+UI 127.0.0.1:<port> · matting 127.0.0.1:8083         │
   │                              └── engine CLI (sd-cli / trellis-cli) under sandbox      │
   └───────────────────────────────────────────────────────────────────────────────────────┘
             same `server/app`, same `web/`, same `catalog/`, same env contract, same directories
   ┌──────────────────────────────────────────┐   ┌──────────────────────────────┐
   │ headless native (both OSes): `lp up`     │   │ `make web-dev` (UI only)     │
   │ uv venv + pidfile or user systemd unit   │   │ API + web watch, no GPU      │
   └──────────────────────────────────────────┘   └──────────────────────────────┘
```

### 3.1 Shell (Tauri v2)

- One main window whose URL is the local server (`http://127.0.0.1:<port>`), so the UI code path is identical to the browser and `web-dev` paths. No second asset pipeline.
- A separate small splash window with **embedded HTML** (it must work before Python starts).
- Sidecar: `resources/runtime/{python,server,web,catalog}` inside the bundle; spawn
  `resources/runtime/python/bin/python3 -m app.supervisor` with `cwd=resources/runtime/server` and the env contract (§3.3). Tauri's `externalBin` is for one file, so this is a direct `std::process::Command` with the resource dir.
- Lifecycle: start splash → preflight → start supervisor → wait for both `/health` → show main window → close splash. On Quit: SIGTERM, wait 10 s, kill the process tree, remove `runtime.json`. If a job is running, ask first (job state is already persisted as failed on restart, `jobs.py`).
- `tauri-plugin-single-instance`: a second launch focuses the existing window instead of starting a second server.
- Tray with Open / Show log / Quit; `tauri-plugin-updater` for the shell only (engine/model updates stay on the Engines/Models pages, which already check versions and upstream releases).
- Capabilities: no filesystem/shell permission for the webview; all privileged actions are Rust commands.

### 3.2 Runtime (Python, identical everywhere)

- **`server/app/supervisor.py`** replaces *both* `server/entrypoint.sh` and `scripts/run-native.sh _supervise`:
  start matting + API, wait for both `/health`, forward SIGTERM/SIGINT, kill the whole process tree (needed for `sd-cli`/`trellis-cli` children), write `<data>/runtime.log` (same name on both platforms, replacing `container.log`/`native.log`), exit with the first child's failure code.
  The supervisor is the only process model: `entrypoint.sh`, `_supervise` and the container's `ENTRYPOINT` are gone. macOS and Linux start the same module; on Linux a generated `systemd --user` unit (optional, for "start at login" on a server) wraps the same command.
- **`server/app/runtime_env.py`**: one definition of `MODELS_DIR`, `ENGINES_DIR`, `LIBRARY_DIR`, `DATA_DIR`, `U2NET_HOME`, `PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED`, `OMP_NUM_THREADS`, `HOST_*`, plus thread-count derivation per host (macOS `hw.perflevel0.physicalcpu`, Linux `sched_getaffinity`), used by the supervisor, `lp`, and tests. Nothing duplicates it: the deleted `Containerfile` and `entrypoint.sh` were the only other copies.
- **`paths.data_root()`**: macOS `~/Library/Application Support/local-producer`, Linux `~/.local/share/local-producer`, overridable with `LP_HOME`. Same sub-layout on both (`models/ engines/ library/ server/ venv/`). There are no named volumes and no bind mounts any more: the desktop app, `lp up` and `make` all see the same plain tree.
- **Discovery file** `<data>/runtime.json`, mode 0600, written atomically:
  `{"url": "http://127.0.0.1:13305", "port": 13305, "pid": 1234, "version": "0.0.0", "token": "...", "started": 1762...}`
  Port: try 13305, fall back to an ephemeral port. The desktop app always enables the token; the webview obtains it through a one-time `/v1/session` bootstrap that sets a `SameSite=Strict` cookie, and `security.py` rejects state-changing requests whose `Origin` is not the local server. (Today `SERVER_TOKEN` is optional and the server is reachable by any page in any local browser.)
- The token is on by default when the supervisor starts the server (desktop app and `lp up`); `lp up --no-token` is the explicit opt-out for local scripts that cannot read `runtime.json`. `runtime.json` is written in both cases.

### 3.3 Asset tier

- `catalog/engines.json` and `catalog/models.json` gain a detached **Ed25519 signature**; the public key is embedded in the app and the server. A compromised mirror cannot push arbitrary binaries. Verification happens before install, next to the existing SHA256 check.
- Engine package metadata becomes explicit instead of implied by code: `platforms`, `requires` (e.g. `cmake`/`xcode-clt` for dev builds only), `features` (`decimate_on_gpu: false` for Metal, `quantized_weights: true`, `resident_server: false`). `GET /v1/system` and the Engines page show it, so a user sees "this package decimates on the CPU" instead of discovering it as slowness.
- **macOS engine becomes a normal download.** `trellis.cpp` has no macOS release, so CI (macos arm64 runner) builds `trellis-cli` once per version and publishes it as a pinned item. End users never need CMake/Xcode CLT. `build.py` stays as a maintainer path (`make engines` with `--from-source`).
  **One artifact, no tuned variants.** Build baseline (`-DGGML_METAL=ON`, no `GGML_NATIVE`): a binary tuned to the CI machine's CPU is not portable, and shipping per-chip artifacts multiplies the QA matrix for an unmeasured gain. The cost of baseline is measured once (same input, n ≥ 3) and recorded; if it turns out to matter, that is a later decision, not a silent second artifact.
- Model profiles are named once and used by splash, the Models page and the add-on: **Fast** (Q4_0 + TRELLIS.2 q4, 13.37 GB), **Quality** (Q8_0 + q8, 18.44 GB), **Full** (F16, 27.95 GB). Shared components are always installed first (7.26 GB), so a profile switch only downloads the main models.

### 3.4 Compatibility scan (LM Studio-style)

One artifact per OS means the app must be able to answer "can this machine run it, and what did you detect?" by itself — the way LM Studio scans the machine, picks a runtime and shows a verdict. Here that becomes a module, `server/app/engines/compat.py`, used by the splash, `lp doctor`, the Engines page and every job failure message.

| Field | Linux | macOS |
| :--- | :--- | :--- |
| GPU model | KFD topology (`host.amd_targets()`) | `machdep.cpu.brand_string`, `ioreg` AGXAccelerator |
| gfx target(s) | KFD `gfx_target_version` → `gfx1103` | n/a |
| Kernel driver version | `modinfo -F version amdgpu` (source to confirm in P2) + running kernel | n/a |
| Userspace stack | the engine package's ROCm version (`rocm/`), confirmed by the runner `self_test` | the engine package's ggml/Metal build, confirmed by `--help`/`--version` |
| glibc | `os.confstr("CS_GNU_LIBC_VERSION")` | n/a |
| OS version | `/etc/os-release` | `platform.mac_ver()` |
| Required kernel parameter | `cwsr_enable` (already `backends.preflight`) | n/a |
| Device access | `/dev/kfd`, `/dev/dri/renderD*`, user groups | n/a |
| Artifact claims | catalog `gfx_targets`, `min_glibc`, `min_macos`, `features` | same |

Verdicts, one per installed package, shown on the splash and the Engines page:

- **compatible** — every required check passed; print what was detected, not just "OK".
- **degraded** — runs with a known limit (e.g. Metal has no GPU decimation; a Vulkan fallback caps res at 512); jobs above the limit are refused with the reason.
- **incompatible** — exactly one blocking reason plus a remediation (a copyable command or a link), never a bare "failed".

Rules that keep the scan trustworthy:

1. A field that cannot be read is `unknown`; `unknown` on a required field is `incompatible`. No guessing, no "probably fine".
2. The verdict goes into `preflight.json` and is repeated in job errors, so a bug report carries it.
3. With one artifact per OS, a wrong verdict is a blocking bug: tests use recorded fixtures (ioreg and sysfs dumps from the M4, the 780M, and one unsupported machine), not the live machine.
4. Not in v1 (decided 2026-11-04): add a `vulkan-linux-x86_64` fallback package only when a user report shows `incompatible` happens in practice. Upstream ships Vulkan builds, and `AGENTS.md` already records that res 1024 on Vulkan can exceed the 2 s lockup, so such a package would carry `max_res: 512`. The scan already models "degraded with a limit", so this is a catalog entry plus one measurement, not new code.

---

## 4. Repository changes (by file)

| Path | Change |
| :--- | :--- |
| `server/app/supervisor.py` | new: the only process model, both OSes (replaces `entrypoint.sh` and `run-native.sh _supervise`) |
| `server/app/runtime_env.py` | new: env contract + thread derivation |
| `server/app/settings.py` | `Paths` defaults from `data_root()`; one function for both platforms |
| `server/app/security.py` | token on by default; `/v1/session` cookie bootstrap; Origin check |
| `server/app/engines/sandbox.py` | new: one `Runner.prefix` per platform — `sandbox-exec` (macOS), `bwrap --unshare-net` / Landlock (Linux) |
| `server/app/engines/compat.py` | new: compatibility scan and verdicts (compatible / degraded / incompatible), read by the splash, `lp doctor`, the Engines page and job errors |
| `server/Containerfile`, `.containerignore`, `server/entrypoint.sh`, `scripts/run-server.sh` | **deleted** (no containers) |
| `scripts/run-native.sh` | reduced to build/setup helpers; supervisor logic removed |
| `scripts/lp-env.sh` | single layout definition; no volumes, no GPU device flags |
| `scripts/lp` | new CLI: `up down status logs exec setup doctor` (same on both OSes) |
| `scripts/systemd/local-producer.service.in` | new (optional): `systemd --user` unit wrapping the same supervisor, for a Linux box that should start at login |
| `scripts/lock-requirements.sh` | new: regenerate both locks, fail if `name==version` sets differ; `make lock-check` |
| `server/requirements.in` | unchanged (single source) |
| `server/requirements.txt` → `requirements.linux.txt` | rename for symmetry; header recipe moves into the script |
| `desktop/src-tauri/` | new: Tauri app (window, splash, preflight, spawn, tray, updater, single instance) |
| `desktop/runtime/` (build output) | bundled Python + `server/app` + `web/dist` + `catalog/` (not committed) |
| `server/catalog/engines.json` | macOS baseline artifact item (no `GGML_NATIVE`); `platforms`, `requires`, `features`, `gfx_targets`, `min_glibc`, `min_macos` (the scan's inputs); signature |
| `server/catalog/models.json` | profiles (Fast/Quality/Full) + signature |
| `blender/local_producer/client.py`, `__init__.py` | read `runtime.json`, fall back to `DEFAULT_URL`; no change to request formats |
| `.github/workflows/ci.yml` | add `macos-14` (pytest, mypy, tsc, web build, `lp setup`, add-on zip) and a native `ubuntu-24.04` run; delete the hadolint job; add `lock-check` |
| `.github/workflows/engine-macos.yml` | new: build `trellis-cli` on `macos-14`, upload artifact, print size + SHA256 for the catalog |
| `.github/workflows/desktop.yml` | new: `tauri build`, notarize (secrets), upload DMG |
| `Makefile` | thin aliases over `scripts/lp`; `lock-check` added to `check` |
| `README.md`, `models/README.md`, `SECURITY.md`, `AGENTS.md` | document the contract and the new layout |
| `CHANGELOG.md` | one entry per phase, with the measurements listed in §10 |

What does **not** change: `web/`, the API surface, `server/app/pipelines/`, `model_store.py` / `model_setup.py` behaviour (only profile names on top), the job/Library format, the add-on's request format.

Prerequisites after this plan: `uv` (Python + locks), and on a Linux desktop build also the WebKitGTK dev/bundle deps. Node is no longer needed to *run* the server (only for `make web-dev` / rebuilding the UI from source); Podman and Docker are not needed at all.

---

## 5. Splash / preflight

Every row must auto-fix or print a copyable command. Results are written to `<data>/preflight.json`, and the UI, `lp doctor` and the log all read that one file (no second diagnosis).

| Check | Source | Action when it fails |
| :--- | :--- | :--- |
| OS + version + arch | `host.detect()` | Block: "macOS ≥ 14 on Apple silicon" (Windows: explicit "not supported in this version") |
| GPU / accelerator | `host.detect()` (`ioreg`, `/dev/kfd`) | Block when no engine package matches |
| Driver / stack compatibility | `compat.py` verdict per installed package | `incompatible`: one reason + remediation; `degraded`: the limit is shown and jobs above it are refused |
| ROCm `cwsr_enable=0` | `/sys/module/amdgpu/parameters` (`backends.preflight`) | Block + instructions (this is the known cause of GPU resets) |
| `/dev/kfd` access, groups | `os.access` + group ids | Instructions (`usermod -aG video,render`, log out/in) |
| System libs + glibc (Linux native) | `ldconfig -p` for libnuma/libdrm/libelf/libgomp; `os.confstr("CS_GNU_LIBC_VERSION")` ≥ 2.39 | Block with the per-distro package names / "needs a glibc 2.39+ distribution" |
| Sandbox ability (Linux) | probe `bwrap --unshare-net … true`, else Landlock ABI | Degraded mode: run with the network allowed, log it, show how to enable (unprivileged user namespaces) |
| Free disk | `shutil.disk_usage(data_root)` | Show real need per profile (13.4 / 18.4 / 27.9 GB + engine + results); allow "engine only" |
| RAM | `hw.memsize` / `MemTotal` | Warn below 16 GiB (16 GiB is the measured working minimum for FLUX + TRELLIS) |
| Network to catalogs | HEAD to the catalog hosts | Allow offline start with an already-installed engine |
| Engine package | install → SHA256/signature → `self_test` → `preflight` | Auto-download (resumable) or instructions |
| Models | `store.components_status()` | Offer Fast by default; resumable downloads |
| Sidecar integrity | hash of `python` + `app/` against a manifest | Block: "installation damaged, reinstall" |
| Linux webview libs | Tauri/bundle dependency | Cannot be fixed by splash: `.deb` declares `Depends: libwebkit2gtk-4.1-0`; AppImage is best effort |

---

## 6. Packaging, signing, updates

- **macOS (v1):** `.dmg` with a Developer ID Application signature, hardened runtime, notarized with `notarytool`.
  - Every Mach-O inside the bundle must be signed (Python binary, onnxruntime/Pillow `.so`, `libstable-diffusion.dylib`).
  - **Risk to test:** hardened runtime enables library validation; engine dylibs downloaded after install are not signed by us. Expected fix: entitlement `com.apple.security.cs.disable-library-validation` (narrower alternative: re-sign downloaded dylibs at install time). Must be verified on a **different** Mac with Gatekeeper on, not on the build machine.
  - Quarantine: files downloaded by the app over HTTPS do not get `com.apple.quarantine`, so engine CLIs run without a Gatekeeper prompt — to verify, not assume.
- **Linux headless (no packaging needed):** a checkout plus `lp setup`, or a tarball with the same directory shape. Nothing is installed system-wide; uninstall = delete `<data>/` and the checkout. The ROCm engine is a prebuilt download, so no compilers are needed.
- **Linux desktop (later):** `.deb` first — it declares the WebKitGTK/GTK dependencies explicitly, so a missing library is a package-manager error with a name, not a silent crash. AppImage is a fallback for distributions without `.deb`, with the FUSE/`--appimage-extract-and-run` caveat. These are ordinary package formats, not containers.
- **Updates:** two channels, never mixed. Shell → Tauri updater (signed manifest). Engine + models → existing catalog checks on the Engines/Models pages. An app update must never touch `<data>/`.
- **Install size** must be measured before any "lightweight" claim; report the DMG size and the on-disk size after install.

---

## 7. Security invariants (one statement, two mechanisms)

| Invariant | Linux (native) | macOS (native app) |
| :--- | :--- | :--- |
| Only loopback | binds 127.0.0.1 only | binds 127.0.0.1 only |
| Only the app's own UI may call the API | token on + Origin check + `SameSite=Strict` cookie | same code |
| Engine CLIs cannot reach the network | `bwrap --unshare-net`, or Landlock ABI ≥ 4 (kernel ≥ 6.7); fallback: allowed network, logged as degraded | `sandbox-exec` `(deny network*)` |
| Model downloads and conversions cannot reach the network | same `Runner.prefix` wrapper | `sandbox-exec` (already used for the download/convert path) |
| Only the data dirs are written | **no filesystem isolation** — residual risk, stated | **no filesystem isolation** — residual risk, stated |
| Assets are authentic | SHA256 + Ed25519 catalog signature | same |

`SECURITY.md` gets this table. The filesystem row is the same residual risk on both OSes now, which is the honest cost of deleting the container; the network row is a real invariant on both, but the Linux mechanism must first be shown to work (§8 item 12). Policy decided 2026-11-04: try `bwrap`, then Landlock, then run *degraded with the gap logged in `preflight.json`* — and that last fallback must be approved in writing before P6 ships, because it weakens an existing rule (`AGENTS.md`, `SECURITY.md`).

---

## 8. Risks to measure (not estimated)

1. **WebGL in WebKitGTK** — `<model-viewer>`/three.js in the Library and 3D pages. Test on Ubuntu 24.04 with the desktop build; fallback is the CPU renderer (slow). Metric: GLB opens, frames render, no console errors.
2. **macOS hardened runtime + downloaded dylibs** — §6. Test on a second Mac.
3. **Installer and installed size** — DMG size, on-disk size, `python` + `site-packages` + `web/dist` breakdown.
4. **Baseline `trellis-cli` vs the current locally tuned build** — same input, same seed/res, n ≥ 3; metric: wall time and visual output (as in `CHANGELOG.md` 2026-10-16). This is the price of one artifact; it must be quantified once, not assumed to be zero.
5. **Baseline runs on older Apple silicon** — the same CI artifact on M1/M2/M3 as well as M4 (portability is the reason for baseline; a crash or an illegal instruction on an older chip is a blocking bug).
6. **Scan correctness** — fixtures from the M4, the 780M and one unsupported machine; every verdict must match a hand-checked expectation. A false "compatible" is worse than a false "incompatible".
7. **First-run cost** — total time from DMG open to the first generated image on a clean Mac, and per-GB download throughput.
8. **Licence/redistribution** — FLUX.2-klein, TRELLIS.2, Qwen3, rembg models; must be checked before public distribution (not a code task).
9. **Supervisor parity** — kill-tree behaviour on macOS vs Linux, orphan CLI processes after Quit, job marked failed after a crash.
10. **ROCm natively, without the container (largest unknown of the migration)** — on the reference machine: `lp setup` → engine `self_test` → `preflight` → one FLUX image → one TRELLIS mesh. Metrics: wall time against the container numbers already in `CHANGELOG.md` (63 s image on HIP, 220–300 s mesh), GPU memory, `journalctl -k | grep -c -E 'GPU reset begin|ring .* timeout'` before/after (must stay equal).
11. **System library and glibc coverage** — a clean Ubuntu 24.04 and the reference machine, with nothing but `uv` installed; list every missing package the preflight finds.
12. **Linux engine sandbox** — does `bwrap --unshare-net` work for an unprivileged user on this Ubuntu (24.04 restricts unprivileged user namespaces via AppArmor), or is Landlock ABI ≥ 4 the answer? If neither: is the degraded mode (network allowed, logged) accepted?
13. **Removal is complete** — `grep -r podman` / `docker` in the repo returns nothing outside the changelog; CI green without Podman; no `Containerfile`.

---

## 9. Roadmap

Each phase ends with a measurement or a check that can fail.

| Phase | Work | Done when |
| :--- | :--- | :--- |
| **P0** | Confirm the remaining open items (§11) | Done on 2026-11-04: all five decided; nothing blocking starts P1 |
| **P1 — one contract, container deleted (no GPU)** | `supervisor.py`, `runtime_env.py`, `data_root()`, `scripts/lp`, `lock-requirements.sh` + `make lock-check`; delete `Containerfile`, `.containerignore`, `entrypoint.sh`, `run-server.sh`, volume code, hadolint; native `ubuntu-24.04` + `macos-14` CI jobs | `make check` green on both OSes in CI; `lp up` serves the UI on both with **no Podman installed**; `grep -r podman` empty outside `CHANGELOG.md`; startup time measured against the container's; bash line count removed recorded |
| **P2 — engine packages are downloads, and run natively** | CI builds one baseline `trellis-cli` (macOS, no `GGML_NATIVE`) and publishes it; catalog items for both platforms; `build.py` demoted to a maintainer path; `compat.py` scan + fixtures; ROCm engine run natively on the reference machine | Clean Mac: `lp setup` installs the engine with no CMake/Xcode CLT (artifact size + SHA256 recorded); the same artifact runs on M1/M2/M3/M4. Scan verdicts match fixtures for the M4, the 780M and one unsupported machine. Linux: engine self-test + one image + one mesh natively; resets 0 → 0; wall time vs the container numbers in `CHANGELOG.md` recorded. glibc/system-lib preflight finds nothing missing |
| **P3 — Tauri shell (unsigned, local)** | splash + preflight, spawn supervisor, main window, single instance, tray, quit guard | From launch to UI ready, measured; no orphan processes after Quit (checked with `pgrep`) |
| **P4 — onboarding** | Fast by default, resumable downloads with progress, disk check, profiles, `runtime.json`, add-on reads it | Clean Mac, no terminal: selection → download → first image; add-on connects without editing a URL |
| **P5 — distribution** | signing, notarization, DMG, Tauri updater, clean-machine test on a second Mac; **gated by the licence check (§11 #5)** | App opens on a Mac that never had the repo; Gatekeeper accepts; an app update preserves `<data>/`; the licence answers are recorded |
| **P6 — Linux desktop** | Tauri build for Linux: `.deb` first, AppImage as fallback; WebKitGTK measurement; Linux engine sandbox (`bwrap`/Landlock) finished; docs | The `.deb` installs on a clean Ubuntu 24.04 with the declared dependencies and no manual step; the same UI runs; `make smoke` green natively; the sandbox row in `SECURITY.md` is either enforced or explicitly accepted |

P1+P2 are prerequisites for "download and run": without them the app would still need a compiler, a second lock file maintained by hand, and two different execution models (container on one OS, host process on the other).

---

## 10. Acceptance criteria for v1

On a Mac that has never installed anything from this project, and without opening Terminal:

1. Download the DMG, open it, drag to Applications, launch. Gatekeeper passes.
2. Splash runs the §5 checks and reports the single real problem (if any) with a fix.
3. Choose **Fast** → 13.37 GB of pinned assets download, verify (hash + signature) and install, resumable after a network drop.
4. The UI opens; one image generates; one mesh generates; the result appears in the Library.
5. Blender + the add-on connects by itself (from `runtime.json`) and imports the GLB.
6. Quit during a job asks first; after Quit no `sd-cli`/`trellis-cli` process remains.
7. Uninstall leaves `<data>/` intact (and offers a separate "delete my data").
8. The **same build** runs on a second Mac with a different Apple silicon generation (baseline artifact, no chip-tuned variant), and the scan reports the detected chip and verdict.

Recorded in `CHANGELOG.md`: DMG size, installed size, launch-to-ready time, full onboarding time, and the numbers from §8 that apply.

---

## 11. Decisions (all resolved)

Closed 2026-11-04. Each row states the decision, why, and what would reopen it.

| # | Decision | Rationale | What would reopen it |
| :--- | :--- | :--- | :--- |
| 1 | **Loopback only.** No LAN exposure in v1; if it is ever added, token is mandatory and the binding interface is an explicit choice — never "open without a token" | The API has no accounts and accepts models from arbitrary http(s) links/uploads; on a LAN that is arbitrary file write followed by parsing in the engine, i.e. the exact scenario the sandbox exists for. The add-on runs on the same machine | A concrete request to drive the server from another machine (render machine, team use) |
| 2 | **No resident `sd-server` in v1.** Keep process-per-job; re-decide after the P3 image-path measurements | Saves 16 s on a 125 s job (~13 % of an image, ~3 % of the 628 s chain) at the cost of a lifecycle manager and ~8.6 GiB held idle in 16 GiB. The performance plan may shorten the image job to ~70 s, making the 16 s more valuable — measure then | Image job significantly shorter after the VAE/cache work, or a desktop app that already supervises long-lived processes well |
| 3 | **Linux sandbox: `bwrap --unshare-net` → Landlock ABI ≥ 4 → degraded with the gap logged.** The degraded fallback must be approved in writing before P6 ships | Preserves the invariant where the OS allows it; never silently drops it. Ubuntu's AppArmor restriction on unprivileged user namespaces is the known obstacle; the reference kernel (7.0) is new enough for Landlock | `bwrap` and Landlock both unavailable *and* the written approval refused → stay on P1–P5 scope (macOS only) and revisit Linux |
| 4 | **No Vulkan fallback package in v1.** `incompatible` is reported with remediation | Adds a package to pin, test and document for a slower, res-limited path (res 1024 exceeds the 2 s lockup on Vulkan). The scan already models `degraded` + `max_res`, so adding it later is a catalog entry | A user report that `incompatible` is common on real Linux machines (no telemetry, so reports are the only signal) |
| 5 | **Weight licences are checked before P5** (FLUX.2-klein, TRELLIS.2, Qwen3, rembg) for automatic download, bundling and attribution | Public distribution is the point of P5; this is a legal gate, not a code task | — (a licence that forbids automatic download would change the onboarding design, not just the docs) |

Everything else still listed as unknown is a **measurement**, not a decision: see §8 (13 items, each with its metric and, where relevant, the machine it needs).

---

## 12. References

- Today's runtime (all scheduled for deletion or rewriting): `scripts/run-server.sh`, `scripts/run-native.sh`, `scripts/lp-env.sh`, `server/entrypoint.sh`, `server/Containerfile`
- `server/app/settings.py` (`Paths`), `server/app/engines/{host,backends,registry,build}.py`, `server/app/security.py`, `server/app/jobs.py`
- `server/catalog/{engines,models}.json` (sizes and pins quoted in §2)
- `blender/local_producer/{__init__,client}.py` (`DEFAULT_URL`, `api_url` preference)
- `.github/workflows/ci.yml` (six jobs, all ubuntu-24.04)
- `models/README.md` (paths per platform), `SECURITY.md` (isolation rows)
- `CHANGELOG.md` 2026-11-03 (M4 numbers, macOS native server, Metal engine package)
- Upstream: `leejet/stable-diffusion.cpp@master-964` (macOS zip has `sd-cli` + `sd-server`), `pwilkin/trellis.cpp@c0bed38` (no macOS release; `build.py` path)
