# local-producer — performance bottleneck analysis and plan

| | |
| :--- | :--- |
| **Status** | Study (historical record). No repository change came from it yet; the plan's phases are tracked in `CHANGELOG.md` and the architecture docs. |
| **Owner** | maintainer |
| **Last verified** | 2026-11-04 |
| **Date** | 2026-11-04 |
| **Machine** | Mac mini M4 (4P+6E, 10-core GPU, 16 GiB unified), macOS. The server runtime is **not installed here** (no `~/.local-producer`, no models, no engine package). |
| **Scope** | Wall-clock of the two GPU paths (FLUX.2 image, TRELLIS.2 mesh), then server/UI overhead. |

Every number below is either **measured** (with its source) or marked **hypothesis**. Per
`AGENTS.md`, nothing is estimated silently.

---

## 1. Where the time goes

### 1.1 GPU pipelines (measured; CHANGELOG 2026-11-03, M4 16 GiB)

| Step | Total | Breakdown |
| :--- | ---: | :--- |
| FLUX.2-klein-4B q8_0, 1024², 4 steps | **125 s** | model load 16 s · text encode 6.7 s · sampling 80 s (~20 s/step) · VAE decode 38 s (tiling 256) |
| FLUX.2 image edit (A-pose), 1024², 3 steps | **184.6 s** | same pipeline + reference image; ~1.5–2x a generate (HIP: 140 s vs 63 s) |
| Matting (rembg isnet + fill_holes) | **1.4–3.0 s** | 2.4 s first call, then 1.44–1.55 s (n=4) |
| TRELLIS.2 q8, res 512, 6 steps | **300–315 s** | flows 102.9 (sparse structure, 11 forwards) + 68.1 (shape) + 41.3 (texture) = 212 s · **"rest" ≈ 88 s** |
| Full chain (`make smoke`) | **628 s** | generate 125 + edit 185 + matte 3 + mesh 315 |

### 1.2 Server/UI overhead (measured on this machine today, n=12 / n=10 / n=3)

| Item | Measured | Where |
| :--- | :--- | :--- |
| `ioreg -r -d 1 -c IOAccelerator` (GPU memory probe) | **11.2–13.8 ms**, median 11.7 ms | `server/app/engines/backends.py:43`; called by `/v1/system` and `/health`, polled every 1–3 s by the app bar |
| `manager.list(limit=500)` (deep-copies 500 `Job`s) | **3.0 ms** per call | `server/app/routes/system.py:52` (`/v1/system` only needs counts) |
| first `tail(200)` on a 131.6 MiB log (`deque(f)`, reads the whole file) | **27–29 ms** | `server/app/routes/system.py:71`; `server.log` has no rotation |
| `/v1/jobs/{id}/files/{name}` responses | no cache headers; Starlette 1.8.0 `FileResponse` does not handle `If-None-Match` | 8.2 MiB GLB @512, 22 MiB @1024 re-sent on every view |

The app bar (`web/src/hooks/useServerActivity.ts`) polls two endpoints: `/v1/system` +
`/v1/jobs?limit=20`, every 1 s while a job is active and 3 s when idle. Total server cost
there is ≈15 ms per busy poll (~1.5 % of one core) — a smoothness matter, not a
throughput bottleneck.

**Conclusion: >98 % of wall-clock is inside `sd-cli` / `trellis-cli`.** Optimise the CLI
invocations and their inputs; the Python/UI work is second-order.

---

## 2. Ranked bottlenecks

### #1 TRELLIS "rest" 88 s — 29 % of a mesh job, 21 % of the character chain

What it contains: DINOv3 image encoder, SS/shape/texture decoders, model load, and
post-processing. On Metal the post-process loses its GPU paths:

- **Measured upstream fact (source pinned at `c0bed38`, `src/decimate_qem.cpp`):** QEM
  decimation has GPU implementations for CUDA/HIP and Vulkan; there is none for Metal, so
  it falls through to `decimate_qem`'s CPU path. The CPU path has **no threading** (no
  `std::thread`/OMP in that file).
- **Measured upstream fact (`src/deform_conv_cpu.cpp`):** deformable conv also has only a
  CPU fallback on Metal (parallel over output channels, still CPU).
- **Upstream figure (not measured by us):** 5.4M → 300k-face decimation ≈ 5 s on ROCm
  (gfx1151) vs ~18x that on the single-threaded CPU path (~90 s).
- **Upstream figure (not measured by us):** the same pipeline on an M5 24 GB, res 512,
  12 steps takes 9:21 with 5.6 GB peak RSS, "all neural stages on Metal".
- **Expected in our log:** `[decimate] GPU decimation unavailable; falling back to the CPU
  path (output is unaffected)` (printed to stderr, forwarded by `run_cli`).

Hypothesis: most of the 88 s is the single-threaded CPU decimation of the 1.4M-face
(raw) res-512 mesh, plus the CPU deformable conv and the model load. Must be confirmed
with `--verbose` timings before any code change.

Levers, cheapest first:
1. Profile with `trellis-cli --verbose` (upstream: "graph timings and progress
   heartbeats").
2. Quick knobs: `--atlas 512` (smaller bake), `--no-texture` for rig-only runs (skips the
   texture flow 41 s and its decoder).
3. Parallelise the CPU QEM path (fork, moderate effort, output should stay identical).
4. Port decimation to Metal (big effort; upstream would be the right home).

### #2 FLUX renders 1024² but TRELLIS only consumes 512² — 4x the pixels

- **Measured upstream fact (`src/trellis_cli.cpp:285`):** `dinov3_encode(m, chw, 512)`
  for the res-512 path; only the 1024 cascade encodes at 1024.
- **Measured (CHANGELOG 2026-10-14, HIP):** 768² q8_0 = 41.0 s vs 1024² = 63.0 s
  (−35 %): sampling 25.6 vs 40.7 s, VAE decode 10.4 vs 19.9 s.
- **Measured (CHANGELOG 2026-10-14):** at 768² "the design changes and detail is lost"
  — for a standalone image. For a 3D input this does not matter because the mesh encoder
  resizes to 512² anyway (**hypothesis for the mesh side; needs a visual A/B**).

Expected on the M4: ~30 s saved per generate, ~50–60 s per A-pose edit, ~15 % of the
character chain. The add-on and the web 3D flow should default to 768² for the image
stage while the standalone Image page keeps 1024².

### #3 FLUX VAE decode 38 s — 30 % of an image job

- **Measured (CHANGELOG 2026-11-03):** tile 256 = 38 s (current); tile 512 = 28.6 s but
  slightly pale; tile 1024/untiled = 15.4 s but clearly washed out (RGB std 45 → 39 → 34).
  The wash also appears with a single tile, so it is probably not seam blending alone
  (**hypothesis**).
- **Measured upstream fact (sd.cpp master-964, `examples/common/common.cpp`):**
  `--vae-tile-overlap` (fraction, default 0.5) and `--vae-relative-tile-size` exist.
  Our pipeline passes only `--vae-tiling` (`server/app/pipelines/flux.py:26`).

Experiment: tile 384/512 with overlap 0.7/0.85, compare wall time and RGB statistics
against the 256 baseline. If colour holds: −10…20 s per image.

### #4 FLUX sampling 80 s — step count and cache modes

- **Measured (CHANGELOG 2026-10-14):** 3 steps at 1024² = 53.8 s on HIP (vs 63.0 s at 4
  steps), small pose/design changes; rejected as a default.
- **Measured upstream fact (sd.cpp master-964):** `--cache-mode
  easycache|ucache|dbcache|taylorseer|cache-dit|spectrum` and `--cache-option`
  (threshold/start/end/…). One skipped step of four ≈ −20 s on the M4. Quality with a
  4-step distilled model is unknown (**hypothesis: risky**).
- `--flash-attn on` everywhere, `--mmap`, q4/q6 weights were already measured and did not
  win (CHANGELOG 2026-11-03 / 2026-10-14).

### #5 Model load per job — `sd-server` is available (13 % of an image job)

- **Measured on this machine:** the pinned macOS sd.cpp zip
  (`sd-master-1d0a58a-bin-Darwin-macOS-26.6.2-arm64.zip`) contains `sd-cli` (3.6 MB) and
  `sd-server` (5.2 MB).
- **Measured (CHANGELOG 2026-11-03):** FLUX model load is 16 s per process; `--mmap` cut
  the load to 0.6 s but total time was unchanged (page faults moved into sampling).
- A resident `sd-server` would remove the 16 s per image job and can cache prompt
  conditioning (6.7 s text encode is per prompt). Cost: ~8.6 GiB held idle; it must be
  stopped before a TRELLIS job (2.1 GiB) to stay safe in 16 GiB.
- `trellis-server` also exists upstream and keeps the process resident, but its HTTP API
  accepts only seed/resolution/bg_removal — our steps/atlas/guidance/texture/token
  parameters would be lost. Not attractive as-is.

### #6 A-pose edit 184.6 s — ~2x a generate (profile first)

Same effect on HIP (140 s vs 63 s). Hypothesis: VAE encode of the 1024² reference plus
heavier sampling with image tokens. Measure with `sd-cli -v` stage lines, then decide.
768² (#2) is the biggest lever here. Also note the framing already asks for "arms slightly
away from the body", so the edit is optional for characters that will not be rigged tightly.

### #7 Server/UI micro-costs (~1–2 % CPU, perceived latency)

1. Cache `gpu_mem()` for 1–2 s instead of spawning `ioreg` (11.7 ms) per poll.
2. `/v1/system`: count queued/running without `manager.list(500)` (3 ms of deep copies).
3. Rotate `server.log` (e.g. 8 MiB) and read the tail by seeking back instead of
   `deque(f)` over the whole file (29 ms per 131 MiB, growing forever).
4. Result files are immutable (`<job id>/<name>`): send `Cache-Control: immutable` and
   handle `If-None-Match` (Starlette's `FileResponse` does not), so the 8–22 MiB GLB is
   not re-sent on every Library open.
5. Optional: no gzip/brotli on `web/dist` (model-viewer chunk 1.0 MB, app 326 KB
   uncompressed); only matters on a first load.

Not worth attacking: the job queue is serialised on the GPU lock by design; CPU matting
(1.5 s) could overlap a GPU job but saves at most 1.5 s per mesh.

---

## 3. Plan

### Phase 0 — prerequisites for measurement

This machine has no runtime. To measure GPU changes: `make server-up && make engines &&
make models` (~25 GB of downloads; the engine `trellis-cli` is built from source). Otherwise
run the same commands on the machine that already has the runtime and paste the logs.

### Phase 1 — no GPU needed, low risk (~30 min + tests)

- Cache the GPU-memory probe (1–2 s TTL) and stop building a 500-job list for `/v1/system`.
- Log rotation + tail by seek.
- Cache headers / conditional requests for job result files.
- Unit tests; `make check`; no behaviour change to jobs.

### Phase 2 — GPU A/B measurements (record every result in `CHANGELOG.md`)

Time: n ≥ 3, report the spread; visuals: n = 1 with close-ups, as in earlier entries.

1. `trellis-cli --verbose` on the cat sample → exact split of the 88 s "rest".
2. TRELLIS `--threads 4` vs default (10) — CPU post-process on 4P+6E.
3. TRELLIS `--atlas 512`, `--no-texture` (time and GLB size).
4. FLUX 768² vs 1024² end to end, then the mesh from both inputs (faces, close-up).
5. VAE tiling sweep (tile 384/512 × overlap 0.5/0.7/0.85): time + RGB std vs baseline.
6. FLUX `--cache-mode easycache` (and one block-level mode) at 4 steps: time + visual.
7. `sd-cli -v` on an A-pose edit to explain the 185 s.

### Phase 3 — larger changes (needs a decision)

- Fork `trellis.cpp`, parallelise the CPU QEM decimation (or port it to Metal), pin the
  fork commit as a new `metal-arm64` engine package. Largest mesh win (~20–60 s).
- A resident `sd-server` for the image path (saves 16 s/job, needs lifecycle + memory
  management under the GPU lock).

---

## 4. Open decisions

1. Where to measure: install the runtime here (~25 GB) or run the Phase 2 script on the
   machine that already has it?
2. Accept faster defaults with a quality trade-off: 768² for image-to-3D, mesh 6 steps
   instead of 8, `--no-texture` for rig-only runs?
3. May the project fork/patch `trellis.cpp` (parallel QEM or Metal kernels) and pin it as
   an engine package, or must engine sources stay untouched upstream?
4. Priority: Phase 1 micro-fixes first, or go straight at the mesh path?

## 5. References

- `server/app/pipelines/flux.py` (`flux_args`, `_run_sd`), `trellis.py` (`run`, CLI args),
  `matte.py`, `server/app/gpu.py` (`run_cli`, lock, logging).
- `server/app/routes/system.py` (`/v1/system`, `/v1/logs`), `server/app/jobs.py`
  (`list`, `public`), `server/app/engines/backends.py` (`apple_gpu_memory`).
- `web/src/hooks/useServerActivity.ts`, `usePoll.ts`, `useJob.ts`.
- `CHANGELOG.md` 2026-11-03 (M4 numbers), 2026-10-14 (FLUX sweep, incl. 768² and VAE
  tiling), 2026-10-16 (hard surface; atlas cost), 2026-10-13 (TRELLIS steps/fa-fast).
- Upstream pinned sources: `pwilkin/trellis.cpp@c0bed38` (`src/decimate_qem.cpp`,
  `src/deform_conv_cpu.cpp`, `src/trellis_cli.cpp`), `leejet/stable-diffusion.cpp@master-964`
  (`examples/common/common.cpp`).
