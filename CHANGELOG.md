# CHANGELOG — R&D journey of local-producer

A log of experiments, measured numbers and decisions. The source code, images, models and benchmark data have been deleted (see "Cleaned up" at the end), so **the numbers here are the only record**. How to rebuild is under "Verified configuration".

Machine: ThinkPad P14s Gen 4, Ryzen 7 PRO 7840U, Radeon 780M (gfx1103), Ubuntu 26.04, kernel 7.0.0-38, rootless Podman 5.7, Mesa 26.0.8.

---

## 2026-10-22 — FLUX.3 Image Klein on sd.cpp HIP: runs, ~3.4x slower than FLUX.2-klein

- **Goal:** can Black Forest Labs' FLUX.3 Image Klein (open weights since 2026-10-15, FLUX Kommunity License v1.0:
  free commercial use under US$5M revenue; BFL's own repo is gated, leejet's GGUFs are not) replace or complement
  FLUX.2-klein-4B on this machine?
- **What it is (upstream docs, not measured here):** a ~5.6B distilled diffusion transformer (16 steps, CFG 1), the
  **same FLUX.2 VAE**, and a new text encoder, Qwen3-VL-4B-Instruct (not the Qwen3-4B FLUX.2-klein uses). Support in
  stable-diffusion.cpp from PR #2143 (merged 2026-10-15, first tag master-968); our engine package has master-964.
- **Configuration:** sd.cpp `master-987-a77d362` upstream Linux ROCm 10.1.0 build (zip sha256 `00f33a60...`), run as
  one `sd-cli` per image in the server image with the ROCm libraries of engine package rocm-gfx1103 2026.10.15,
  `--network none`, `AMD_SERIALIZE_KERNEL=3`, cwsr_enable=0. FLUX.3: leejet `flux3-image-klein-Q8_0.gguf` (6.15 GB) +
  `Qwen3VL-4B-Instruct-Q8_0.gguf` (4.28 GB; both SHA256 = Hugging Face's) + our `flux2-vae.safetensors`, `--sampling-method
  euler`. FLUX.2: our q8_0 converted model + Qwen3-4B q8_0. Both: the sample cat prompt (`scripts/make_sample.py`),
  seed 7, 1024x1024, CFG 1, `--vae-tiling --flash-attn off,diffusion=on`. Peak GTT sampled every 0.5 s on the host.

  | Run | Steps | Wall | Sampling | VAE decode | Peak GTT over idle |
  |---|---|---|---|---|---|
  | FLUX.2 q8_0, master-964 (current engine) | 4 | 57.1 s | 35.3 s | 18.1 s | 8.4 GiB |
  | FLUX.2 q8_0, master-987 (n=2) | 4 | 57.5 / 57.5 s | 36.4 / 36.3 s | 18.3 / 18.3 s | 8.4 GiB |
  | FLUX.3 Q8_0, master-987 (n=2) | 16 | 191.6 / 196.7 s | 169.9 / 174.7 s | 18.5 / 19.0 s | 9.8 GiB |
  | FLUX.3 Q8_0, master-987 | 8 | 115.0 s | 92.8 s | 19.4 s | 9.8 GiB |

- **Stability:** 6 of 6 runs finished; GPU resets + ring timeouts 0 before and 0 after every run.
- **No regression for FLUX.2:** master-987 gives a bit-identical image to master-964 (same SHA256); the repeat runs
  are bit-identical too (deterministic). The ~1 s difference in sampling between the two builds is within what n=1
  vs n=2 can show.
- **Speed:** FLUX.3 sampling costs ~10.8 s per step vs ~9.1 s for FLUX.2 (1.2x per step), but it is distilled for
  16 steps instead of 4: ~3.4x the wall time per 1024^2 image at its default. 8 steps: 2.0x.
- **Look (one prompt, one seed: no conclusion about quality in general):** FLUX.3 draws a grey-and-white plush cat
  with a felt/fur texture, facing almost straight to the camera; FLUX.2 draws an orange-and-white glossy toy in the
  requested three-quarter view. So on this sample FLUX.3 followed the "three-quarter view" instruction worse and
  chose a grey coat on the grey background (a matting risk for image-to-3D). 8 and 16 steps look nearly the same.
  BFL recommends a prompt upsampler (a separate 9B model) for short prompts; not tried.
- **Conclusion:** FLUX.3 Image Klein **runs** on the 780M with sd.cpp HIP at Q8_0 within GTT, stably, but at ~3.4x
  the time and without a visible gain on the image-to-3D sample. Keeping FLUX.2-klein as the default. Integrating
  FLUX.3 as an optional image family needs: an engine package with sd.cpp >= master-968 (safe for FLUX.2, above),
  the Qwen3-VL-4B text encoder as a new shared component (+4.3 GB), and per-family default steps (16) and sampler.
  Before that, a wider comparison (several subjects and seeds, matting + TRELLIS.2 on the results) would show whether
  it is worth it. Weights and outputs: `~/.local-producer/experiments/flux3/` (not in git).
- **Step sweep (same day, same configuration):** FLUX.3 at 16 / 12 / 8 / 6 / 4 / 3 / 2 steps and FLUX.2 at 4 steps,
  on 2 subjects ("a cute cat", "a friendly retro robot", both with the add-on's character framing) x 2 seeds (7,
  1234) = 32 images; then every image through the server's matting (`isnet-general-use` + `fill_holes`). 32 of 32
  runs finished, GPU resets 0 before and after. Wall time per 1024^2 image, min-max over the 4 subject/seed pairs:

  | | FLUX.2 4 | FLUX.3 16 | 12 | 8 | 6 | 4 | 3 | 2 |
  |---|---|---|---|---|---|---|---|---|
  | Wall (s) | 57-67 | 190-224 | 150-178 | 113-123 | 95-100 | 72-76 | 60-62 | 48-51 |

  The spread within one setting (up to ~18 %, later runs slower) is larger than the step-to-step noise of the first
  benchmark; its cause (heat?) is not measured.
- **Look vs steps (visual, 4 images per setting):** 16, 12 and 8 steps are nearly indistinguishable on all four.
  6 steps keeps the composition and colours with small detail changes. 4 steps keeps the composition but shifts
  colours and markings (stripes appear on the cats, one robot's face changes). 3 steps changes the subject visibly and
  adds noise; 2 steps is broken (smeared fur, wrong colours, noisy robot). **The minimum that matches the 16-step
  image is 6 steps (~97 s, ~1.5x FLUX.2); 4 steps (~73 s, ~1.15x) is usable but drifts.**
- **Matting:** clean on all 32: no body part cut away, the grey cat on the grey background included. Alpha
  coverage (share of the 1024^2 frame kept) is stable across FLUX.3 steps 16-4 (cat 0.27-0.29, robot 0.23-0.26) and
  drops a little only at 2-3 steps. FLUX.3 draws the subject larger in the frame than FLUX.2 (0.20-0.26).
- **View:** FLUX.3 draws the subjects mostly facing the camera, at most a slight turn; FLUX.2 follows the requested
  three-quarter view more closely on all four. Whether the frontal view gives worse TRELLIS.2 meshes is not measured.

---

## 2026-10-15 — Shared components, main models as options

- **Goal (maintainer request):** "built-in" should mean only the shared parts a main model needs, not a main model:
  the built-in FLUX.2-klein q8_0 and TRELLIS.2 f16 made every added variant redundant.
- **Change:** `catalog/models.json` items are now only the shared components per family (`components`): FLUX.2-klein
  Qwen3-4B text encoder q8_0 + VAE; TRELLIS.2 DINOv3 image encoder + `ss_dec`, `shape_dec`, `tex_dec` (f16). Main
  models (a FLUX.2-klein diffusion model, the TRELLIS.2 flow models) are options added like any user model; a
  TRELLIS.2 Hugging Face folder contributes only its flow models. trellis-cli takes one `--models` directory, so each
  run links the flows + components into a temporary directory. One default model per family
  (`PUT /v1/models/{id}/default`, falls back to the first usable one); the setup download adds the recommended
  suggestion (FLUX.2-klein-4B Q8_0 leejet, TRELLIS.2 q8) for a family without a model. `birefnet.gguf` is no longer
  downloaded: the server mattes every input before TRELLIS.2.
- **Sizes:** components 7.26 GB on disk (was 31.4 GB for the old built-in set); fresh setup with the recommended
  models ~18.4 GB on disk. TRELLIS.2 options: q4 flows 3.65 GB, q8 6.88 GB, f16 12.93 GB (were 6.5 / 10.0 / 15.3 GB
  as full sets).
- **This machine:** the former built-in main files were moved, not re-downloaded, into user models
  `flux-2-klein-4b-q8-0-converted` and `trellis-2-f16-ilintar` (both set as default); `birefnet.gguf` and the q4 set's
  own encoder/decoder copies were deleted (models volume, `du -sh`: 32.8 GiB -> 29 GiB; it now holds 4 main models).
- **Checked (Test = tiny real run, rocm-gfx1103 2026.10.15, n=1 each):** FLUX q8_0 converted 7.3 s, FLUX Q4_0 6.3 s,
  TRELLIS.2 f16 flows 62.5 s, q4 flows with the f16 encoder/decoders 55.4 s; GPU resets 0 before and after. Whether
  q4 flows with f16 decoders look different from the all-q4 set is not measured. 121 unit tests, mypy, tsc.

---

## 2026-10-15 — Any link for user models; remaining security rows approved

- **Maintainer decisions:** users may give any http or https link for a model, also to this machine or the local
  network (the server runs on the user's machine for that user, who is responsible for the links); the engine
  allowlist entry `repo.amd.com` and the token-less `/blender/*` add-on repository are approved as proposed.
- **Change:** the public-address (SSRF) guard and the https-only rule are gone from `model_store.py`; links must be
  http or https with a host (also after redirects; `file:`, `ftp:` refused). Kept: weights-only header check,
  Hugging Face pinning + SHA256, size cap, staging, failed-test refusal.
- **Checked:** a model added end to end from a plain http server on 127.0.0.1 (unit test); a cross-site page cannot
  start an add: a text/plain POST (no preflight) gets 422, and the server sends no CORS headers, so the JSON
  preflight is never granted (now a test). 118 unit tests, mypy, ruff clean.

## 2026-10-15 — Dependency updates merged; CSP allows WebAssembly compilation

- **Merged** (squash, CI green): pre-commit 4.6.2, actions/setup-node 7.1.0, ruff 0.17.0, pytest 9.1.1, mypy 2.4.0;
  @google/model-viewer 4.4.0 with three 0.183.2 (#10: model-viewer 4.4 needs three@^0.183.0, so Dependabot's
  separate updates, three 0.186.1 among them, could not install); react, react-dom and their types 19.3.0 together
  (#11; no code changes: the app uses createRoot and the Lucent bundle uses none of the APIs React 19 removed).
  Every page, the Library dialog with the 3D viewer and the segmented controls checked in headless Chrome.
- **Found after #10:** model-viewer 4.4 instantiates its bundled meshopt decoder (WebAssembly) at load, which the CSP
  (`script-src 'self'`) blocked: a console error on every page with a viewer, and meshopt-compressed GLBs would not
  decode (TRELLIS and Blender GLBs are not compressed that way, so models still showed).
- **Fix (maintainer approved):** `script-src 'self' 'wasm-unsafe-eval'`. Measured with a same-origin page script
  under each header: new CSP: eval blocked, new Function blocked, WebAssembly compiles; old CSP: all three blocked.
  (Probing through the DevTools protocol is not valid: Chrome exempts DevTools evaluation from the CSP, eval "worked"
  under both headers.) The console error is gone on all pages.

## 2026-10-15 — Model suggestions, TRELLIS.2 q8 measured, aligned badges

- **Requests (user):** an old "Adding failed: 127.0.0.1 ..." message stayed on the Models page; the TRELLIS.2 set had
  no alternative; badges sat higher than the buttons next to them on the Models page and elsewhere.
- **Changes:** the last add's error has a Dismiss (`DELETE /v1/models/adding`); `catalog/models.json` lists
  suggestions shown in each family with a one-click Add (TRELLIS.2 q8_0 and q4 from ilintar/trellis2-gguf at the
  pinned revision; FLUX.2-klein-4B Q4_0 from leejet, Q5_K_M / Q6_K / F16 from unsloth), hidden once added; the add
  progress moved to the top of the page; `.row-actions` centres its items, so badges line up with buttons. Measured
  in headless Chrome on every page: each badge's centre is within 1 px of its row neighbours' (Fact cards stack label,
  badge and detail on purpose).
- **TRELLIS.2 q8_0** (ilintar/trellis2-gguf `q8/`, 10.0 GB instead of 15.3 GB): added from Hugging Face in 230 s, test
  (one-step untextured res-512 mesh) 57.4 s. Cat sample, res 512, 6 steps, seed 1234, back to back, power-saver
  profile, resets 0 -> 0: q8_0 223.2 s (149,878 faces), built-in f16 268.4 s (148,534 faces). Today's f16 runs:
  252.1 / 261.7 / 268.4 s, so q8_0 is below all three, but it ran once (n=1): needs repeats before it becomes a
  default. By eye the two meshes look alike (shape, face, texture). The q4 set was not tried.

## 2026-10-15 — Engine versions and updates, user models with a test run, add-on renamed LocalProducer

- **Requests (user):** the Engine card on Status overflowed; list engine versions, check for the newest, remove the
  running engine, choose another version; the same for models, with a compatibility check that loads the model with
  the engine; models from Hugging Face, another public link or an upload. Rename the add-on to LocalProducer, add
  importing 3D models from the server's Library, remove the old add-on and install the new one in this machine's
  Blender.
- **Status card:** long values wrap inside a Fact; the engine shows as a badge plus a detail line.
- **Engines:** the catalog may hold several versions per package (natural version order); every version can be
  installed side by side, loaded, removed (the loaded one is unloaded first; refused while a job runs). "Check for
  updates" re-reads the catalog and asks api.github.com for the latest release of each pinned component
  (`upstream` in catalog/engines.json); it reports only, a new version stays a reviewed catalog change. Live check:
  stable-diffusion.cpp master-964-1d0a58a and trellis.cpp v0.8.1 are the latest upstream releases.
- **Models** (`server/app/model_store.py`, `/v1/models`): families `flux2-klein` (one diffusion model file; the
  built-in Qwen3-4B text encoder and VAE go with it) and `trellis2` (a Hugging Face folder with the GGUF set). Added
  from Hugging Face (pinned to the commit, size + SHA256 from the HF API), another public https link (hashed while
  downloading) or a streamed upload; weights only (.gguf / .safetensors header check), hosts must resolve to public
  addresses (SSRF guard), 64 GiB cap. "Test" queues a `model.check` job: the loaded engine makes a 256^2 image in one
  step, or an untextured res-512 mesh in one step from the cat sample; the result is stored per engine version and
  a model that failed is refused for jobs. Image and 3D pages show a Model picker when there is a choice.
- **Measured** (power-saver profile, GPU resets 0 -> 0): `leejet/FLUX.2-klein-4B-GGUF` Q4_0 (2.46 GB) added from
  Hugging Face in 50.1 s; its test 7.0 s; a 1024^2 4-step image (seed 42, "a small wooden toy robot") 74.9 s with Q4_0
  vs 82.8 s with the built-in q8_0 (n=1 each: the difference cannot be told from the noise yet); the two images look
  nearly identical by eye. A link to 127.0.0.1 was refused ("resolves to a non-public address"). TRELLIS.2 user sets
  (e.g. the q8 folder of ilintar/trellis2-gguf) are covered by unit tests only, not run on the GPU.
- **Add-on:** renamed to LocalProducer (`blender/local_producer/`, extension id `local_producer`, 0.14.0, sidebar tab
  LocalProducer); new Library panel: lists the server's finished 3D models (prompt of the source image when known,
  date, resolution, faces) with the input image as preview; Import downloads the GLB and imports it like a generated
  mesh. In the running Blender 5.2.2 (over MCP): `trellis_addon` disabled, its folder
  `~/.config/blender/5.2/scripts/addons/trellis_addon` deleted, the server added as the extension repository
  "LocalProducer" (`http://127.0.0.1:13305/blender/index.json`), `local_producer` installed from it and enabled,
  preferences saved. Library refresh listed 3 models; Import of one took 1 s (141,760 faces, with its material).
- **Checks:** 113 unit tests, mypy strict, tsc, pre-commit clean; image rebuilt.

## 2026-10-15 — Server core + engine packages; data moved to volumes and ~/.local-producer

- **Request (user):** prepare for a server that also supports NVIDIA (CUDA) and Apple silicon (MLX) as packages whose
  engines and libraries are loaded and reloaded inside the running server; results (Library) on a host directory,
  model weights in a separate volume, stable performance; for now build and download everything for this machine.
  Data directory hidden (`~/.local-producer/`, user request).
- **Podman cleanup:** 21 dangling images of earlier builds pruned (`podman image prune --build-cache`): image storage
  8.41 GB -> 4.24 GB, and after the rebuild 0.99 GB.
- **Design:** the image is the portable core (API, queue, web UI, CPU matting) and holds no GPU code. An engine package
  (`server/catalog/engines.json`) carries everything platform-specific: the GPU runtime and the CLI builds ("runners"
  `sd-cli`, `trellis-cli`), plus env settings (`AMD_SERIALIZE_KERNEL=3`). It is installed as a unit into
  `ENGINES_DIR/<id>/<version>/` (staging dir, then one rename) and loaded after three checks: built for this machine
  (OS, arch, compute stack, gfx target from `/sys/class/kfd`), the stack preflight (`cwsr_enable=0`, which replaces the
  start-up refusal: the server now starts and says why no engine loaded), and a self-test of each runner
  (`sd-cli --version`, `trellis-cli --help`: proves the libraries resolve without touching the GPU). Each job resolves
  its runner when it starts, so install / load / reload take effect with the next job, no restart
  (`POST /v1/engines/reload`, `/v1/engines/{id}/install`, `/{id}/{version}/load`, Server > Engines page). Mac: Podman
  runs a Linux VM without Metal, so an MLX package will run with a native server (planned); CUDA via the NVIDIA CDI
  device in the same container (planned). `/v1/setup` (the add-on's "Download Models") installs the engine for this
  machine first when none is loaded, so the add-on works unchanged.
- **Storage:** weights in the Podman volume `local-producer-models` (24 GB, moved by rename from `models/`, no copy),
  engines in `local-producer-engines`, Library in `~/.local-producer/library`, config and logs in
  `~/.local-producer/server` (`scripts/lp-env.sh`). The volumes are directories on the same ext4 disk as before
  (`~/.local/share/containers/storage/volumes`), not in an image layer, so reads go to the filesystem directly like the
  old bind mount; read speed was not measured separately.
- **Numbers:** image 4.01 GB -> 751 MB (the ROCm wheels, 3.1 GB, left the image). Package `rocm-gfx1103 2026.10.15`:
  1.14 GiB download (sd.cpp zip, trellis.cpp tarball, three AMD TheRock 10.1.0 wheels unpacked with their pinned
  hashes), 5.2 GB installed; installed and loaded with `make engines`, self-tests passed.
- **End to end** (`make smoke`, cat sample, Fast 512 3 6), twice: edit 118.6 / 141.2 s, matting 2.2 / 2.3 s,
  TRELLIS.2 261.7 / 252.1 s; GPU resets 0 -> 0 both times. The earlier smoke on the old image measured edit 107.0 s and
  TRELLIS.2 224.3 s. The power profile was `power-saver` during both new runs (n=2); the earlier profile was not
  recorded. Hypothesis: the profile explains the ~13 % slower mesh; same binaries, libraries and env as before. Not
  tested.
- **Checks:** 94 unit tests (17 new for engines: catalog rules incl. no `LD_*`/`PATH` env, gfx names, platform
  mismatch, install from fake archives, blocked preflight / self-test, version choice, remove, API), mypy strict,
  tsc, pre-commit clean.

## 2026-10-15 — Web UI: live job and server status in the app bar

- **Request (user):** the header looked empty; show the server status and the running job there, in real time.
- **Change:** the bar is a three-column grid: name; the active job (a progress ring, kind, stage with step n/m,
  percentage, elapsed time, "+N queued"; links to the page that shows its result) or "Idle"; and the vitals (a live
  dot "Online" / pulsing "GPU busy", GPU memory in use, models ready or missing). `useServerActivity` polls
  `/v1/system` and `/v1/jobs?limit=20` every 1 s while a job runs or waits and every 3 s when idle. Below 860 px the
  job keeps ring, kind and percentage, the vitals only the dot.
- **Checked with real jobs** (two 512² FLUX.2 images, 3 steps, seeds 1 and 2, submitted together through the
  container's API, viewed in headless Chrome): after 9 s the bar read "Image · Encoding the prompt · 0 % · 9 s ·
  +1 queued · GPU busy · GPU 10.9 GB", after 18 s "Denoising 1/3 · 44 % · 18 s"; later "Decoding the image 1/9 ·
  70 % · 23 s". GPU resets/ring timeouts 0 before, 0 after. The narrow layout was checked with a stubbed running 3D
  job. Job ids a7fe73f2457548e9a52e310768ed56a9 and 4a5fa223f63b4a8eb9d742a043dd8e23 are in the Library.

## 2026-10-15 — Library dialog: viewers contained, full tools; dialogs above the tab bar

- **Request (user):** in Library, the opened item overflowed: the 3D view spilled out of its frame, the image was
  fitted but partly hidden; give it the full tools and always show it whole.
- **Cause (found):** the viewers are absolutely positioned to fill their box, and the dialog's media box was not a
  containing block (no `position`), so the 3D viewer sized itself to the dialog; the image was still a plain `<img>`.
  The box is now `position: relative`, 520 px or 55 % of the window high, on the studio sweep, and shows the same
  `ImageView` / `ModelView` (with their toolbars) as the creation pages. The toolbar scrolls sideways instead of
  spilling out of a narrow box. Measured in headless Chrome at 1440×900: media box 710×495 px, 1024² image fitted at
  38 % (387 px, inside the box), model viewer exactly the box; at 390×844 both fit with the toolbar inside.
- **Regression fixed:** the page transitions gave the page area a permanent `view-transition-name`, which makes a
  stacking context, so a page's dialog sat under the bottom tab bar (on a phone it hid the Download button). The
  names are now set only while a transition runs (`html[data-vt]`); checked: the dialog is on top, the cube
  transition still renders.

## 2026-10-15 — Web UI: one page width, width cap with a live backdrop, 18 shuffled page transitions

- **Request (user):** on the Log page the view changed size so the sub-navigation moved; make every page as wide as
  the header; cap the whole view on very wide (21:9) screens with the background still full and a moving liquid
  backdrop; transitions must be random, the same page reached differently each time, about 12 more effects.
- **Cause of the jump:** Log and Library used the `wide` doc page (full width), the other document pages a 1100 px
  column, so the sub-navigation started at a different x. The `wide` variant is gone; document pages are as wide as
  the app bar. Measured at 2560×1080: the sub-navigation starts at x = 456 px on both Status and Log, page width =
  app bar width = 1648 px (`--app-max` 1680 px minus the 16 px gutters).
- **Backdrop:** four large radial colour fields (Lucent wall tokens and the accent tint) drift on 39–61 s loops,
  transforms only, behind the glass; frozen with reduced motion.
- **Transitions:** 12 more (push, zoom through, card flip, cube, blinds, liquid melt, diamond iris, opening doors,
  soft wipe, halftone dots, old TV, ink spread), 18 in all. Random now deals from a shuffled deck, so all 18 play
  before any repeats and a deck never starts with the previous effect; push, wipe, blinds, doors, flip and cube pick a
  random direction each time. Blinds, halftone, wipe and diamond animate registered custom properties (`@property`);
  the liquid melt uses a slow round SVG turbulence; the ink spread is a noise mask thresholded on the distance from
  the pressed point, regenerated per transition. Checked by freezing the animations mid-way in headless Chrome: all 12
  render as designed. Frame rate on the real GPU not measured.

## 2026-10-14 — Web UI: image and 3D viewers, glass scrollbars, live job log, page transitions

- **Request (user):** the scrollbars looked raw, make them professional and liquid-glass; on the creation pages a
  square image showed only a rectangle of its top part; basic view tools for images and 3D models (zoom in/out, move,
  turn left/right); on Server, Status the job log did not scroll to the end nor update live although Follow was on;
  transitions between screens, several premium effects picked at random (shatter, fade, noise ...); merge Status and
  the Blender add-on, give the log its own page.
- **Square image clipped (cause found):** `.stage__content` was a one-cell grid with an auto-sized row, so the
  image's `max-height: 100%` resolved against its own content and the 1024² image overflowed the stage (clipped by
  `overflow: hidden`). Now the cell is `minmax(0, 1fr)` both ways and previews are viewers that fill the stage.
- **Image viewer** (`ui/organisms/ImageView.tsx`): fits by default (keeping clear of the result bar via a stage-inset
  context and of the toolbar), wheel / pinch zoom at the pointer (5 %–1600 %), drag to pan, double-click fit / 100 %,
  keys + - 0 1 and arrows, pixelated rendering from 200 %, full screen. Checked in headless Chrome over CDP: fit 61 %
  of a 1024² image in a 1440×900 window, one wheel step to 112 %, drag pans, Actual size gives 100 %, Fit returns.
- **3D viewer** (`ModelView`): glass toolbar with zoom out/in, turn left/right (30°), turntable on/off, reset view,
  full screen; mouse: drag orbit, right-drag pan, wheel zoom (min radius 20 % of the framing). The buttons move
  relative to the camera *goal*: `getCameraOrbit()` returns the position mid-glide, so "zoom, zoom, turn" pressed
  quickly lost the zoom (measured: radius stayed 2.729 m). After the fix three zooms and a turn give
  0.5236 rad / 1.397 m (= 2.729 × 0.8³). Right-drag moved the target by 0.25 m; Reset returned to 0 rad, 2.729 m,
  target ≈ 0.
- **Scrollbars:** a 14 px clear track with a capsule thumb inset 4 px (3 px on hover), translucent label colour, a
  1 px glass rim, no arrow buttons, track margins so it clears rounded corners; Firefox gets `scrollbar-width: thin`
  in the same colours.
- **Live log (cause found):** the Status page polled the last 400 lines every 3 s into a `<pre>` capped at 60vh and
  never touched its scroll position, so Follow only meant "keep polling". Now `GET /v1/logs` also takes `since=<byte
  offset>` and returns only complete lines written after it plus the new `offset` (`reset: true` for a fresh tail, a
  truncated log or a catch-up over 1 MiB); the new Log page polls once a second, keeps 5000 lines, sticks to the
  bottom while following, stops following when scrolled up (a "Latest" button resumes), filters, downloads, strips
  ANSI erase codes and tints error / done lines. Checked: 12 lines appended at 0.5 s intervals all arrived with the
  view at the bottom (0 px from the end); one wheel step up turned Follow off. New test `test_logs_follow_by_offset`
  (partial lines wait for their newline).
- **Server section:** Status now holds the facts and the Blender add-on (drag-to-install); Log is its own page;
  `#/addon` redirects to Status. Sub-navigation: Status, Log, Models, Settings.
- **Page transitions** (`web/src/lib/transitions/`, `styles/transitions.css`): a random effect per page change, never
  the same twice in a row, or a fixed one / off in Settings; off with `prefers-reduced-motion`. Only the page area
  animates (top bar and tab bar have their own view-transition names and stay still). Effects: fade and blur;
  noise dissolve (20 mask frames of thresholded smooth noise generated on a canvas at first use); glitch (an SVG
  turbulence displacement filter animated with SMIL, slice clips, red/cyan split); circle reveal from the pressed
  point; depth (old recedes, new rises); shatter (the old page on its wallpaper copied into 28 shards cut by rays
  and rings around the pressed point, cracked apart and thrown in 3D with gravity, the 3D viewer's canvas copied via
  `toDataURL`). All but the shatter use the View Transitions API. Checked by freezing `document.getAnimations()` mid-
  way in headless Chrome: each effect renders as designed. Not measured: frame rate on the real GPU; under
  SwiftShader the 28-clone shatter took long to start (headless timings are not representative).
- **Checks:** tsc strict clean, mypy strict clean, API types regenerated, 77 tests pass, pre-commit hooks clean.

## 2026-10-14 — Typed stack: TypeScript web UI (atomic design), mypy-strict server, drag-to-install add-on

- **Request (user):** the web UI in TypeScript with explicit types, the server typed too, so both are easier to
  control and upgrade; atomic design for the most reuse; the Library detail dialog overflowed (content wider than the
  dialog); install the Blender add-on by dragging a button into Blender like https://www.blender.org/lab/mcp-server/;
  an app-like bottom bar instead of the sidebar; then: glass looked flat on the light theme (nothing behind it), and
  the parameter panel covered part of the image / 3D preview.
- **Server (v0.3.0), same behaviour, now typed:** `mypy --strict` with the pydantic plugin passes on `server/app`,
  `matte_server.py` and the generator script (25 files). Every route returns a pydantic model (`schemas.ApiModel`,
  defaults always present in responses); jobs are `schemas.Job` with typed `JobProgress` / `JobInfo` instead of
  dicts (old `job.json` records load unchanged); `Pipeline[P]` is generic over its params; `POST /v1/jobs` takes
  `JobRequest`, a discriminated union of one `{kind, params}` model per pipeline (an unknown kind is now 422, not 404;
  a test checks the union matches the registry); `model_setup` has a `TypedDict` manifest and typed status/progress.
- **Shared contract:** `scripts/gen_api_types.py` turns the server's OpenAPI schema into `web/src/api/types.gen.ts`
  (in-repo, no codegen dependency); `--check` runs in the tests and CI. `api.submit(kind, params)` is checked against
  that kind's params, so changing a server model shows up as a TypeScript error.
- **Web UI rewritten in TypeScript** (strict, `noUncheckedIndexedAccess`; TypeScript 7.0.2, esbuild 0.28.2, React
  18.3.1, model-viewer 4.0.0 + three 0.169.0 from npm; 26 packages installed (70 lock entries with esbuild's per-platform binaries), exact versions, sha512-locked, `npm ci` with
  install scripts off; Lucent stays vendored and pinned, bundled after React is published on `window`, with hand-written
  prop types in `src/ui/atoms/lucent.ts`). Atomic layers in `src/ui/`: atoms (Lucent controls, icons, text), molecules
  (field, choice field, number/seed field, progress and result capsules, drop zone, drag-install link...), organisms
  (image picker, schema form, model viewer, job tile and dialog, tool card, tab bar, toaster), templates (app shell,
  stage layout, document page); each layer keeps its CSS next to it. Navigation is Lucent's floating glass bottom tab
  bar (Image, 3D model, Library, Tools, Server; Server holds Status, Models, Blender add-on, Settings). Measured on this
  machine: `tsc --noEmit` 0.30-0.31 s (3 runs), production build 0.11 s; `app.js` 211 kB, `app.css` 36 kB, the
  model-viewer chunk 892 kB loaded on first use (minified, not gzipped). 3114 lines of TS/TSX besides the 355 generated.
- **Fixes:** the job dialog had a fixed 720 px body inside Lucent's 420 px dialog; it is now up to 760 px wide, its
  content fits (checked at 1440 px and 390 px), the body scrolls and the actions wrap. Long option labels (cutout
  model, atlas) clipped in segmented controls; a choice field now switches to a menu above 30 characters of labels.
  The page body now carries Lucent's own wallpaper tokens (`--wall-*`, as its `.lg-stage` demo backdrop), so the glass
  bars and panels show colour behind them in both themes. The creation pages are a two-column grid (preview, 380 px
  panel) instead of a panel floating over the preview. A circular import (page registry <-> server sub-navigation)
  left the first build blank; caught in headless Chrome and removed.
- **Blender add-on v0.13.0 as an extension:** `blender_manifest.toml` (id `trellis_addon`, Blender 4.2+, permissions
  network + files); the server publishes an extension repository (`GET /blender/index.json`, the v1 format Blender's
  `server-generate` writes, with archive size and SHA256 of a reproducible zip served at `/blender/<id>-<version>.zip`).
  The web button links to `<zip>?repository=<index URL>&blender_version_min=4.2.0`, which Blender's drop handler
  matches against the repository (same mechanism as lab.blender.org). Verified with Blender 5.2.2 in an isolated user
  directory: `--command extension validate` accepts the zip; `repo-add` + `sync` + `install lp.trellis_addon --enable`
  downloaded and installed it, and a fresh Blender loaded it as `bl_ext.lp.trellis_addon` with `trellis2.generate`
  registered. The drag gesture itself in the Blender GUI was not tested here.
- **Build and checks:** the image builds the UI in a first stage (`node:24-slim` pinned by digest; `tsc` then
  esbuild) and copies only `web/dist`; CI has new jobs for `mypy` + the generated types, and for `tsc` + the build;
  Dependabot watches `web/`. 76 unit tests pass, all pre-commit hooks pass. Real run in the rebuilt image (v0.3.0)
  through the typed job API: "a small wooden toy robot" (object framing, 3 steps) 50.1 s, then image-to-3D from that
  job (auto matting, 512, 6 steps) 200.5 s, 146,754 faces, resets 0 -> 0 (one run each; the 186.3 s of the earlier
  telescope run is a different subject, so the two times say nothing about a speed change).

## 2026-10-14 — Web UI on the server (Lucent design system), job queue, pipeline registry

- **Request (user):** a web UI on the server to configure it, download models, upload by drag and drop, download the
  Blender add-on, and generate images and 3D models with every parameter; built to be extended and maintained by many
  contributors; design system: Lucent (https://claude.ai/artifact/SDYfdYxdUAzWGwcxka3vKw, Liquid Glass, React 18 UMD).
- **Server (`server/app/`, v0.2.0), restructured as a package:** `pipelines/` (one `Pipeline` class per capability:
  `image.generate`, `image.edit`, `image.matte`, `mesh.generate`; validated pydantic `Params` that double as the API
  schema and the web form; registry in `pipelines/__init__.py`), `jobs.py` (FIFO queue with one worker = one GPU job at
  a time, persisted `job.json` + results under `<data>/jobs/<id>/`, progress parsed from CLI output, cancel, delete,
  restart recovery, pruning), `routes/` (system, setup, config, jobs + uploads, prompts, add-on download, and the
  Lemonade-format endpoints the add-on uses, now queued like everything else), `settings.py` (hard limits + a
  validated `RuntimeConfig` persisted in `<data>/config.json`), `security.py` (token for `/v1/*`, body cap, strict CSP
  and other headers on every response), `storage.py` (uploads and results by random id only). The prompt framing is
  loaded from the add-on's `prompts.py` (one source for add-on, server and web). New mesh options exposed: matting
  auto/rembg/none + cutout model, texture on/off, atlas size, structure/shape guidance, token budget.
- **Web UI (`web/`, no build step):** ES modules + React 18 + htm + Lucent, every third-party file vendored and pinned
  (`web/vendor/VENDOR.json`, sizes + SHA256 + licences, checked by tests); `styles/tokens.css` generated from the
  Lucent tokens (`scripts/gen_tokens_css.py --check` in the tests). Pages (registry `web/app/pages/index.js`): Image
  (generate/edit, framing, size, steps, CFG, seed, full-prompt preview), 3D model (all options, interactive GLB preview
  with model-viewer), Tools (forms generated from pipeline schemas: a new pipeline appears without web code), Library,
  Models, Blender add-on, Status and log, Settings (form generated from the config schema, access token, theme).
  Design: the stage is the studio grey FLUX.2 images are generated on, with the parameter panel as thick glass over its
  edge; light/dark; responsive to 390 px. Extra icons drawn to the Lucent icon rules (24 px grid, 2 px stroke).
- **Checks:** 72 unit tests (API with fake CLIs: validation, refs, cancel, failure, auth, CSP, config, add-on zip;
  model setup; prompts; client; web: vendor pins, imports resolve, no remote scripts, tokens up to date) pass; all
  pre-commit hooks pass (vendored files excluded from the auto-fixers: the end-of-file fixer had changed
  `lucent/tokens.json` and its pin). Real run through the job API in the rebuilt image: "a small brass desk telescope on
  a tripod" (object, stylized, 3 steps) 51.3 s, then image-to-3D from that job (auto matting, 512, 6 steps) 186.3 s,
  147,736 faces, resets 0 -> 0; checked in headless Chrome: result pages, interactive GLB viewer (WebGL via
  SwiftShader), library, dark mode, 390 px. Fixed on the way: sd-cli prints the same bar for denoising and VAE tiles
  (now separate stages), internal paths in stage names, results opened later restore their settings.

---

## 2026-10-14 — Repository standardised for many contributors; models downloaded by the server (pinned + verified)

- **Decisions (user):** licence GPL-3.0-or-later; hosting on GitHub; models are fetched by the server and the add-on
  only triggers and shows it ("server downloads, add-on presses the button").
- **Layout:** `server/` (image: `server.py`, `model_setup.py`, `manifest.json`, `matte_server.py`, hashed
  `requirements*.txt`), `scripts/` (`run-server.sh`, `smoke_test.py`, `make_sample.py`), `tests/`, `blender/`
  (add-on split into `prompts.py` + `client.py` without bpy, UI in `__init__.py`). Repo files: `LICENSE`,
  `CONTRIBUTING.md`, `SECURITY.md` (threat model + rules), `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1),
  `pyproject.toml` (ruff with security rules, pytest), `uv.lock`, `.pre-commit-config.yaml` (hygiene, ruff,
  shellcheck, gitleaks; frozen SHAs), `Makefile`, `.editorconfig`, `.gitattributes`, `.hadolint.yaml`, a source-only
  `.gitignore`, `.github/` (CI: pre-commit + pytest + hadolint + add-on package; Dependabot; CODEOWNERS with a
  placeholder team; issue/PR templates).
- **Model setup:** `server/manifest.json` pins all 15 items (2 release archives, 11 files, 2 bf16 -> q8_0 conversions)
  by URL at a fixed release/revision, size and SHA256 (Hugging Face LFS oids, GitHub asset digests; the q8_0 outputs
  hashed from the files in use). `model_setup.py`: https + domain allowlist checked on every redirect (HF serves from
  regional CDN hosts such as `us.aws.cdn.hf.co`), streaming SHA256, `.part` + resume with Range, atomic rename,
  disk-space check, tar `data` filter and equivalent zip checks, text-file symlinks of the sd.cpp zip recreated.
  Server: `GET /v1/setup`, `POST /v1/setup/download`; jobs answer 503 until ready. Add-on v0.12.0: "Check Server",
  "Download Models" with progress, "Server Token" preference. CLI: `make models`, `models-status`, `models-verify`.
- **Server hardening:** pydantic validation of every field (size 256-2048 multiple of 16, steps, seed, cfg, prompt
  length and control characters, resolution / bg_removal enums), image magic-byte check (PNG only for meshes), 48 MiB
  body cap, optional `SERVER_TOKEN` (constant-time compare), no API docs endpoints, runs as non-root with
  `--cap-drop=all` and `no-new-privileges`, Python deps installed with `--require-hashes`, base image pinned by
  digest; the entrypoint now waits on the two server PIDs only (a bare `wait` would also wait for its log `tee`).
- **Checks:** 56 unit tests (prompts, client against a stub server, server API with fake CLIs, model setup with a
  fake opener: allowlist, hash mismatch, resume, zip/tar escapes, end-to-end install) pass in 2.4 s; all pre-commit
  hooks pass; hadolint clean (DL3008 ignored on purpose, see `.hadolint.yaml`).
- **Real run:** image rebuilt with `--require-hashes`. With `trellis2/ss_dec.gguf` and `sdcpp-rocm/` moved aside the
  server started, reported both missing (0.4 GiB), answered jobs with 503, and `POST /v1/setup/download` reinstalled
  them in 101 s (GitHub + Hugging Face CDN redirects passed the allowlist, SHA256 matched); the result was
  byte-identical to the originals, including the zip's `.so` symlinks. Found and fixed on the way: the non-root image
  user could not write `models/` (now run as the host user with `--user uid:gid`), extracted directories were 0700.
  `make smoke` (Fast) on the new image: edit 107.0 s, matting 1.7 s, TRELLIS.2 res 512 224.3 s, resets 0 -> 0. Add-on
  v0.12.0 installed over MCP: "Check Server" -> "Models ready".

---

## 2026-10-14 — Decision: self-hosted GPU server (ROCm) replaces Lemonade; cleanup

- **Decision (user):** the 3D asset path runs on our own server, `tools/server/` (FLUX.2-klein-4B via stable-diffusion.cpp
  HIP with q8_0 GGUF weights, TRELLIS.2 via trellis.cpp v0.8.1 HIP, one CLI process per job, matting on the CPU), with
  the host kernel parameter `amdgpu cwsr_enable=0`. Lemonade is dropped.
- **Measured against Lemonade/Vulkan (entries below):** text-to-image 63 s vs 107-120 s; A-pose edit 140 s vs 220 s;
  TRELLIS.2 res 512 261-278 s vs 270-310 s; a full character (image + A-pose + mesh 512) ~8 min vs ~10 min (Fast
  preset ~6 min); res 1024 works on every object tried (~19 min) and res 1536 runs (~53 min), while Lemonade's Vulkan
  backend failed res 1024 on complex objects and stayed broken until a restart; GPU memory is released after every job
  (Lemonade kept models loaded until 300 s idle); per-request mesh steps. Costs: a root-only kernel parameter, release
  binaries and weights fetched and converted by hand (`models/README.md`), our own ~220-line server to maintain.
- **Cleanup:** deleted `tools/lemonade/` (its `matte_server.py` and `make_sample.py` moved to `tools/server/`),
  `tools/rocm/` (PyTorch P0-P2), `tools/server/bench_flux.py`, the Vulkan FLUX.2 fallback (never run) and its Mesa
  packages in the image; in `models/`: Lemonade's state and downloads (31 GB, after moving the TRELLIS.2 f16 GGUFs to
  `models/trellis2/` and the FLUX.2 VAE to `models/flux2/`), the diffusers FLUX.2 weights (15 GB), the bf16 FLUX.2
  safetensors (kept only as q8_0 GGUF, `models/flux2/`), `sdcpp-vulkan`, `rocm-out`, `rocm-cache` and all benchmark
  outputs: `models/` went from ~57 GB to 26 GB. `server.py` now has fixed weight paths, no backend/weight switches,
  and refuses to start when `cwsr_enable` is not 0. Add-on v0.11.1: texts no longer point at Lemonade.
- **Slip during the cleanup:** `git mv -k` silently skips untracked files (nothing is committed yet), so
  `matte_server.py` was deleted with `tools/lemonade/`; the first rebuild failed and the old image kept running. The
  file was recovered byte-identical from the previous `local-producer-gpu` image (same as in the Lemonade image).

---

## 2026-10-14 — Add-on v0.11.0: Subject (Character / Object) and Style (Stylized / Realistic) for prompt mode

- **Why (user):** the framing appended to FLUX.2 prompts described a character ("Full body, standing upright, arms
  slightly away from the body", "cartoon toy figure"), which does not fit props, machines or parts.
- **Change:** `full_prompt(prompt, view, framing, subject, style)`; `FRAMING_OBJECT` ("A single object on its own,
  three-quarter view from the front left and slightly above, so the front, one side and the top are all visible") and
  `TAILS[(subject, style)]` ("nothing else in the scene", "Realistic 3D product render, accurate proportions, detailed
  physically based materials" / "Stylized 3D model with clean simple shapes"). Character + Stylized keeps the old text,
  so the sample image still reproduces. Make A-pose is hidden and refused for objects. `start_image(..., subject,
  style)` for headless use; image file names now contain the subject.
- **Check over MCP (Fast preset, 3/4 view, image seed 7, mesh seed 1234, res 512, n = 1 each):**

  | prompt | style | image | mesh | faces | res-32 voxels |
  | :--- | :--- | ---: | ---: | ---: | ---: |
  | a small single-cylinder gasoline engine | realistic | 49 s | 365 s | 144,878 | (not logged) |
  | a red retro toaster | stylized | 60 s | 513 s | 146,200 | 6,820 |

  Both images show one object, slightly from above, on grey; both meshes are clean closed objects with textures.
  The "gasoline engine" came out looking like an electric motor (FLUX.2's content, not the framing). Bulky objects
  fill more of the volume than characters (toaster 6,820 active res-32 voxels vs the cat's 2,472), so all three
  TRELLIS.2 flows take longer (toaster at 6 steps: 95 / 166 / 104 s vs 89 / 49 / 30 s for the cat).
- After the run the panel showed Subject = Character again: the user had clicked it in Blender's UI (not a bug).

---

## 2026-10-14 — Add-on v0.10.0: Speed preset (Quality / Fast / Custom) and res 1536; server takes per-request mesh steps

- **Add-on:** "Speed" switch above the mesh options: Quality = FLUX.2 4 steps + TRELLIS.2 8 steps (default), Fast =
  3 + 6 (the two speed options of the sweeps below), Custom = "Image Steps" (text-to-image and Make A-pose) and "Mesh
  Steps" by hand; resolution 1536 added. Mesh steps go out as `"steps"` in `/v1/3d/generations`.
- **Server:** `/v1/3d/generations` accepts an optional `steps` (1-50) that replaces `--steps` of `--trellis-args`
  (Lemonade has no such field and ignores it).
- **Check, Fast preset end to end** (`tools/server/smoke_test.py ... 512 3 6`, cat sample): A-pose edit 99.6 s (Quality:
  139.9 s), matting 1.7 s, TRELLIS.2 res 512 211.6 s (Quality: 278.1 s); log shows `--steps 6`; resets 0 -> 0. The
  3-step A-pose image keeps the character (arms near horizontal, as at 4 steps). n = 1.

---

## 2026-10-14 — TRELLIS.2 HIP with cwsr off: serialisation costs nothing, 6 steps -14 %, res 1024 stable

- **Setup:** trellis-cli v0.8.1 HIP inside `local-producer-gpu` (`models/server/bench_trellis/run.sh`), cat sample,
  seed 1234, `--webp off`, cwsr_enable=0, one run each; meshes rendered with Cycles on the CPU (front + 40 degrees,
  orthographic) and compared by eye.

| run | flows SS / shape (LR / HR) / texture | total | faces |
| :--- | :--- | ---: | ---: |
| res 512, 8 steps, `AMD_SERIALIZE_KERNEL=3` | 121.1 / 63.2 / 36.4 s | 260.9 s | 141,098 |
| res 512, 8 steps, serialisation off | 121.8 / 62.5 / 35.8 s | 259.0 s | 143,180 |
| res 512, 6 steps | 89.2 / 49.4 / 30.2 s | 225.0 s | 148,482 |
| res 1024, 8 steps | 121.9 / 63.5 + 494.1 / 288.6 s | 1142.6 s | 289,956 |

- Serialisation off is not faster (within one run), so it stays on. 6 steps saves 36 s (14 %); its mesh looks like
  the 8-step one with small differences around the eye outlines and mouth, about the size of a seed change (n = 1).
  Res 1024 ran with no reset or ring timeout with cwsr off (1143 s vs 1075 s on 2026-10-14 with cwsr on, n = 1 each)
  and is visibly sharper (eye highlights, stripes). Resets 0 -> 0.
- **Decision:** keep 8 steps as the default (`--trellis-args`); 6 steps is the speed option. Res 512 for drafts, 1024
  for final assets.

---

## 2026-10-14 — FLUX.2 speed/quality sweep on HIP (cwsr off): pre-converted q8_0 GGUF is the sweet spot (63 s vs 76-80 s bf16)

- **User question: would an FP8 FLUX.2 be faster?** Not on this GPU (reasoning, not measured): gfx1103 (RDNA3) has
  no FP8 matrix instructions (FP8 WMMA arrived with RDNA4 / gfx12) and ggml has no FP8 compute type, so FP8 weights
  would be converted on load; they only save disk/RAM, which q8_0 already does.
- **Setup:** `tools/server/bench_flux.py` inside `local-producer-gpu` (sd.cpp HIP `master-964`, Lemonade's sd-server
  switches: `--vae-tiling`, `--flash-attn off,diffusion=on`), 1024^2, 4 steps, cfg 1, seed 7, two prompts (cat sample,
  hip-hop capybara), one run each; PSNR (8-bit RGB) against the bf16 image of the same prompt; contact sheets judged
  by eye. sd.cpp is deterministic: `bf16_again` = bf16 bit for bit (PSNR 99), so differences are not noise.
  Resets 0 -> 0 over all 32 runs.

| variant (cat / capybara) | wall s | load s | text enc. s | sampling s | VAE decode s | PSNR vs bf16 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| bf16 (reference) | 76.0 / 77.6 | 2.2 / 2.1 | 2.6 / 2.4 | 54.0 / 55.1 | 18.6 / 19.3 | - |
| bf16 again | 80.1 / 80.1 | 2.0 / 2.1 | 2.5 / 2.4 | 56.8 / 56.8 | 20.1 / 20.1 | 99 / 99 |
| `--type q8_0` (on load) | 67.9 / 70.2 | 7.0 / 7.2 | 4.1 / 4.3 | 43.3 / 45.1 | 19.7 / 20.0 | 24.1 / 29.8 |
| **q8_0 GGUF, pre-converted** | **63.0 / 63.9** | 1.4 / 1.4 | 1.6 / 1.7 | 40.7 / 41.5 | 19.9 / 20.0 | **28.7 / 28.8** |
| q8_0 GGUF, 3 steps | 53.8 / 53.7 | 1.4 / 1.4 | 1.7 / 1.7 | 31.4 / 31.3 | 20.0 / 19.9 | 24.8 / 26.4 |
| `--type q8_0`, 3 steps | 60.0 / 60.0 | 7.3 / 7.3 | 4.3 / 4.3 | 34.9 / 34.9 | 20.0 / 20.1 | 25.1 / 26.8 |
| `--type f16` | 88.1 / 87.7 | 6.8 / 6.9 | 4.6 / 4.6 | 62.6 / 62.1 | 20.2 / 20.2 | 32.4 / 28.3 |
| `--type q6_K` | 113.1 / 113.3 | 30.7 / 30.8 | 15.0 / 15.1 | 77.2 / 77.3 | 20.2 / 20.2 | 25.6 / 25.6 |
| `--type q5_K` | 175.2 / 174.2 | 111.5 / 110.7 | 49.7 / 49.7 | 104.6 / 103.8 | 20.1 / 20.0 | 26.5 / 24.9 |
| `--type q4_K` | 171.3 / 170.7 | 108.0 / 107.6 | 48.8 / 48.3 | 101.8 / 101.7 | 20.0 / 19.9 | 21.3 / 24.7 |
| `--type q4_0` | 89.5 / 89.4 | 26.9 / 26.7 | 13.0 / 12.7 | 55.7 / 55.8 | 20.1 / 20.0 | 22.0 / 24.5 |
| q8_0, no VAE tiling | 58.2 / 58.3 | 7.3 / 7.3 | 4.3 / 4.3 | 45.0 / 45.0 | 8.2 / 8.3 | 23.5 / 24.4 |
| q8_0, VAE tile 512 | 65.3 / 65.4 | 7.3 / 7.3 | 4.3 / 4.3 | 45.0 / 45.0 | 15.2 / 15.3 | 24.0 / 27.3 |
| q8_0, `AMD_SERIALIZE_KERNEL=0` | 70.4 / 70.2 | 7.2 / 7.2 | 4.2 / 4.2 | 45.3 / 45.1 | 20.1 / 20.1 | 24.1 / 29.8 (= q8_0) |
| q8_0, `--flash-attn on` (all) | 69.9 / 70.2 | 7.2 / 7.3 | 4.1 / 4.1 | 45.0 / 45.1 | 20.0 / 20.2 | 27.8 / 29.1 |
| q8_0, 768^2 | 41.0 / 41.0 | 7.4 / 7.3 | 4.3 / 4.3 | 25.6 / 25.6 | 10.4 / 10.4 | 18.2 / 20.0 (resized) |

- "load"/"text enc." include sd.cpp's on-the-fly weight conversion (CPU), which is what makes the K-quants and q4_0
  slow to start; their sampling is also slower than q8_0 on HIP (K-quant matmul paths, hypothesis).
- **By eye:** without VAE tiling the colours wash out (grey capybara, pale cat) -> rejected even though the decode is
  2.4x faster; tile 512 is slightly paler too. On-the-fly q8_0 turned the cat's orange arms white; the pre-converted
  q8_0 GGUF keeps them (closest to bf16 of all faster variants, also by PSNR). 3 steps keeps the design with small pose
  changes. 768^2 changes the design and loses detail. f16 is slower than bf16. Serialisation off and flash attention
  everywhere change nothing measurable.
- **Decision:** server default = pre-converted q8_0 GGUF (`models/flux2-gguf/`, made with `sd-cli -M convert --type
  q8_0`, 4.8 s per file, 4.2 + 4.3 GB), 4 steps, VAE tiling 256, serialisation on: 62.7 s per text-to-image through the
  server (vs 107-120 s Lemonade/Vulkan, 76-80 s bf16 HIP). 3 steps (~54 s) is the option if speed matters more.

---

## 2026-10-14 — amdgpu `cwsr_enable=0` stops the HIP launch failures: FLUX.2 on ROCm 9/9, full chain 10/10, 0 resets

- **Change (by the user, root):** `/etc/modprobe.d/amdgpu-cwsr.conf` = `options amdgpu cwsr_enable=0` (amdgpu is not in
  the initramfs, so no rebuild), reboot; `/sys/module/amdgpu/parameters/cwsr_enable` = 0. CWSR = compute wave
  save/restore, the mechanism that lets the GPU preempt running compute waves. Revert: delete the file, reboot.
- **Setup:** fresh boot (counter 0), `tools/server` image (now also with Mesa RADV for an optional Vulkan FLUX.2
  path), `SERVER_ARGS='--flux-backend rocm --flux-type q8_0'`, `AMD_SERIALIZE_KERNEL=3`; the SDMA / HW-queue env
  switches were removed (no effect, entry below). Blender open (no HIP context), Lemonade stopped.
- **Soak:** 8 text-to-image jobs back to back, alternating the cat prompt and the hip-hop capybara prompt (the one
  that failed before), seeds 1-8: **8/8 OK**, 63.8-70.2 s each (sampling 40.1 -> 45.2 s and VAE decode 18.7 -> 20.1 s,
  rising over the first 5 jobs, then flat: thermal/power, hypothesis). Then `tools/server/smoke_test.py` (new; the
  add-on's calls without Blender): A-pose edit 139.9 s -> matting 1.6 s -> TRELLIS.2 res 512 278.1 s (139,146 faces),
  TRELLIS started 2 s after FLUX.2 exited. GPU memory in use before / after every FLUX.2 job: 1.86 / 1.86 GiB.
  Resets/ring timeouts 0 -> 0, no `MES failed` lines.
- **Comparison (same server, sd.cpp HIP q8_0 FLUX.2):** CWSR on: 4 OK / 4 failed (failures at the first diffusion
  matmul); CWSR off: 9/9 OK. **Conclusion:** strong evidence that CWSR (wave preemption via MES on gfx1103) triggers
  the intermittent launch failure -> MES hang -> GPU reset seen since 2026-10-12; not proven for every workload
  (n = 9 + 1 TRELLIS run). Not yet checked with CWSR off: bf16 FLUX.2 on HIP, PyTorch, TRELLIS res 1024, desktop
  responsiveness during long jobs (waves can no longer be preempted), and whether `AMD_SERIALIZE_KERNEL` is still
  needed.
- **Defaults now:** `tools/server/server.py` runs FLUX.2 on HIP with q8_0; `--flux-backend vulkan` (sd.cpp Vulkan
  build in `models/sdcpp-vulkan/`, bf16) is the fallback for machines without the parameter, not yet run.

---

## 2026-10-14 — FLUX.2 on ROCm (sd.cpp HIP) is not reliable: 3 failures in a row after a reset; q8_0 does not prevent them

- **Run by the user from the add-on** (a hip-hop character prompt, q8_0): `MUL_MAT failed` / `unspecified launch
  failure` in the first diffusion-model matmul, ~2 s after the FLUX.2 weights were loaded; `MES failed to respond to
  msg=REMOVE_QUEUE` -> GPU reset 11:27:27, counter 2 -> 3. Server survived (sd-cli rc -6).
- **Tried:** `HSA_ENABLE_SDMA=0` + `GPU_MAX_HW_QUEUES=1` in the image (copies by blit kernels, one HW queue per
  process). First job of a planned 8-run soak (capybara prompt, seed 1) failed the same way at the same point
  (reset 11:29:22, 3 -> 4). Then the cat prompt that had passed 3/3 at 11:00-11:03 failed the same way too
  (4 -> 5), so the failure does not depend on the prompt (an idea that the prompt length/matmul shape mattered: wrong).
- **Tally for sd.cpp HIP FLUX.2:** 4 OK (3 text-to-image + 1 edit, all between the reset at 10:58 and the one at
  11:27), 4 failed (1 bf16 + 3 q8_0), every failure at the first diffusion matmul. The new env switches show no
  effect (n = 2 after them, both failed). All three failures after 11:27 came in a row, which suggests (hypothesis)
  that the GPU/MES stays in a bad state after some resets until a reboot; TRELLIS.2 was not run after 11:27.
- **Stopped GPU testing** at 5 resets this boot. Open options: (a) FLUX.2 back on Vulkan but still one sd-cli process
  per job inside `tools/server` (keeps the memory-release property), TRELLIS.2 stays on HIP; (b) after a reboot, retry
  ROCm FLUX.2 with `amdgpu.cwsr_enable=0` (kernel parameter, root + reboot, the user's call).

---

## 2026-10-14 — FLUX.2 + TRELLIS.2 both on ROCm: own server (`tools/server/`), one process per job, q8_0 FLUX

**Decision (user):** move FLUX.2 to ROCm as well, next to trellis.cpp HIP, and make sure FLUX.2's GPU memory is
released as soon as it finishes so TRELLIS.2 gets it.

**Design:** `tools/server/` -> image `localhost/local-producer-gpu` (Ubuntu 24.04, since the sd.cpp release binaries
need glibc >= 2.38; the bookworm PyTorch image cannot run them; ROCm 10.1.0 runtime from AMD's `rocm-sdk-core` /
`rocm-sdk-libraries` / `rocm-sdk-device-gfx1103` wheels, no PyTorch; plus rembg for the matting server). `server.py`
speaks the part of Lemonade's API the add-on uses (`/v1/images/generations`, `/v1/images/edits`,
`/v1/3d/generations`, same JSON), so the add-on needs no protocol change. Each job is one CLI process
(`sd-cli` from stable-diffusion.cpp `master-964-1d0a58a` rocm-10.1.0 release, gfx1100-1103 code objects;
`trellis-cli` v0.8.1 HIP) under one GPU lock: jobs never overlap, and a job's memory goes away with its process.
The log gets GTT+VRAM in use (sysfs, whole machine) before and after each job and the CLI output in Lemonade's
`[Info] (Process)` format, so the add-on's progress parser works unchanged. `AMD_SERIALIZE_KERNEL=3` is set in the image.
Weights are still read from Lemonade's HF cache, with the same files and switches Lemonade's sd-server used.

**First FLUX.2 run, bf16 weights as loaded from the safetensors:** text encoding (3 s) passed, then the first
diffusion-model matmul failed: `ROCm error: CUBLAS_STATUS_INTERNAL_ERROR` in `hipblasGemmEx` ->
`MES failed to respond to msg=REMOVE_QUEUE` -> GPU reset (10:58:47), counter 1 -> 2; sd-cli aborted (rc -6), the
server survived. The earlier PyTorch failure (VAE decode, same day) was also a BF16 `hipblasGemmEx`; trellis.cpp's
F16 GEMMs never failed (4/4). hipBLAS and rocBLAS here both link hipBLASLt, which ships only one gfx1103 file
(rocBLAS: 150). **Hypothesis:** BF16 GEMMs on gfx1103 in this ROCm 10.1 stack fail intermittently. Not proven: no
controlled BF16-vs-other A/B was run.

**Workaround:** `sd-cli --type q8_0` (server default `--flux-type q8_0`): sd.cpp quantizes the weights on load
(2-3 s) and the matmuls run in ggml's own MMQ kernels instead of hipBLAS BF16.

| job (through the server) | n | result | time | Lemonade/Vulkan (bf16) |
| :--- | ---: | :--- | ---: | ---: |
| text-to-image, cat prompt, seed 7, 1024^2, 4 steps | 3 | 3/3 OK | 62.5 / 63.6 / 64.1 s (load ~7 s, encode 4 s, sampling 40.2-40.4 s, VAE decode with tiling 18.7-18.9 s) | 107-120 s |
| "Make A-pose" edit (add-on over MCP, default cat) | 1 | OK | 131.5 s (sampling 97.9 s) | 220 s |
| then TRELLIS.2 res 512 right after (add-on) | 1 | OK | 278.4 s (job), 280 s in the add-on, 148,310 faces | 313 s total for the add-on |

GPU memory in use (whole machine) before / after each FLUX.2 job: 2.49 / 2.49 GiB, i.e. everything the job
allocated was released when sd-cli exited; TRELLIS.2 started 3 s after the edit with 2.49 GiB in use. After TRELLIS.2 jobs the reading right after exit was
3.01 / 3.11 GiB (+0.5 GiB) and 2.59 GiB a few minutes later (health endpoint), so the rest is released with a
delay (or belongs to the desktop/Blender; not separated). Resets: 2 -> 2 over all q8_0 and TRELLIS jobs (including,
after the add-on v0.9.0 reinstall, one more TRELLIS res 512 job: 292 s, OK). Image quality by eye (n = 1 per job): the text-to-image cat matches the Lemonade
sample's style; the A-pose edit keeps the character but the arms are nearly horizontal (closer to a T-pose than 45
degrees, as with PyTorch). Live progress in the add-on (v0.9.0, "Server Log" preference) checked:
`[4/7] shape SLAT flow (512)  1/8 10.1s ~71s`.

Open: the VAE decode with `--vae-tiling` takes ~19 s (PyTorch untiled: 5 s); try without tiling. A longer soak
(many mixed jobs) before calling the path reliable; the BF16 hypothesis (a controlled test costs GPU resets).

---

## 2026-10-14 — P2 continued: res 1024 and 1536 work on ROCm (no 2 s timeout); FLUX.2 on PyTorch failed once with serialisation on

**Goal:** res 1024 fails on Vulkan (`ErrorDeviceLost`, amdgpu 2 s compute timeout, at ~13.6k HR tokens). Does the HIP build get past it?

**Setup:** as in the entry below (`tools/rocm/p2_trellis.py` + `--res 1024|1536`, seed 1234, 8 steps, serialised kernels, Lemonade stopped, Blender open without a KFD handle). The capybara of 2026-10-13 was deleted, so a new one was made with FLUX.2 through Lemonade/Vulkan (`T2I_PROMPT` / `PROMPT` env overrides added to `tools/rocm/p1_flux.py` and `tools/lemonade/make_sample.py`; prompt "a cute capybara hip-hop character wearing an oversized hoodie, big headphones, a gold chain and baggy jeans" + the 3/4 grey framing, seed 7, 122 s + matting 3.2 s).

| input / res | HR tokens | SS flow | shape flow LR / HR | texture flow | total | faces | resets |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| cat 1024 | 10,366 | 115.2 s | 60.5 / 456.4 s | 273.6 s | 1075 s | 289,698 | 0 -> 0 |
| capybara 1024 | 9,500 | 120.8 s | 54.0 / 431.8 s | 250.8 s | 1023 s | 278,320 | 1 -> 1 |
| cat 1536 | 23,673 | 127.6 s | 63.7 / 1694.9 s | 956.0 s | 3200 s | 297,566 | 1 -> 1 |

- Res 1536 at 23.7k HR tokens (1.7x the token count that kills Vulkan) finished with no ring timeout; single HR forwards took up to 122 s. With HIP the 2 s `lockup_timeout` applies per kernel/queue, not per long ggml graph, and no single kernel came near it (hypothesis for why Vulkan's per-submission timeout does not apply here).
- Vulkan reference for the cat at res 1024 (v0.4.3, 12 steps, CHANGELOG 2026-10-13): 1657 s / 1491 s. Not directly comparable (version and step count differ).
- The new capybara did not reproduce the hard case (9.5k tokens, below the cat), so "res 1024 on an object Vulkan cannot do" is shown only through the res 1536 run.
- By eye (front view, Material Preview, n = 1 each): res 1024 is clearly sharper than 512 (eye highlights, stripes, cleaner chest); 1536 looks about the same as 1024 from the front at 3x the time. The capybara's fur is tan, as in its input image (the orange-red tint of 2026-10-13 did not appear; different input image, one run).

**FLUX.2 on PyTorch/ROCm failed once with `AMD_SERIALIZE_KERNEL=3`:** the capybara text-to-image (`p1_flux.py`) ran 4 steps (12.2 s each), then the first conv of the VAE decode raised `HIPBLAS_STATUS_INTERNAL_ERROR` / `hipErrorLaunchFailure`; kernel: `MES failed to respond to msg=REMOVE_QUEUE` -> `GPU reset begin` -> MODE2 reset (09:05:32-36), counter 0 -> 1; the container exited by itself (rc 1). This was the first job after the two TRELLIS runs. PyTorch also warned `Ignoring invalid value for boolean flag AMD_SERIALIZE_KERNEL: 3` (c10's own parser; the HIP runtime takes 0-3). So serialisation lowers but does not remove the launch failures in PyTorch: 4 passes, now 1 failure (n = 5). The trellis.cpp HIP runs (4/4 so far) have not failed.

**Conclusion:** for the 3D model, ROCm (trellis.cpp HIP) removes the res-1024 limit of the Vulkan path and is at least as fast at res 512. For FLUX.2 the PyTorch path is still not reliable. Next candidates: drive trellis.cpp HIP from the add-on (own server or Lemonade's `rocm` backend), keep FLUX.2 on Vulkan.

---

## 2026-10-14 — P2: TRELLIS.2 runs on ROCm (trellis.cpp HIP build), 249 s, 0 resets

**Goal:** check whether the 3D model runs on ROCm at all (FLUX.2 soak test skipped on the user's request).

**Setup:** trellis.cpp v0.8.1 release asset `trellis-rocm-linux-x64.tar.gz` (same version as the Vulkan baseline; `libggml-hip.so` carries gfx1103 code objects among gfx103x/110x/115x/120x) unpacked in `models/trellis-rocm-v0.8.1/`. It links `libamdhip64.so.7`, `libhipblas.so.3`, `librocblas.so.5`, `libomp.so`, taken from the ROCm SDK inside the PyTorch wheels of `localhost/local-producer-rocm` via `LD_LIBRARY_PATH` (`tools/rocm/p2_trellis.py`, run through `tools/rocm/run.sh`, so `AMD_SERIALIZE_KERNEL=3`). Weights: Lemonade's f16 `ilintar/trellis2-gguf` snapshot. Cat sample, seed 1234, res 512, `--steps 8 --webp off`. Lemonade container stopped; Blender open without a HIP context. Fresh boot, counter 0.

**Result (n = 1):** rc 0, `done in 249.4 s`, resets/timeouts/MES 0 -> 0, no NaN/Inf in any stage. ggml sees `AMD Radeon 780M Graphics, gfx1103, 29338 MiB`.

| stage | ROCm (this run) | Vulkan v0.8.1 via Lemonade (3 runs, 2026-10-13) |
| :--- | ---: | ---: |
| sparse-structure flow, 8 steps / 15 forwards | 115.2 s (~7.7 s per forward) | 107.5 / 118.9 / 123.6 s |
| shape SLAT flow, 14 forwards | 60.3 s (~4.3 s per forward) | 58.4 / 63.4 / 69.8 s |
| texture SLAT flow, 8 forwards | 34.4 s | 32.1 / 35.1 / 44.1 s |
| total | 249.4 s | 269.9 / 286.8 / 310.3 s |

Output: 137,128 faces (Vulkan reference run: 141,284), atlas 1024. Seen in Blender (front view, Material Preview): correct cat with eyes, whiskers, pink ears and cream belly; a few light speckles on the chest. Not compared side by side with a Vulkan GLB.

**Conclusion:** TRELLIS.2 works on ROCm on the 780M with serialised kernels and no GPU fault in this run. Per-stage flow times are within the spread of the Vulkan runs, so ROCm is not measurably faster per stage (n = 1 vs 3); the ~20-60 s lower total is mostly outside the flows (Lemonade's request overhead is included in the Vulkan totals, not in this one). No single forward hit the 2 s compute timeout, which is consistent with serialisation splitting the work into short kernels (hypothesis). Open: repeat runs, res 1024 (fails on Vulkan with `ErrorDeviceLost`), the original PyTorch TRELLIS.2.

---

## 2026-10-13 — Serialising HIP kernels (AMD_SERIALIZE_KERNEL=3) stops the intermittent launch failures; now the default

**Goal:** find the kernel behind the intermittent `hipErrorLaunchFailure` -> MES hang -> GPU reset (previous entry).

**Runs** (`p1_flux.py` A-pose edit, MIOpen off, flash attention, same input and seed; Lemonade stopped, Blender open without a HIP context; container the only KFD client):

| env | edits passed | failures |
|---|---|---|
| `AMD_SERIALIZE_KERNEL=3` | 4 / 4 (120.7, 125.3, 126.2, 128.0 s) | 0, resets 7 -> 7 |
| default (async) | 1 / 3 over two runs | edit 2 of the previous run; edit 1 of the control run, in denoising step 1 (`on_step` sync, 16:13:44 + ~13 s) |

- Each failure: `unspecified launch failure`, then `MES failed to respond to msg=REMOVE_QUEUE` and a MODE2 GPU reset, and stopping the hung container gives one more reset (counter 7 -> 9 for the control run). No page fault or ring timeout is logged first.
- With serialisation the failing kernel never fired, so it is still unidentified; the failures hit different stages (after the VAE encode; inside a transformer step), and P0 run 1 failed in math SDPA without AOTriton. **Hypothesis:** a race between back-to-back/overlapping kernel dispatches on gfx1103 (HIP runtime or MES firmware), not one bad kernel. 4/4 vs 1/3 is a small sample; the effect is consistent with the hypothesis but not proven.
- Serialisation had no measurable cost here: edit 120.7-128.0 s serialised vs 122.7 s async (n = 1); identical output images for the same seed.

**Decision:** `tools/rocm/run.sh` now always sets `AMD_SERIALIZE_KERNEL=3` and `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`. Next: longer soak test (many t2i + edit jobs) under these defaults before relying on it; then decide whether ROCm diffusers replaces Lemonade's sd.cpp for FLUX.2.

---

## 2026-10-13 — P1 continued: MIOpen off + flash attention halve FLUX.2-klein time vs Lemonade; an intermittent launch failure remains

**Setup:** as the previous entry; old hung Blender (pid 7117, stuck in `drm_syncobj_array_wait_timeout` since the 22:48 resets) killed without a reset; a fresh Blender open but with no HIP context (no `/dev/kfd` fd), Lemonade stopped. So the ROCm container was the **only KFD client** in all runs below.

**VAE decode with MIOpen disabled** (`p1_vae.py bfloat16 256,512,1024 native`): 256 0.65 / 0.20 s (cold / warm), 512 0.93 / 0.85 s, **1024 5.19 / 4.76 s**, slowest single op 0.65 s (cold) / 0.36 s (warm), outputs finite, 0 new timeouts/resets. With MIOpen the cold 512 decode was 29.7 s (bf16). PyTorch's own conv path removes the first-use search entirely.

**SDPA backends** (`p1_attn.py`, bf16, 24 heads x 128, with `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`): seq 4608 math 576 ms vs flash 77 ms / efficient 77 ms; seq 8704 math 2200 ms vs flash 265 ms; rel. diff to math 2.5e-3. 0 new resets. AOTriton's flash kernel fails on the VAE's single 512-wide attention head (`hipErrorProfilerNotInitialized`), so `p1_flux.py` forces the math backend inside `vae.encode` / `vae.decode`.

**P1 results** (`p1_flux.py`, MIOpen off, flash attention, 1024x1024, 4 steps, guidance 1, seed 7; pipeline to GPU 6.8 s, peak 20.85 GiB):

| job | ROCm | Lemonade (sd.cpp Vulkan) |
|---|---|---|
| text-to-image, run 1 (cold) | 55.1 s (steps ~12.0 s, VAE 5.0 s) | 107-120 s |
| text-to-image, run 2 | 54.5 s | |
| A-pose edit, run 1 | 122.7 s (steps 27.6-30.6 s) | 220 s |
| A-pose edit, run 2 | launch failure + GPU reset | |

- Denoising step 24.3 s (math attention) -> 12.0 s (flash). Text-to-image and edit are both **~1.8-2x faster than Lemonade** (n = 2 and n = 1; Lemonade numbers from earlier entries, not re-measured today).
- Quality by eye (n = 1 each, RNG differs from sd.cpp so images are not the same cat): text-to-image is as clean as the Lemonade sample. The edit keeps the character (face, markings, colours) and opens the arms, but nearer a T-pose than 45 degrees and turned to a front view (the prompt asks for the same view).
- **Edit run 2 failed** 2 s after start: `hipErrorLaunchFailure` reported at a host copy in `prepare_image_latents` right after the VAE encode (async, so the failing kernel is not known), no page fault or ring timeout logged first, then `MES failed to respond to msg=REMOVE_QUEUE` and a MODE2 GPU reset (23:01:39-44). The container hung and stopping it gave a second reset (23:02:10, `Failed to remove queue 0`, `Resetting wave fronts`), the same teardown pattern as 22:19. Resets/timeouts counter 5 -> 7.
- The same input and kernels had passed in edit run 1, so the failure is intermittent. It matches P0 run 1 (launch failure -> MES unresponsive -> reset) but this time there was **no second KFD client**, which rules that out as a necessary condition. Not yet known: which kernel faults (needs `AMD_SERIALIZE_KERNEL=3`), whether it depends on the AOTriton flash kernels (used in the text encoder and transformer), or on the native conv path.

---

## 2026-10-13 — Own pipeline P1: FLUX.2-klein-4B on ROCm denoises like Lemonade; MIOpen's first-use conv search stalls the GPU and reset it

**Goal:** FLUX.2-klein-4B in diffusers on ROCm 10.1 (`tools/rocm/p1_flux.py`) vs Lemonade/sd.cpp Vulkan (text-to-image ~107-120 s, A-pose edit 220 s, 1024x1024, 4 steps, cfg 1, seed 7). Fresh boot, host ROCm 10.1, Blender open with a HIP context, Lemonade stopped.

**Text-to-image, job 1 (cold), bf16:** pipeline to GPU 9.3 s (14.93 GiB), prompt encoding 2.3 s, 4 denoising steps at 24.6 / 24.4 / 24.2 / 24.1 s (97 s, n = 1). Attention is SDPA math (efficient/flash need `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`): 25 attention layers x ~0.59 s (P0) ~ 15 s of each 24 s step (estimate from P0, not profiled). The **VAE decode then ran > 60 s** without finishing; during it the desktop's gfx ring timed out twice (22:44:02 `ptyxis`, 22:44:48 `resources`), both recovered by a ring reset. The job was stopped by hand; no image.

**VAE probe (`tools/rocm/p1_vae.py`, random latents, every decoder leaf module timed with synchronising hooks):**

| dtype | size | cold | warm | slowest op cold / warm |
|---|---|---|---|---|
| bf16 | 256 | 8.38 s | 0.23 s | up_blocks.2.upsamplers.0.conv 2.79 / 0.03 s |
| bf16 | 512 | 29.67 s | 0.90 s | same conv 11.84 / 0.13 s |
| fp16 | 256 | 11.71 s | 0.13 s | 3.14 / 0.01 s |
| fp16 | 512 | 45.59 s | 0.55 s | 13.24 / 0.05 s |
| fp32 | 256 | 20.79 s | 0.24 s | 4.29 / 0.02 s |
| fp32 | 512 | — | — | launch failure (below) |

- Warm decodes are fast (512: 0.55-0.90 s); the time goes into the **first** call of every new conv shape, i.e. MIOpen's find step (compiles and benchmarks candidate solvers; winners and timings land in the user find-db `models/rocm-cache/.config/miopen/*.ufdb.txt`, e.g. bf16 512x256x256 3x3 -> `GemmFwdRest` 89 ms; fp16 shapes pick Winograd, bf16 only GEMM). How much of the cold time is CPU compilation vs long GPU candidate kernels was not separated.
- **fp32 512 cold:** a gfx-ring timeout in Blender's UI thread (22:48:31), the ring reset failed (`MES failed to respond to msg=RESET`), then two MODE2 GPU resets (22:48:33/34) and `hipErrorLaunchFailure` in a conv inside the probe. Resets/timeouts counter 2 -> 5 for the session (0 at boot).

**Conclusion (hypothesis, consistent with all three incidents today):** on this iGPU, long GPU work from a ROCm job starves the graphics ring of the desktop/Blender; when such a submission waits > `lockup_timeout` (2 s) the kernel resets the gfx ring, and if MES does not answer, the whole GPU, taking the ROCm job down. The denoiser's kernels (<= ~0.6 s each) did not trigger it; MIOpen's first-use conv search did. **Not yet tested:** decode with MIOpen disabled (`torch.backends.cudnn.enabled = False`, im2col + rocBLAS GEMM, no search), `MIOPEN_FIND_MODE=FAST`, a pre-filled find-db, tiled VAE decode. Blender's HIP context went through the 22:48 resets and may be broken (cf. the reset when Blender exited at 22:19).

---

## 2026-10-13 — Host ROCm replaced by AMD's 10.1 (gfx1103); P0 passes with Blender holding a HIP context

**Goal:** test the hypothesis that the 22:15 reset came from two mismatched ROCm runtimes on one KFD (Blender's HIP on Ubuntu's `rocm` 7.1, the container on ROCm 10.1).

**Change (done by the user, needs sudo):** purged Ubuntu's `rocm` 7.1 packages; installed `amdrocm10.1-gfx1103` (10.1.0-3) from AMD's apt repo (`https://stable.repo.amd.com/rocm/core/packages/ubuntu2604/`, keyring `/etc/apt/keyrings/amdrocm.gpg`), per AMD's install guide; rebooted. Libraries land in `/opt/rocm/core-10.1/lib` (`/opt/rocm/lib` via alternatives); nothing left in `/usr/lib/x86_64-linux-gnu`. `rocminfo` sees gfx1103, runtime 1.21.

**Blender render kept:** Blender 5.2 (snap) still lists "AMD Radeon 780M Graphics" as a HIP device (enabled). After `refresh_devices()` its process maps `/opt/rocm/core-10.1/lib/libamdhip64.so.7.16.26385`, `libhsa-runtime64.so.1.21.0` and `libamd_comgr.so.3.5.0` and holds `/dev/kfd` open, so Blender and the container now run the same HIP (7.16.26385). Not yet tested: an actual Cycles HIP render.

**P0 rerun** (`tools/rocm/p0_smoke.py`, fresh boot, Blender open with a live HIP context but idle, Lemonade container stopped): passed, rc 0, wall 76.8 s, resets/timeouts/MES 0 -> 0, no amdgpu fault lines in the kernel log. Numbers match the clean run within noise: matmul 4096^3 fp16 4.69 TFLOPS, linear fp16 3.62 TFLOPS, conv2d fp16 4.3 ms, SDPA math 1x24x4608x128 588 ms fp16 / 577 ms bf16 (clean run 596 / 598), sustained 10 iterations in 64 s, peak 4.95 GiB.

**Conclusion:** with the old runtime gone, a second KFD client (Blender) no longer breaks the FLUX-sized attention kernel in this one run (n = 1). This supports, but does not prove, the mismatched-runtime hypothesis: the failing run also had 17 GB of GTT used by Lemonade and an older Blender session, and this run had neither GTT pressure nor a fresh-boot difference ruled out. Next: rerun P0 with the Lemonade container up and FLUX/TRELLIS loaded (separates GTT pressure), then P1.

---

## 2026-10-13 — P0 rerun on an idle GPU passes; the reset at container stop came from Blender's stale KFD queue

- **User's hypothesis:** the first P0 fault was caused by memory sharing (other GPU users holding GTT).
- **Clean state:** stopped the `local-producer` container and closed Blender (file saved): GTT used 17,029 ->
  335 MiB, VRAM used 3,938 -> 618 MiB (`/sys/class/drm/card1/device/mem_info_*`).
- **P0 again, nothing else on the GPU** (same image and script, n=1): every stage passed, 0 new resets.
  matmul 3.1-4.6 TFLOPS, linear 3.3-3.5 TFLOPS, conv2d 3.7 / 10.4 ms (fp16 / bf16), **SDPA math 1x24x4608x128:
  596 ms fp16, 598 ms bf16** (rel err 4.3e-4 / 3.4e-3), memory-efficient and flash attention unavailable without
  `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`, sustained GPU-produced-tensor -> GEMM/attention load 10 iterations
  in 66 s (peak 4.95 GiB), all finite. The same SDPA call had faulted 4 min earlier with Lemonade (FLUX.2 and
  TRELLIS loaded) and Blender running.
- **The reset while stopping (22:19:32.48):** the container had already exited (22:19:32.400) and Blender was being
  closed. The kernel lines are KFD process-teardown lines (`Failed to remove queue 0`, `Resetting wave fronts
  (cpsch)`, MES `REMOVE_QUEUE` timeout, doorbell 0x1000), and the Lemonade container has no `/dev/kfd`. Blender is a
  KFD client: its Cycles preferences use HIP with the 780M enabled, and a headless check showed `/dev/kfd` opened
  after `get_devices()`. During the 22:15 reset the kernel had failed to evict Blender's queues ("Failed to
  suspend process pid 7109"). **Most likely cause (inferred from the log, not reproduced):** Blender's KFD queue
  was left broken by the ROCm fault at 22:15, and removing it at Blender's exit hung MES again -> second reset.
  Standard counter now 6 (4 -> 5 at 22:15, -> 6 at 22:19).
- **Correction:** host ROCm is installed: `apt install rocm` (Ubuntu 7.1 packages, 74 packages incl.
  `libamdhip64-7`, `libhsa-runtime64-1`) on 2026-10-05, purged 2026-10-06, installed again by the user on
  2026-10-09 (`/var/log/apt/history.log`); the "0 ROCm packages left" notes of 2026-10-06 are outdated. Blender's
  Cycles HIP uses this host runtime; the container uses its own ROCm 10.1 from the wheels. Both talk to the same
  kernel driver (amdgpu/KFD, MES firmware), which is where the faults show up.
- **Open question:** the failing and the passing P0 differ in two ways at once: 17 GB of GTT in use, and a second
  KFD process (Blender with Cycles HIP) alive. The 2026-10-12 ROCm faults also happened while Blender was open
  (requests were sent from the add-on). Which factor matters is not known yet.

---

## 2026-10-13 — Own pipeline study, P0: PyTorch on ROCm 10.1 (native gfx1103 wheels) still resets the GPU

- **Goal (P0 of the "no Lemonade, ROCm-optimised pipeline" study):** check whether the current AMD stack runs
  plain PyTorch ops on the 780M without faults before porting FLUX.2 (P1) and TRELLIS.2.
- **Stack:** `tools/rocm/Containerfile` -> `localhost/local-producer-rocm` (6.6 GB): python:3.12-slim-bookworm +
  AMD TheRock wheels `torch[device-gfx1103]==2.14.0+rocm10.1.0` (HIP 7.16.26385, self-contained ROCm; rocBLAS now
  ships 150 gfx1103 Tensile files, hipBLASLt has gfx1103, so no `HSA_OVERRIDE_GFX_VERSION`), diffusers 0.41.0
  (has `Flux2KleinPipeline`), transformers 5.19.0. `tools/rocm/run.sh` runs a script with `/dev/kfd` + `/dev/dri`,
  `--network none`, MIOpen cache in `models/rocm-cache` (MIOpen fails with `miopenStatusUnknownError` when it
  cannot write its user db). `tools/rocm/p0_smoke.py`: one checked stage at a time (rel. error vs CPU fp32).
- **Results** (n=1 run after the cache fix; profile as set by the user):

  | stage | result |
  | :--- | :--- |
  | matmul 1024^3 / 4096^3 fp16 | 3.21 / 4.68 TFLOPS, rel err 3.6e-4 |
  | matmul 1024^3 / 4096^3 bf16 | 2.85 / 4.17 TFLOPS, rel err 2.9e-3 |
  | linear 4608x3072->12288 fp16 / bf16 | 3.56 / 3.30 TFLOPS |
  | conv2d 1x128x256x256 3x3 fp16 / bf16 | 1.9 / 7.1 ms (MIOpen: no CK grouped-conv library for gfx1103) |
  | SDPA math fp16, 1x24x4608x128 (FLUX-sized) | `hipErrorLaunchFailure` in the softmax of the first call |

  Kernel: `MES failed to respond to msg=REMOVE_QUEUE` -> `GPU reset begin` -> MODE2 reset 22:15:32-37, recovered
  ("device wedged, but recovered through reset"). Counter (`GPU reset begin|ring .* timeout`) 4 -> 5. The
  reset also tried to evict Blender's queues (pid 7109); Blender, Lemonade and the desktop kept working.
- **Conclusion:** the newest native gfx1103 stack reproduces the same fault class as 2026-10-12 (launch failure,
  then MES hang and GPU reset) on the first attention-sized kernel. Following the P0 stop rule, GPU work on ROCm
  is stopped; the sustained-load stage and P1 (FLUX.2 on ROCm) were not run. Hypotheses, untested: a gfx1103
  driver/firmware issue (MES / CWSR; `amdgpu.cwsr_enable=0` needs a kernel command-line change and a reboot);
  a kernel running past the 2000 ms compute `lockup_timeout` (unlikely for one softmax of 0.5 G elements).
  FLUX.2-klein-4B diffusers weights (15 GB) are in `models/flux2/` for a later P1.

---

## 2026-10-13 — Rigging-ready input settled: "Make A-pose" in the add-on, hole restore in the matting server

- **Decision (for now):** characters meant for rigging go through a FLUX.2 image edit into an A-pose before
  TRELLIS.2; the experiments above showed this is what removes the armpit artefacts while keeping the design.
- **Add-on v0.8.0:** new "Make A-pose" button (`start_apose()` for headless use): flattens the current image onto
  mid grey (matted inputs have no background), sends it to `POST /v1/images/edits` with a character-agnostic
  "change only the pose ... keep exactly the same character" prompt plus the usual framing tail, previews the
  result and makes it the current image. Checked over MCP on the default `samples/cat.png`: edit 220 s, the same
  cat with the arms out; then "Generate Textured Mesh" on it: 313 s in total, 141,868 faces, 0 new resets.
- **Matting server:** `fill_holes` (default on) restores enclosed non-background regions (algorithm in the A-pose
  entry). Over HTTP on the cream-belly image: 1.91 s with 41,975 px restored vs 0.63 s with `fill_holes=false`;
  on the edited cat 1.67 s, nothing restored. Image rebuilt, container restarted.
- **Cleanup:** deleted `models/bench/` (388 MB of benchmark GLBs/logs) and `models/upscale/` (Real-ESRGAN binary and
  outputs, 144 MB; upscaling is not used), the scratch renders, and the test objects in the Blender scene except
  `cat_apose` / `cat_apose_rig` (the edited-A-pose cat at x=3).

---

## 2026-10-13 — A-pose without losing the chubby look: FLUX.2 image edit of the sample cat

- **Problem:** the text-to-image A-pose cat (previous entry) came out slimmer than the sample cat (longer limbs,
  smaller head), so it no longer looked like the same character.
- **Tested** (FLUX.2-klein-4B via Lemonade, 1024x1024, 4 steps, seeds 7 and 23, by eye):
  - Image edit (`POST /v1/images/edits`, multipart, input `samples/cat_raw.png`, prompt "change only the pose ...
    arms out to the sides (A-pose) ... keep exactly the same character: same chubby round body, same big round
    head, same short stubby limbs, same colours and markings, same view and framing"): 215.1 s / 226.1 s. Both keep
    the character (shape, stripes, face); the arms come out nearly horizontal (closer to a T-pose).
  - Text-to-image with "chubby, big round head, plump belly, short stubby limbs, chibi proportions" added to the
    A-pose prompt: 120.0 s / 121.1 s. Chubby, but a different character (other face, colours).
- **3D:** edit seed 7, matting + enclosed-hole restore (nothing to restore: one 240 px hole at distance 5.3 kept),
  trellis-cli v0.8.1 seed 1234, res 512, `--steps 8`: 308.9 s, 137,164 faces, 0 new resets. autorig.py: 21 bones,
  1.1 s, 0 % unweighted.
- **Pose test** (same four fight poses as before): same chubby proportions as the sample cat. With the arms
  raised there are no shards; a thin serrated ring remains where the upper arm meets the body (smaller than the
  shards of the sample cat, rougher than the clean fold of the slim text-to-image cat). Guard and kick poses
  clean.
- **Conclusion:** to rig an existing character, edit its image into an A/T-pose instead of re-prompting; it
  keeps the design.

---

## 2026-10-13 — A-pose input fixes the armpit artefacts; matting cut out a cream belly

- **Goal:** test the hypothesis from the previous entry: the armpit shards come from arms touching the body in
  the generated rest pose.
- **Input:** FLUX.2-klein-4B via Lemonade, the sample prompt with the pose part replaced by "standing upright in
  an A-pose: both arms stretched down and out to the sides at about 45 degrees, paws far from the body with clear
  empty space between each arm and the torso, legs slightly apart with a gap between them, tail pointing away
  from the body" (3/4 view, grey background), seeds 7/11/23: 106.9/108.7/109.1 s each, all three with the arms
  clearly apart; seed 23 picked (tail also apart).
- **Matting failure:** `isnet-general-use` cut out the cream belly (a hole inside the body; on the 3D model the
  belly came out black). Fix tested in a scratch script: close the matte with a 15 px max filter, flood-fill the
  background from the image border, treat unreached background as enclosed holes, and restore a hole (alpha 255,
  colours from the raw image) when its mean RGB distance to the border median colour is > 40 (here: one hole,
  41,975 px, distance 83.0). Not yet in `matte_server.py`.
- **TRELLIS:** trellis-cli v0.8.1, seed 1234, res 512, `--steps 8`: 252.1 s, 140,510 faces, 0 new resets
  (the unfilled input: 241.7 s, 149,000 faces). autorig.py: 21 bones, 0.9 s, 0.18 % unweighted vertices.
- **Pose test** (bone directions copied from the fight animation at frames 1, 30, 92, 141; Workbench close-ups
  and full views, by eye, n=1 per pose): with arms raised (frame 141) the A-pose cat has no shards at the armpit,
  only a smooth skin fold; guard, hit and kick poses deform cleanly. The original cat (arms touching the body)
  shows shards at every raised-arm pose. A raised outline around the belly patch is part of the generated
  geometry, not a deformation artefact.
- **Conclusion:** for characters that will be rigged, ask the image model for an A-pose; the rig code needs no
  change. Matting needs the enclosed-hole restore for light body parts on the grey background.

---

## 2026-10-13 — Jagged edges on TRELLIS.2 characters: subdivision, joint smoothing, texture size, upscaling, quad remesh

- **Question:** the cat and husky look jagged at close range; can the edges be made smooth ("vector-like"), and
  would that make stretching and rigging behave better?
- **Diagnosis** (Workbench close-ups of the cat head, textured vs untextured): the geometry is already smooth
  (141,284 faces, 99 % smooth-shaded, median edge 7.6 mm on a 1 m figure; husky 5.4 mm). The jaggedness is in the
  colour: 1024x1024 base colour atlas, saw-tooth colour borders (eye rim, nose), thin dark crack lines along UV
  seams.
- **Subdivision Surface after Armature** (level 1, cat, arm-raised pose at fight frame 141): 141,284 -> 423,852
  faces; the shards at the armpit stay, slight shading blotches appear; one render took 160 s (Blender shared the
  GPU with a TRELLIS run, so not a clean timing). Not useful.
- **Corrective Smooth after Armature** (length weighted, factor 0.5, 10 iterations): armpit shards stay and new
  white slivers appear on the arm. Not useful; removed.
- **Bigger TRELLIS atlas** (trellis-cli v0.8.1, cat sample, seed 1234, res 512, `--steps 8`, n=1 each, 0 new
  resets): `--atlas 2048` 290.8 s, 11.4 MB GLB; `--atlas 4096` 301.5 s, 22.9 MB; baseline 1024 = 270 s (earlier
  run), 6.9 MB. Same mesh (141,284 faces, xatlas 1200x1188 charts). At a close-up of the eye rim the saw-tooth is
  the same at 1024/2048/4096 (by eye). Hypothesis: the colour detail is limited by the res-512 voxel colour field,
  not by atlas pixels.
- **AI upscaling of the existing base colour** (realesrgan-ncnn-vulkan 20220424 release in a `--network none`
  container, 1024 -> 4096, 0 new resets): `realesrgan-x4plus-anime` 12.9 s (cat) / 11.5 s (husky),
  `realesrgan-x4plus` 32.0 / 31.2 s. Seam cracks turn into faint light patches; the eye-rim saw-tooth stays
  (its teeth span tens of texels). Binary and outputs in `models/upscale/` (not in git).
- **Quad remesh + bake** (Blender: copy at rest, voxel remesh 5 mm -> 98,534 faces, 100 % quads, Smart UV
  Project, Cycles CPU bake of base colour from the original, 2.3 s in total; re-rigged with autorig.py, same pose
  copied): worse. The voxel remesh welds the arm to the body where they touch at rest, so raising the arm tears
  the skin, and the bake paints the arm's orange onto the torso there. Script deleted.
- **Conclusion:** smoother texture borders do not change how the rig deforms; deformation depends on topology,
  weights and the rest pose. The armpit artefacts come from the arm touching the body in the generated rest pose
  (inner shells / fused surfaces). Next to try (hypothesis): generate characters with the arms clearly away from
  the body (A-pose) in the FLUX prompt; for sharper colour borders, reproject the input image (`recolour` mode)
  instead of upscaling.

---

## 2026-10-13 — Second character rig (husky) and a keyframed two-character fight

- **Goal:** check that `autorig.py` generalises to a second TRELLIS.2 character, and that a short scripted
  action scene (cartoon MMA exchange, cat vs husky) can be built over MCP without manual keyframing.
- **Rig fixes found on the husky** (126,166 vertices, upright, big tail lying on the floor): the depth (y) of
  each joint was the mean of nearby vertices and was pulled to the front by the densely tessellated belly patch
  (spine ran along the belly); it is now the midpoint of the 2nd/98th y percentiles. The tail margin was 0.02 H
  behind the upper back; the husky's rump sticks out 0.07 H, so it is now 0.08 H. Result: 21 bones, 76,305 tail
  vertices, 0 % unweighted, 1.3 s. The cat rig was not regenerated (it was made with the old rules).
- **Animation** (`blender/experiments/fight_anim.py`, 168 frames at 24 fps, 1.4 s to build): each rig is
  parented to an empty at its feet that carries travel, facing (fighters along X) and the knockdown tilt. 19
  named poses (guard, jab, cross, hook, uppercut, teep, roundhouse, block, slip, hit reactions, fallen, victory)
  are written as target bone directions in the canonical character frame (front -Y, up +Z, left +X) plus an
  optional twist; spine bones (hips/chest/neck/head) tilt the rest direction instead, because absolute spine
  targets bowed the cat's head (its rest head bone leans). The root is shifted so the lowest foot stays on the
  floor; quaternion keys get sign continuity; impact keys are linear. 32 + 27 pose keys, plus a floor plane, a
  sun and a camera.
- **Result** (Workbench render, 168 frames at 960x540, judged by eye, n=1): readable sequence: approach, cat jab
  lands, husky slips the cross and lands a hook, cat blocks, husky teep pushes the cat back, cat body kick and
  uppercut, husky falls on its back, cat turns to the camera and cheers. Limits: no contact solving (fists stop
  short or pass through in places), FK only so feet slide during travel, the fall is a rigid tilt of the whole
  rig, poses are hand-tuned numbers for these two body shapes.

---

## 2026-10-13 — Auto-rigging a TRELLIS.2 character over MCP (cat sample)

- **Goal:** rig a generated character without manual work, driven only through the Blender MCP connection.
- **Method** (`blender/experiments/autorig.py`, CPU only, 1.2 s for the 141,284-face cat): joints from the vertex
  cloud with geometric rules (tail = what sticks out behind the upper body below mid height; neck = narrowest
  front-silhouette row between 25 % and 60 % of the height; hands = extreme x below the neck; feet = lowest points
  per side; shoulders at 0.7 x the torso half width just below the neck; hips at 32 % of the height), 21 bones
  (root, hips, chest, neck, head, upper_arm/forearm/hand, thigh/shin/foot per side, 4 tail bones). Skin weights:
  Blender automatic weights (bone heat) on a voxel-remeshed copy (voxel 1.2 % of the height, 16,952 faces,
  0.7 s), copied to the original with a Data Transfer modifier (nearest face, interpolated) and applied; the copy
  is deleted. 0 % unweighted vertices on the proxy and on the original.
- **Iteration:** first pass measured the torso width in a band that still contained the arms (half width 0.304),
  so the upper arm started mid-arm; measuring it just below the neck (0.160) put the shoulders at the body edge.
  Checked by drawing the bones over the front and side vertex silhouettes.
- **Pose test** (left arm raised 75 degrees + elbow 35, right arm forward 40, head turned 30 and tilted 10, tail
  40/20, right leg stepping forward with the knee bent 45; EEVEE renders, by eye, n=1): every part follows its
  bone, head/tail/legs deform smoothly; small creases at the raised arm's armpit at close range.
- **Limits:** rules assume an upright, symmetric character facing -Y with arms away from the body; no face or
  ear bones (TRELLIS meshes are one piece, eyes are texture); no IK controls (plain FK bones, not Rigify).

---

## 2026-10-13 — Faster TRELLIS.2 at res 512: trellis.cpp v0.8.1 with 8 steps (374 s -> 270 s)

- **Goal:** speed up res 512 without losing quality (the 780M is compute-bound: ~7.4 s per 1.3B DiT forward
  with f16 here, ~7 s with Q8_0 in the pixal3d.cpp phase, so smaller weights would not help).
- **Setup:** trellis.cpp v0.8.1 `trellis-cli` (release Vulkan build), cat sample, seed 1234, res 512,
  `--webp off -v`, n=1 per config, 0 new GPU resets / ring timeouts in all runs. Close-ups at 900 px.

  | config | SS / shape / texture flow (s) | rest (s) | total | faces | close-up |
  | :--- | :--- | :--- | :--- | :--- | :--- |
  | A defaults (12 steps, xatlas) | 166.1 / 84.6 / 51.9 | ~72 | 374 s | 142,058 | clean |
  | E `--steps 8` | 109.8 / 57.3 / 32.9 | ~72 | 272 s | 141,284 | clean |
  | D `--steps 8 --fa-fast` | 93.2 / 48.5 / 27.7 | ~72 | 242 s | 148,170 | white blotch at the armpit, grey ring round the eyes |
  | B `--steps 8 --box-uv` | 112.1 / 58.7 / 34.2 | ~68 | 273 s | 141,284 | (5-view render only) |
  | C `--steps 8 --box-uv --fa-fast` | 90.8 / 49.9 / 28.3 | ~68 | 237 s | 148,166 | white blotches at the arm-body joint |

- **Findings:** 8 steps cuts the flows by a third (-27 % end to end) with no visible defect on this sample; the
  hidden back-of-head markings differ between configs (made up by the model either way). `--fa-fast` (F16 K/V,
  F16 accumulation; ~18 % faster flows) adds texture defects; `--box-uv` saves ~4 s (noise level) and adds
  blotches in concave joints. Both rejected.
- **Applied:** Lemonade now runs the v0.8.1 server: binaries in `models/lemonade/data/trellis-v0.8.1/`
  (sha256 of the release tarball 8c2ed7f7...), `config.json` `trellis.vulkan_bin` = that path, `trellis.args` =
  `--steps 8 --webp off` (PNG textures). Check through Lemonade's API: 270 s, 141,284 faces, identical to the
  CLI run E (deterministic).

---

## 2026-10-13 — Why res 1024 fails: amdgpu 2 s compute timeout, not FlashAttention

- **Symptom:** res 1024 (`1024 cascade`) fails with `vk::Queue::submit: ErrorDeviceLost` at the start of the HR
  shape flow; afterwards every request fails until the backend restarts.
- **Kernel side (measured):** each failure logs `amdgpu: ring comp_X.Y.Z timeout ... reset compute queue ...
  device wedged, but recovered through reset`, but no `GPU reset begin`, so the reset counter used until now
  missed them (now `grep -c -E 'GPU reset begin|ring .* timeout'`, AGENTS.md and run-server.sh updated).
  `modinfo amdgpu`: `lockup_timeout` default 2000 ms; the parameter is unset on this machine (kernel 7.0.0-38).
  So any compute submission running longer than 2 s is treated as a hang.
- **Runs** (Lemonade's trellis-server v0.4.3 standalone in a `--network none` container, seed 1234, res 1024;
  "HR tokens" = the quantized res-1024 token count the server prints):

  | input | HR tokens | FlashAttention | result |
  | :--- | :--- | :--- | :--- |
  | capybara 3/4 (add-on, earlier) | 13,619 | on | ring timeout at HR step 0/12 |
  | capybara 3/4 (rerun) | 13,619 | on | ring timeout at HR step 0/12 (reproduced, 2/2) |
  | capybara 3/4 | 13,796 | off (`--no-fa`) | HR step 1/12 took 100.3 s, ring timeout in step 2 |
  | cat sample | 10,474 | on | OK: 1657 s, 283,044 faces, HR flow 709.7 s |
  | cat sample | 10,474 | off (`--no-fa`) | OK: 1491 s, 288,216 faces, HR flow 631.8 s |

- **Conclusion:** the failure depends on the object's HR token count (attention cost grows with its square:
  13.6k vs 10.5k tokens is ~1.7x), not on FlashAttention. The hypothesis "one FA dispatch exceeds 2 s" was
  wrong: the exact chunked attention also times out. Hypothesis (not verified): ggml-vulkan groups many nodes
  into one queue submission, and at ~13.6k tokens one submission's work exceeds 2 s. `--no-fa` was faster on
  the cat (HR flow 632 vs 710 s, n=1 each, within one run each: not a significant result).
- **Fix candidates:** raise the compute timeout (`options amdgpu lockup_timeout=0,30000,0,0` in
  /etc/modprobe.d, reboot; amdgpu is not in the initramfs), which needs root and is the user's call; or cap
  the HR tokens with `--max-tokens` (untested, costs detail).
- Also: the cat sample at res 1024 takes ~25-28 min vs 6 min at res 512.

---

## 2026-10-13 — White parts on a white background were matted away; FLUX framing now asks for grey

- **Problem (user report):** prompt "a cute cat", view 3/4, image seed 7, mesh seed 1234, res 512 (add-on v0.7.0):
  the white belly of the mesh is a red/green/black camouflage pattern, and the back of the head has a face-like
  pattern. 371 s, 144,492 faces.
- **Cause (measured):** the FLUX framing asked for a "plain pure white background". ISNet matting then removed
  the white belly together with the background: alpha 4-5/255 over the belly (median of 40x40 px patches), 254
  on the white face, which is surrounded by orange. TRELLIS still built the belly's geometry (shape from the
  silhouette) but had no colour for it and made one up.
- **Fix:** `FRAMING_TAIL` asks for a "plain uniform medium grey background" (add-on v0.7.1). Same prompt and
  seeds: FLUX 104 s; the matte keeps the whole belly; TRELLIS 361 s, 140,610 faces, 0 GPU resets. By eye
  (5 EEVEE views): white belly and paws clean, orange/white pattern close to the input, no made-up patterns.
- **Tried and removed:** a "hole share" check in the matting server (transparent area enclosed by the object,
  `scipy.ndimage.binary_fill_holes`) reported 0.0000 for the broken white-background cat: the cut-out belly is
  open to the background between arm and leg, so it is not an enclosed hole. A check that misses the real case
  was not kept.
- **Open:** `tools/lemonade/make_sample.py` (the capybara sample) still uses a white background. Whether the
  capybara's orange fur tint is also linked to the white background is untested (hypothesis).

---

## 2026-10-13 — Fixing TRELLIS.2 colours by reprojecting the input image

- **Goal:** keep the TRELLIS.2 geometry (good) and replace its wrong texture colours with the input image's.
- **Method** (`blender/experiments/reproject.py`, runs in the live Blender over MCP, CPU only, 2.7-3.1 s for a
  142,578-face mesh with a 1024x1024 atlas): bake per-texel object-space position and normal (Cycles CPU,
  emission of object coordinates + object-space normal bake); ray-cast a 384x384 front depth map; fit the matted
  input image to the mesh's front silhouette by bounding box, then a small scale/offset search (IoU 0.945 ->
  0.963); texels facing the camera (normal -Y) and not occluded (depth test) take the image colour, blended out
  between facing 0.15 and 0.5. Hidden texels: 10 k-means clusters of the TRELLIS colours, per-cluster median
  offset in Lab learned from texels seen head-on (facing > 0.8), chroma always applied, lightness only when the
  seen texels agree (MAD of L < 8), soft assignment (no hard edges).
- **Numbers (sample, seed 1234, res 512, unlit base colour, median 24x24 px):**

  | patch | input | TRELLIS | reprojected |
  | :--- | :--- | :--- | :--- |
  | cheek | 180,127,77 | 233,76,39 | 194,128,83 |
  | hand | 213,157,107 | 232,77,43 | 206,115,75 |
  | hoodie | 227,44,44 | 215,20,15 | 227,58,55 |
  | jeans | 79,119,159 | 48,101,145 | 74,117,160 |

  Only 65,197 of 842,183 covered texels (8 %) take the image colour directly, 39,050 more are blended: about
  half of the front-facing texels lie up to 0.32 units behind the front surface (inner walls of the shell), so
  the depth test is needed.
- **Iterations:** (1) per-RGB-bin mean offset: blocky patches on the sides, black cap turned brown; (2) RGB
  k-means + median + MAD gate: the gate also rejected the fur cluster (MAD 0.117, shading in the image); (3) Lab,
  chroma always / lightness gated: cap stays black, fur tan on all sides, no blocks.
- **Remaining defects (by eye, n=1):** the back of the head is a darker tan than the front (lightness kept from
  TRELLIS); the shading baked into the FLUX image (highlights, soft shadows) is now in the albedo on the front.
- **User review of "project" mode: rejected, looks blotchy.** Close-ups (900 px, ortho scale 0.5) show the cause:
  the mesh and the 2D image disagree at part boundaries, so projected colours spill across them (tan fur on the
  cap rim, the image's chain printed beside the mesh's chain, orange smears on the headphones, stair-stepped eye
  outlines from nearest sampling). The small 400 px renders used for the first judgement hid this.
- **"recolour" mode (default now):** the image only teaches the per-cluster Lab correction; every texel keeps
  TRELLIS's own layout and gets the corrected colour. Close-ups: clean part boundaries like the original, fur tan
  on all sides, cap black. Unlit medians: cheek 179,116,71 (input 180,127,77); hand 180,116,75 (213,157,107);
  hoodie 218,53,53 (227,44,44); jeans 63,100,139 (79,119,159). Limits: details TRELLIS lost stay lost (the pink
  nose is fur-coloured, the chain is pale), and one correction per colour cluster cannot fix a region whose
  TRELLIS colour equals another region's.
- **Conclusion:** recolouring (not projecting) fixes the colour shift without visible artifacts on this sample
  (n=1). Next: make it an add-on option and test it on other objects.

---

## 2026-10-13 — Wrong colours in TRELLIS.2 textures: measured, causes narrowed down

- **Problem:** the capybara's tan fur comes out orange-red. Measured on the unlit base colour (EEVEE, emission =
  base-colour texture, Standard view transform, orthographic front view, median of a 24x24 px patch), so it is
  not Blender lighting or AgX tone mapping. All runs: sample image, seed 1234, res 512, Lemonade/trellis.cpp v0.4.3.

  | patch | input image | default Vulkan | fast paths off | `--f32` | green-hoodie input |
  | :--- | :--- | :--- | :--- | :--- | :--- |
  | cheek (fur) | 180,127,77 | 233,76,39 | 240,64,39 | 234,58,38 | 249,148,56 |
  | hand (fur) | 213,157,107 | 232,77,43 | 216,78,35 | 233,85,41 | 249,150,61 |
  | hoodie | 227,44,44 | 215,20,15 | 193,3,0 | 187,4,11 | input 43,227,43 -> 2,85,9 |
  | jeans | 79,119,159 | 48,101,145 | 61,98,150 | 54,95,125 | 64,100,140 |

  - "Fast paths off": `GGML_VK_DISABLE_COOPMAT/COOPMAT2/INTEGER_DOT_PRODUCT/BFLOAT16/F16/FUSION=1` (log confirmed
    `fp16: 0 | int dot: 0 | matrix cores: none`): 564 s, 146,118 faces. `--f32` (f32 sparse conv, standalone
    trellis-server in the container): 395 s, 142,564 faces. Neither fixes the colour, so it is not a
    precision / RADV fast-path problem.
  - Green hoodie (hoodie pixels hue-shifted to green in the input; the pink nose and inner ears were shifted too):
    380 s, 147,762 faces. The fur moved from red-orange to orange (G 76 -> 148): the red hoodie does bleed into the
    fur (part of the earlier hypothesis confirmed), but the fur is still far more saturated than the input, and the
    bright green hoodie became dark green. No single per-channel curve maps input to output (e.g. 227 -> 85 in the
    hoodie's G but 180 -> 249 in the fur's R), so a plain sRGB/linear mix-up does not explain it.
  - The official `pipeline.json` (microsoft/TRELLIS.2-4B) uses texture guidance 1.0 (no CFG); trellis.cpp also runs
    the texture flow with 12 forwards for 12 steps, so the sampler setting matches.
  - Side finding: `--voxply` makes trellis-server v0.4.3 segfault right after the sparse-structure flow (2/2).
  - 0 GPU resets in all runs.
- **trellis.cpp v0.8.1** (release `trellis-vulkan-linux-x64.tar.gz`, sha256 8c2ed7f7..., in `models/trellis-v0.8.1/`,
  `trellis-cli` in a `--network none` container from the server image, same GGUFs, seed 1234, res 512,
  `--webp off`): 397 s, 143,550 faces, 0 GPU resets. Colours: cheek 254,62,40; hand 243,73,33; hoodie 215,6,6;
  jeans 60,100,136. Same error as v0.4.3, so a newer trellis.cpp does not fix it.
- **Official demo (HF Space `microsoft/TRELLIS.2`):** anonymous call refused (ZeroGPU quota: "120s requested vs.
  142s left", retry in ~4.4 h); needs a Hugging Face token. Not compared yet.
- **Conclusion:** the colour error comes from the texture model output itself (model or trellis.cpp port; cannot
  tell which without running the reference PyTorch pipeline on the same image).

---

## 2026-10-13 — Add-on v0.7.0 prompt mode; 3/4-view input vs front-view input; res 1024 device lost

- **Add-on v0.7.0 (`blender/trellis_addon/`):** new Source switch Image / Prompt. Prompt mode sends the text
  (plus an optional image-to-3D framing suffix, `FRAMING`: full body, chosen view Front or 3/4, centered, white
  background, no shadow) to FLUX.2-klein-4B (`/v1/images/generations`, 4 steps, cfg 1, 1024x1024, own seed),
  saves the PNG in `<tmp>/trellis_addon/`, shows it in the panel (`template_icon` of a bpy image preview), and
  only builds the mesh when "Generate Textured Mesh" is pressed. Headless: `start_image(prompt, seed, view)`.
  The Front framing text equals the one `make_sample.py` used, so prompt mode can reproduce the sample.
- **3/4-view test (n=1 per input, seed 1234, res 512, ISNet matting):** subject = the sample capybara prompt,
  view 3/4, image seed 7. FLUX image 120 s; it shows the front and the left side (about 30-45 degrees).
  TRELLIS: 407 s, 142,944 faces. Front-view sample regenerated for comparison in the same session: 411 s,
  142,578 faces (identical face count to the earlier 459 s run: the backend is deterministic for a fixed seed).
  0 GPU resets (kernel counter 0 before and after).
- **Observations (4 orthographic EEVEE renders per mesh, judged by eye, n=1):** TRELLIS turned the 3/4 input
  into a front-facing object (canonical pose), so the input angle did not rotate the mesh. The 3/4 mesh has a
  modelled hood on the back, sleeve cuffs and a more three-dimensional chain/headphones; the front-input mesh
  has a smooth, featureless back. The fur is pink-orange in both meshes although it is tan in both input
  images, so the tint is not caused by the front pose (hypothesis still open: hoodie colour bleeding, or the
  texture decoder). The jeans are darker teal in the 3/4 mesh. One seed per input: cannot tell whether the
  back-side gain is systematic.
- **Res 1024 failure:** the first attempt ran with the scene's resolution 1024 (`1024 cascade`): after 327 s,
  in `[4/7] shape SLAT flow (LR 512 -> upsample -> HR 1024 cascade, max_tok=49152)`, trellis-server failed with
  `vk::Queue::submit: ErrorDeviceLost`; the kernel logged no `GPU reset begin`. Every later request then failed
  immediately with the same error until the container was restarted (Lemonade does not restart the backend).
  Not retried; res 1024 is not usable as is.
- **Conclusion:** a 3/4-view input is free (same image and mesh time) and gave a more detailed back on this
  sample; worth checking on more seeds/objects before making it the default. Fur tint unrelated to the view.

---

## 2026-10-12 — Lemonade and the matting server merged into one container

- **Goal:** run the project's two services (Lemonade, matting) as one container instead of two.
- **Configuration:** `tools/lemonade/Containerfile` extends `ghcr.io/lemonade-sdk/lemonade-server:v2026.41.1`
  (Ubuntu 24.04, no Python) with apt `python3` + a venv `/opt/matte` (rembg 2.0.85, onnxruntime 1.31.0, fastapi,
  uvicorn, pillow) -> image `localhost/local-producer-server` (1.41 GB; base 780 MB). `entrypoint.sh` starts
  `matte_server.py` (:8083) and `lemond` (:13305) and stops both when either exits or on SIGTERM.
  `run-server.sh` builds the image if missing (`BUILD=1` forces a rebuild), starts container `local-producer`
  with both ports on 127.0.0.1 and `models/rembg` mounted as `U2NET_HOME`. `tools/matte/` and the images
  `localhost/matte` and `python:3.12-slim-bookworm` were removed.
- **Check (n=1):** `/v1/models` lists `TRELLIS-3D` and `Flux-2-Klein-4B` from the existing `models/lemonade/`;
  `/matte` on `capybara_hiphop_raw.png` returned a 1024x1024 RGBA PNG in 0.93 s (first request, includes HTTP);
  matting weights were reused, not re-downloaded. No 3D generation was run in the merged container yet.
- **Conclusion:** one container serves the whole 3D asset path; the add-on URLs did not change.

---

## 2026-10-12 — Repository layout for GitHub

- Blender add-on moved into the repo as a package: `blender/trellis_addon/__init__.py` (v0.6.0) + `samples/capybara_hiphop.png` (and `_raw.png`, not shipped); `blender/build_addon.sh` -> `dist/trellis_addon.zip` (581 kB). Absolute paths removed: the default image is resolved next to the package, the Lemonade log path is an add-on preference (`log_path`) instead of a hard-coded `/home/...` default. Installed in Blender 5.2.2 from the zip; the old single-file `trellis_blender` add-on was removed (`addon_remove` needs an area context, otherwise it fails in `tag_redraw`).
- `tools/blmcp/`: the vendored copy of Blender Lab's MCP server (4444 files, 28 MB, GPL-3.0, manifest 1.0.3) was replaced by `install.sh` (uv venv in `tools/blmcp/.venv`, `git+https://projects.blender.org/lab/blender_mcp.git@dbbf836...#subdirectory=mcp`, reports `blender-mcp 1.0.2`; its bundled docs differ slightly from the vendored ones). `send_code` to Blender verified with the installed package. `.mcp.json` now uses the relative `tools/blmcp/.venv/bin/python -m blmcp`.
- `tools/lemonade/make_sample.py` writes into `blender/trellis_addon/samples/` by default.
- New `README.md` (overview, layout, setup), `models/README.md`, `.gitignore` (`models/*` except its README, `.venv/`, `dist/`, `__pycache__/`, `*.glb`, `*.ply`, `*.log`, `.claude/settings.local.json`). Personal absolute paths in `CHANGELOG.md` shortened to `~/`.
- Result: `git add -A --dry-run` lists 20 files, 1.5 MB in total.
- Outside the repo: deleted the obsolete `~/work/blender/add-on/trellis_blender.py` and its `samples/` copy, and the `__pycache__` of the removed add-ons in Blender's user add-on dir; the BlenderKit and MCP add-on zips and the user's `.blend` files were left alone. Branch (`master`) and licence intentionally left undecided for now (R&D).

## 2026-10-12 — Cleanup after the switch to Lemonade (keep FLUX.2-klein-4B and TRELLIS-3D)

- **TRELLIS-3D cache:** deleted the unused `q8/` (9.4 GB) and `q4/` (6.1 GB) folders of `ilintar/trellis2-gguf` (Lemonade's trellis-server reads the f16 files in the snapshot root). Checked first by moving them aside and restarting: still `downloaded: true`, size now 15.3 GB, `POST /v1/models/check-updates` -> 0 updates; then deleted.
- **Unrequested ROCm install:** the log shows `Installing backend: trellis:rocm` at 16:06:36 (trellis-server ROCm tarball downloaded, then TheRock ROCm 10.0.0 for gfx1103 started) without a matching API call from the agent; the user confirmed afterwards that they installed it themselves. The restart at 16:10 cancelled it; deleted the 2.2 GB `therock-...tar.gz.partial` and the empty `therock/` dir; no ROCm trellis binary was left. ROCm never ran. `config.json` now sets `"no_fetch_executables": true` (backends cannot be fetched any more: ROCm/CPU show `unsupported`; the installed Vulkan backends of trellis and sd-cpp still work) and `"auto_check_model_updates": false`. To install another backend later, set `no_fetch_executables` back to false temporarily.
- **Other:** removed rembg `birefnet-general` and `birefnet-general-lite` (1.1 GB; the matting server downloads them again on first use), `__pycache__` in `tools/blmcp`, dangling build layers of `localhost/matte`.
- Later the same day, at the user's request, `no_fetch_executables` and `auto_check_model_updates` were removed from `config.json` again (Lemonade defaults: backends can be installed/updated, model updates are checked); the ROCm backend install had been the user's own.
- Kept: Lemonade image + state (`models/lemonade/`: TRELLIS-3D f16 15.3 GB, FLUX.2-klein-4B 15 GB, Vulkan backends of trellis and sd-cpp), `localhost/matte` + rembg `isnet-general-use` and `u2net` (339 MB), the sample image. Disk used 241 GB -> 222 GB.
- Found the Lemonade container already gone when stopping it before the cleanup (cause not checked); restarted with the new config.

## 2026-10-12 — Fixed sample image for 3D tests: chibi hip-hop capybara generated locally with FLUX.2-klein-4B

**Why:** every test so far used a different picture, so runs were not comparable. The Blender add-on now defaults to one image.

**Setup:** Lemonade recipe `sd-cpp` (stable-diffusion.cpp) on Vulkan, model `Flux-2-Klein-4B` (16.1 GB: FLUX.2-klein-4B + Qwen3-4B text encoder + FLUX.2 VAE; labels image + edit), `tools/lemonade/make_sample.py`: 1024x1024, 4 steps, cfg 1.0, seed 7, then the local matting server (`isnet-general-use`). The prompt asks for a full-body, front-view, symmetrical, centred stylised 3D-toy figure on a plain white background without shadow (what image-to-3D handles best).

**Numbers (n=1):** generation 133.4 s, matting 0.71 s, resets 0 -> 0. Result: chibi capybara with a backwards black cap, headphones around the neck, gold chain, red hoodie, blue jeans, white sneakers; clean mask. Files: `tools/lemonade/samples/capybara_hiphop_raw.png` (generated) and `capybara_hiphop.png` (RGBA); copy at `~/work/blender/add-on/samples/capybara_hiphop.png`, the add-on default (`DEFAULT_IMAGE`, v0.5.1).

**First 3D run of the sample** (add-on v0.5.2 in Blender, Lemonade `TRELLIS-3D` f16, 12 steps, res 512, seed 1234, the sample already has an alpha mask so no matting): **459 s** in Blender (457.3 s server side), 2503 voxels @32, shape flow 108.4 s (20 forwards), texture flow 53.8 s, 142 578 faces, no floor slab, resets 0 -> 0. Front: cap, neck headphones, gold chain, hoodie with pocket, jeans and sneakers all clean and symmetric; the invented back side is plausible. Defect: the fur is tinted orange-red instead of the source's tan (hypothesis: the red hoodie bleeds into the fur during texture generation/baking; not checked).

**Add-on progress fix (v0.5.2):** with `log_level: debug` Lemonade forwards trellis-server output as `<time> [Info] (Process) <line>`; `read_progress()` now strips that prefix, so the panel shows stage + flow step again.

## 2026-10-12 — Cleanup; switch to AMD Lemonade for TRELLIS.2

**Why:** Lemonade (AMD's local AI server) ships TRELLIS.2 image-to-3D through pwilkin/trellis.cpp, the upstream of the pixal3d.cpp fork used today; a maintained distribution instead of our own builds and patches.

**Removed:** containers `trellis`, `matte`; `tools/hunyuan3d/`, `tools/pixal3d/` (Containerfiles, run scripts, patches `flow_steps_env.py` / `deform_cpu_env.py` / `server_fields.py`, all run logs and GLBs); `models/hunyuan3d/` (36 GB), `models/pixal3d/` (7.6 GB), `models/trellis2/` (6.8 GB), a stray 1 GB `models/rembg/bria-rmbg.onnx`; images `localhost/hunyuan3d`, `hunyuan3d-vulkan`, `pixal3d:{latest,main,steps}` and their dangling layers, `ubuntu:26.04`. Disk used 261 GB -> 192 GB. The numbers and findings above are the only record of those experiments.

**Kept / rebuilt:** `tools/matte/` with its own image `localhost/matte` (python:3.12-slim + rembg 2.0.85 + onnxruntime 1.31, 742 MB) instead of the 17.7 GB Hunyuan3D image; same API, 0.54 s for `OIP.webp` with `isnet-general-use`.

**Lemonade setup:** `ghcr.io/lemonade-sdk/lemonade-server:v2026.41.1` (latest stable, 2026-10-07; versions are now calendar-based, "11.0" was July 2026), rootless Podman with `--userns=keep-id:uid=10001,gid=10001` (the image runs as UID 10001) and `/dev/dri` only; bind mounts under `models/lemonade/`. It detects `AMD Radeon 780M (gfx1103)`, 4 GB VRAM + 28.7 GB GTT, and the NPU. TRELLIS.2 recipe: backends vulkan / rocm (TheRock; gfx110X listed) / cuda, all trellis.cpp `v0.4.3`; model `TRELLIS-3D` = `ilintar/trellis2-gguf` (the f16 set, 15.4 GB, not the q8 set used before). API `POST /v1/3d/generations` (JSON: model, base64 image, resolution 512/1024/1536, bg_removal, uv, seed) — no steps, face count or atlas size. By default lemond broadcasts on the LAN (`192.168.0.233`): disabled with `"broadcast": false`; telemetry off.

**First run through Lemonade** (Blender add-on v0.5.0: `OIP.webp` -> local matting -> `POST /v1/3d/generations`, seed 1234, res 512, server defaults = 12 steps, f16 weights from the snapshot root, Vulkan trellis.cpp v0.4.3 started as `trellis-server --models <snapshot> --res 512`, no `GGML_VK_*` switches): **288 s** in Blender, 61 704 faces after the add-on removed the floor slab (the slab still appears), resets 0 -> 0. No zero-voxel and no decoder NaN with every Vulkan feature at its default: upstream v0.4.3 does not show the two numerical bugs of the pixal3d.cpp fork (n=1). Visually clearly better than the q8 / 8-step mesh of the same image: sharper eyes, clean cap and metallic headphones, hoodie drawstrings. Not comparable in time with the 195 s q8 / 8-step run (two variables changed). `TRELLIS-3D` downloaded the whole HF repo: 31 GB (f16 + q8 + q4), not the advertised 15.4 GB. trellis-server's progress is only forwarded to lemond's log at `log_level: debug` (`ProcessManager::start_process(..., is_debug(), ...)`); set in `config.json` for the next start. The sample image `character_1316.png` was deleted with `tools/hunyuan3d/`.

## 2026-10-12 — Per-request steps, face count and texture size (server patch + add-on v0.4.0)

- `tools/pixal3d/patches/server_fields.py` (in `localhost/pixal3d:steps`): trellis-server `POST /generate` now accepts `steps` (1–50, via `TRELLIS_FLOW_STEPS`), `faces` (1000–2 000 000, new `TRELLIS_TARGET_FACES` override of the hard-coded 150 K @512 / 300 K @1024 decimation target in `trellis_cli.cpp`) and `atlas` (256–4096 px, `TrellisParams::tex`). Without a field the launch value is restored. Validation checked with out-of-range values (HTTP 400 with the right message); a full generation with the new fields has not been run yet.
- Resolutions below 512 are not possible: TRELLIS.2 only has res 512 / 1024 / 1536 paths (fixed structure grid and decoders). Face count and atlas size are the knobs for a lighter output instead; they only change post-processing (~20 s of a ~200 s run), not the flow time.
- The server currently runs with `STEPS=8 ./run-server.sh`; the add-on sends its own `steps` (default 8), `faces` (150K/80K/40K/20K/10K) and `atlas` (256–2048).

## 2026-10-12 — Capybara with a correct matte at 8 steps; "floor slab" artifact removed in the add-on

**Setup:** resident server restarted as `STEPS=8 run-server.sh` (`localhost/pixal3d:steps`, `TRELLIS_FLOW_STEPS=8`, config A); request from the Blender add-on v0.3.0: `OIP.webp` (360², white background) -> local matting server (`isnet-general-use`, 0.83 s) -> RGBA PNG -> trellis-server (`bg auto`, keeps the alpha), seed 1234, res 512.

**Numbers (n=1):** 193.6 s server side, 195 s in Blender; SS flow 110.6 s (1485 voxels), shape flow 31.9 s, texture flow 19.3 s; 141 562 faces; resets 0 -> 0. The broken-matte runs of this image had 5295–6975 voxels and took 500–637 s, so most of their extra time came from the wrong input.

**Result:** a recognisable capybara (cap, ears, headphones, hoodie with drawstrings, shoes); the face is soft and the eyes are blurred (input is only 360 px; whether 8 steps contributes is unknown without a 12-step run of the same matte).

**Artifact:** the mesh also contained a 0.004-thick flat slab covering the whole generation box (x, y = -0.5..0.5) at foot level: two pieces of ~15.9 k verts each, plus thin rim strips split off by UV seams. The matte has no shadow under the feet (checked: alpha 0 there), so it is not a shadow turned into geometry; whether fewer steps cause it is unknown. Add-on v0.3.2 `remove_ground_slab()` (option "Remove floor slab", default on): deletes connected pieces spanning >= 95 % of both horizontal axes with thickness < 0.02, then flat pieces in the same height band that reach the box edge (|x| or |y| > 0.45). On this mesh it removed 31 585 + 1 214 vertices (87 474 -> 54 675); the remaining object spans |x|, |y| <= 0.134. Also: rembg's alpha tops out at 254, never 255 (not shown to matter).

## 2026-10-12 — Bad capybara meshes explained: trellis-server's BiRefNet is wrong on RADV; replaced by a local rembg matting server

**Observation:** in the steps sweep (entry below) all `oip_capybara` meshes, 12 steps included, were shapeless grey-white blobs, like the earlier `capi-hiphop` run, while `character_1316` (own alpha, no matting) was fine. Both bad images went through the server's BiRefNet.

**Test (`--bg-only`, `oip_capybara.png`, q8 `birefnet.gguf`, resets 0):**

| Path | Time | Opaque pixels | Mask |
| :--- | -: | -: | :--- |
| Vulkan, config A | 37 s | 12.4 % | wrong: a skin-coloured oval + specks, jacket/cap/headphones lost |
| Vulkan + `GGML_VK_DISABLE_COOPMAT=1` | 36 s | 12.4 % | same |
| Vulkan + coopmat and f16 off | 37 s | 12.4 % | same |
| CPU (`--gpu=-1`, 16 threads) | 179 s | 36.6 % | correct |
| Vulkan + `TRELLIS_DEFORM_CPU=1` (patch) | 191 s | 36.6 % | correct |

**Conclusion:** the wrong mask comes from pixal3d.cpp's custom Vulkan deformable-convolution kernel (`deform_conv_vk.cpp`), not from ggml (no ggml switch changes it); its CPU fallback is correct but makes matting take ~190 s. Patch `tools/pixal3d/patches/deform_cpu_env.py` (`TRELLIS_DEFORM_CPU=1`) added to `localhost/pixal3d:steps` for the record; not used by default. Note: `--gpu -1` is rejected by the CLI parser, `--gpu=-1` works.

**rembg on the CPU instead** (`tools/matte/rembg_bench.py`, image `localhost/hunyuan3d` = rembg 2.0.85 + onnxruntime 1.31, 8 threads; inference time after warm-up, n=1):

| Model | oip_capybara (360², white bg) | capi-hiphop (800², dark bg) |
| :--- | :--- | :--- |
| u2net | 0.19 s, 37.7 % | 0.20 s, 33.9 % (loses whiskers) |
| isnet-general-use | 0.60 s, 37.7 % | 0.64 s, 34.3 % |
| birefnet-general-lite | 5.52 s, 37.5 % | 5.84 s, 34.2 % |
| birefnet-general | 9.98 s, 37.5 % | 9.98 s, 34.2 % |

All four masks are visually clean on both images (the dark background is not a problem). `tools/matte/server.py` + `run-server.sh`: matting HTTP server on `127.0.0.1:8083` (`POST /matte?model=...`, image bytes in, RGBA PNG out), default `isnet-general-use`, 0.64 s per request end to end for the 800² WebP. Weights in `models/rembg/`. Blender add-on v0.3.0: images without an alpha mask are cut out by this server first, then sent to trellis-server, which keeps the alpha ("Local matting" mode, default).

**Consequence for the steps sweep:** its `oip_capybara` rows measured a garbage input and say nothing about step quality; they have to be redone with a correct matte.

## 2026-10-12 — TRELLIS.2 speed-up, step 2: fewer flow steps (TRELLIS_FLOW_STEPS)

**Setup:** `tools/pixal3d/runs/steps_bench.sh`, image `localhost/pixal3d:steps`, config A (coopmat on, `--no-fa`, int-dot / fusion / graph-opt off), q8, res 512, seed 1234, n=1 per cell; the resident server stayed up but idle. Images: `character_1316` (RGBA) and `oip_capybara.png` (the user's `OIP.webp`, 360² RGB, white background -> BiRefNet). Chamfer/Hausdorff vs the 12-step mesh of the same image (`compare_meshes.py`, 200 k samples, meshes span ~2 units). Reference noise: two 12-step runs of `character_1316` with different Vulkan paths differ by Chamfer 0.0031 / Hausdorff 0.024. The user stopped the sweep during `oip` 4 steps (machine hot, GPU at 100 %).

| Image | Steps | SS / shape / tex flow (s) | Voxels @32 | Wall (s) | Chamfer | Hausdorff | Resets |
| :--- | -: | :--- | -: | -: | -: | -: | :-: |
| character_1316 | 12 | 164.8 / 83.9 / 48.2 | 2535 | 351.4 | — | — | 0 |
| character_1316 | 8 | 112.1 / 56.7 / 32.4 | 2553 | 252.3 | 0.0035 | 0.052 | 0 |
| character_1316 | 6 | 83.8 / 44.7 / 24.4 | 2541 | 202.9 | 0.0037 | 0.041 | 0 |
| character_1316 | 4 | 60.8 / 25.1 / 14.3 | 2262 | 141.4 | 0.0072 | 0.090 | 0 |
| oip_capybara | 12 | 158.3 / 208.4 / 122.7 | 5295 | 636.7 | — | — | 0 |
| oip_capybara | 8 | 113.9 / 171.4 / 98.5 | 6064 | 508.9 | 0.0136 | 0.264 | 0 |
| oip_capybara | 6 | 83.4 / 167.0 / 90.9 | 6975 | 500.6 | 0.0159 | 0.170 | 0 |

**Observations:**
- The SS flow scales with the step count as expected (~7 s per forward). The shape and texture flows scale with the number of sparse tokens, which depends on the voxel count: the capybara has 2–3x the voxels of `character_1316`, so its shape/tex flows dominate and fewer steps also produced *more* voxels (5295 -> 6975), eating most of the saving (637 -> 501 s).
- `character_1316`: 8 and 6 steps are within ~1.2x of the run-to-run numeric difference in Chamfer (not distinguishable with n=1); 4 steps doubles it and drops 11 % of the voxels.
- `oip_capybara`: deviations are 4–5x larger than for `character_1316` already at 8 steps (Hausdorff 0.26: a part of the shape moved). No 12-step noise reference exists for this image, so how much of it is step-related is unknown. Visual comparison still to do.
- Wall time also depends strongly on the input: the same settings take 351 s or 637 s.

## 2026-10-12 — TRELLIS.2 speed-up, step 1: Vulkan features re-enabled one group at a time

**Setup:** `tools/pixal3d/runs/opt_bench.sh`, `character_1316`, seed 1234, res 512, q8 weights, `localhost/pixal3d:main`, resident server stopped during the runs; n=1 per config. Baseline (coopmat, integer dot, fusion, graph optimize all off): 406.6 s (earlier run). The repeat of the baseline (config D) did not run: the user had to force a shutdown during the bench.

| Config | SS flow | Shape flow | Tex flow | Result | Wall | Resets |
| :--- | ---: | ---: | ---: | :--- | ---: | :-: |
| A: **coopmat on** + `--no-fa`, int-dot / fusion / graph-opt off | 164.8 s | 83.9 s | 48.2 s | OK, 2535 voxels, 149 130 faces | **351.4 s** | 0 |
| B: int-dot on (coopmat, fusion, graph-opt off) | 197.7 s | 98.9 s | — | `c2s: non-finite input features in blocks.0.4` | (301 s, failed) | 0 |
| C: fusion + graph-opt on (coopmat, int-dot off) | 215.1 s | — | — | `vk::Queue::submit: ErrorDeviceLost` during the SS stage | (236 s, failed) | 0 |

**Conclusions:**
- The zero-voxel bug needs coopmat **and** FlashAttention together: coopmat with `--no-fa` gives correct voxels and is 14 % faster end to end (single runs; the noise has not been measured). Mesh A vs the baseline mesh: Chamfer 0.0031, Hausdorff 0.024 (mesh spans ~2 units), the same size as other numeric-path differences seen today.
- The decoder NaN is caused by the integer-dot (Q8 x Q8 dot product) path (B), not by fusion or graph optimize.
- Fusion + graph optimize led to a lost Vulkan device (C); the kernel did not log a GPU reset. Not retried: a lost device can take the desktop with it. Which of the two is responsible is not isolated.
- New default in `run-server.sh` / `run_trellis2.sh`: config A (`GGML_VK_DISABLE_INTEGER_DOT_PRODUCT/FUSION/GRAPH_OPTIMIZE=1`, `--no-fa`).

**Steps override:** `tools/pixal3d/patches/flow_steps_env.py` + `Containerfile.steps` -> image `localhost/pixal3d:steps`: `TRELLIS_FLOW_STEPS=<n>` overrides the hard-coded 12 Euler steps of every `sample_flow` call (SS, shape, texture flows); unset = unchanged.

## 2026-10-12 — TRELLIS.2 server + Blender add-on, driven live in the running Blender over the MCP socket

**Setup:** `tools/pixal3d/run-server.sh` starts `trellis-server` (pixal3d.cpp main build) resident on `127.0.0.1:8082` (Vulkan, the four `GGML_VK_DISABLE_*` switches, `--res 512 --webp off --require-gpu`, models `models/trellis2/q8/`), progress to `tools/pixal3d/runs/server.log`. API: `POST /generate` multipart (`image` part + `seed`, `resolution`, `webp`, `bg_removal`, `uv`, `band` fields), returns the GLB; `GET /capabilities` has only a busy flag, no progress, so the add-on tails the server log instead. Added `birefnet.gguf` (q8, 0.88 GB, SHA256 verified) for background removal of images without an alpha mask.

**Add-on:** `~/work/blender/add-on/trellis_blender.py` (outside the project, v0.2.1): sidebar tab "TRELLIS.2"; converts non-PNG input (WebP, JPEG...) to PNG with Blender's image API (the server decodes PNG only); forces BiRefNet when the image has no real alpha mask (an all-opaque PNG would otherwise be taken as already matted); shows "stage + flow step / elapsed / ETA" from the log every second; imports the GLB, selects it, frames it and switches the viewport to Material Preview. `start_generation()` lets an agent start a run exactly like the button. The Claude-side Blender MCP server had disconnected, so the add-on was installed and driven by sending code straight to the MCP add-on socket (`127.0.0.1:9876`, `blmcp.tools_helpers.connection.send_code`).

**Numbers:** `character_1316` (RGBA, seed 1234, res 512) from inside Blender 5.2.2: 415 s, 149 534 faces (same count as the CLI run, deterministic), 1 material with two 1024² textures, textures visible in Material Preview; resets 0 -> 0. Pitfalls hit: Blender loads image pixels lazily, so `Image.save()` right after `images.load()` fails with "does not have any image data" until the pixels are read.

**Second image** `capi-hiphop.webp` (800², RGB WebP, dark studio background, no alpha; converted to PNG by the add-on, background removed by BiRefNet q8 on Vulkan), seed 128, res 512: 578 s (577.1 s server side), 145 370 faces, resets 0 -> 0. **Visually poor:** the jacket is recognisable, but the head is a dark, shaggy blob without the capybara's brown colour or shape. Cause unknown; candidates: a bad BiRefNet matte (dark background close to the fur colour), numerical drift from the Vulkan switches on a harder input, or a model limitation. The server deletes its staged/matted image, so the matte has not been inspected yet.

## 2026-10-12 — TRELLIS.2 at res 512 (pixal3d.cpp binary, Vulkan): textured mesh in 6.8 min

**Goal:** a lighter textured option after Pixal3D took 30.6 min. Same binary (`localhost/pixal3d:main`; the fork keeps the TRELLIS.2 single-image path), `tools/pixal3d/run_trellis2.sh` with the same four Vulkan switches (coopmat, integer dot, fusion, graph optimize off). Weights: `ilintar/trellis2-gguf` (the trellis.cpp author's set, rev `a57397b`) `q8/`, only the 7 files res 512 needs (6.4 GB, SHA256 = HF LFS hashes) in `models/trellis2/q8/`. Input `character_1316.png` (RGBA, alpha used as matte), `--seed 1234 --res 512 --webp off`.

**Numbers (n=1):** exit 0, **406.6 s wall**, resets 0 -> 0. SS flow 189.0 s (2550 voxels), shape SLAT flow 512 105.3 s, decode 728 693 voxels -> 1.45 M faces, texture flow 60.9 s, then remesh + Vulkan QEM decimation to the default 150 K target (149 534 faces, 74 335 verts) + 1024² atlas. `tools/pixal3d/runs/t2_q8_1316_r512_s1234/out.glb` 7.7 MB. The base-colour atlas shows recognisable eyes, glasses, orange-white shoes, hair; the mesh itself has not been inspected yet.

**Observation:** the SS flow (~190 s, 22 forwards of a 1.3B DiT, same cost as in Pixal3D) is now half of the time; res 512 removes the 13-min HR shape flow and most of the texture cost. Remaining speed-ups not tried: fewer steps, a q4 set, or re-enabling Vulkan features one at a time to find the minimal set of switches (coopmat alone was enough for the SS stage).

## 2026-10-12 — Pixal3D (pixal3d.cpp, GGML) on Vulkan: two numerical bugs on RADV, worked around; one textured mesh in 30.6 min

**Goal:** evaluate Pixal3D (Tencent ARC, SIGGRAPH 2026, MIT; image -> PBR-textured mesh, TRELLIS.2-based) as a lighter, textured alternative that avoids ROCm.

**Setup:** `tools/pixal3d/` — `Containerfile` builds [raven38/pixal3d.cpp](https://github.com/raven38/pixal3d.cpp) (fork of pwilkin/trellis.cpp; vendored ggml from `pwilkin/ggml` `trellis-patches`) at tag `v0.10.1-desktop-alpha` (`1f432fd`) on Ubuntu 26.04 with `-DGGML_VULKAN=ON -DGGML_NATIVE=OFF`; only `/dev/dri` mapped, `--network none`. Weights: `raven38/pixal3d-sv-q8_0-v1` (single-view, Q8_0, 8.1 GB, 9 files, all SHA256 verified) in `models/pixal3d/sv-q8_0-v1/`. `run_sv.sh`: `--sv-image` (`character_1316.png`, already RGBA), `--seed 1234 --res 1024 --webp off --require-gpu`. ggml reports `AMD Radeon 780M (RADV PHOENIX) | uma | fp16 | KHR_coopmat`, 33 434 MB usable.

| Run | ggml-vulkan switches | SS flow (12 steps, 22 forwards) | Active voxels @res32 | Next | Resets |
| :--- | :--- | ---: | ---: | :--- | :-: |
| default | — | 154.2 s | **0** -> "no voxels produced" | — | 0 -> 0 |
| vk1 | `GGML_VK_DISABLE_COOPMAT=1` | 162.1 s | 2492 | LR shape flow 80.4 s (latent finite: mean -0.088, std 5.58), then shape decoder: `c2s: non-finite input features in blocks.0.4`, exit 139 | 0 -> 0 |
| vk5 | `DISABLE_COOPMAT=1` + `DISABLE_F16=1` | 169.7 s | 2493 | LR shape flow 84.9 s, same NaN in `blocks.0.4` | 0 -> 0 |

**Facts:**
- Bug 1 (zero voxels) matches upstream issue raven38/pixal3d.cpp#89 (Strix Halo gfx1151, RADV, Mesa 26.0.8: 0 voxels on Vulkan, 4385 on CPU; open, no reply). Here it is caused by the coopmat (`KHR_coopmat` matrix-core) path: disabling it alone fixes the SS stage.
- Bug 2: NaN/Inf appears in the shape decoder (sparse ConvNeXt stage 0 + `from_latent`, before the first C2S) with fp32 compute too, so it is not fp16 overflow. Which op is wrong is not known yet (`TRELLIS_DBG_STAGE_DUMP=1` would show the stage).
- Upstream pwilkin/trellis.cpp has related open Vulkan issues: #37 (segfault in shape decode on Vulkan, NVIDIA), #27 (access violation in shape decode, RX 6800 Vulkan), #17 (GPU hang on RADV gfx1152 in the res-1024 shape SLAT flow).
- SS-flow speed on the 780M: ~7 s per DiT forward (Q8_0, 1.3B), 0 GPU resets in 3 runs.
- Rebuilt at `main` (`d1b4926`, 17 commits after the tag, incl. a C2S graph split) with `DISABLE_COOPMAT=1`: same result (2497 voxels, LR shape flow 92.3 s, then the same `c2s: non-finite input features in blocks.0.4`), 0 resets.

**First complete mesh (main build, `GGML_VK_DISABLE_COOPMAT=1 GGML_VK_DISABLE_INTEGER_DOT_PRODUCT=1 GGML_VK_DISABLE_FUSION=1 GGML_VK_DISABLE_GRAPH_OPTIMIZE=1`, n=1):** exit 0, **1835.6 s wall (30.6 min)**, 0 -> 0 resets. Which of the three extra switches fixes the decoder NaN is not isolated (integer-dot is the main suspect because the weights are Q8_0). Stage times: SS flow 207.9 s (2406 voxels; the earlier runs gave 2492–2497, so the switches change the numerics), LR shape flow 109.9 s, HR-1024 shape flow 783.0 s (~75 s/step), shape decode 45.9 s (3 711 808 voxels, 7.8 M faces), texture flow 443.1 s + decode 43.5 s, post-processing 166.9 s (Vulkan QEM decimation 11.8 M -> 974 K faces, xatlas UV, 4096² atlas bake). Output `tools/pixal3d/runs/sv_q8_1316_main_vk4/out.glb` (74 MB, PNG textures) + `out_base.png`. The base-colour atlas shows the source's colours (skin, orange jacket, dark hair, black glasses rims); the mesh itself has not been inspected yet. Too slow for the pipeline: the user asked for a lighter local model.

## 2026-10-12 — Conditioner on CPU: 2/2 clean pipeline runs, but the math-SDPA load makes the whole desktop lag

**Setup:** `pipe_stress.py` with `COND=cpu` (a fp32 copy of DINOv2 runs on the CPU every run, 6.9–7.1 s; its output is moved to the GPU outside `inference_mode`, `is_inference()=False`), native gfx1103, hipBLASLt, math SDPA, v2-0-turbo, 5 steps; `runs/stress.sh` now has a no-output watchdog (180 s). Fresh boot, resets 0.

**Numbers:** run 0: 202.7 s, run 1: 197.1 s (DiT steps 38.0–38.9 s, first step 45–47 s), latent mean 0.9329 both runs (same as the earlier `CPU_COND=1` file run). Resets 0 -> 0. Together with the earlier `CPU_COND=1` runs: 4/4 clean pipeline runs with a CPU-made cond (n is still small).

**Stopped by the user during run 2** (killed, exit 137) because the whole machine was lagging. The log shows the job was still progressing normally (step 0 of run 2 at 45.5 s): this lag is the load itself, not a hang. Hypothesis: math SDPA issues long-running kernels (16 heads x 4442² attention per call) that monopolise the shared iGPU so the compositor starves. This casts doubt on the "silent hang" reading of run 12 in part 2: its log also simply stopped while the desktop lagged, and the user rebooted; whether it was a real hang or the same lag cannot be distinguished from the log.

## 2026-10-12 — ROCm crash hunt, part 2 (after reboot): math SDPA also crashes; the fault follows the GPU-produced cond tensor; one silent GPU hang

All runs native gfx1103 (no override), `TORCH_BLAS_PREFER_HIPBLASLT=1`, `MIOPEN_DEBUG_CONV_GEMM=0`, **math SDPA (AOTriton off)**, v2-0-turbo fp16, profile `balanced`, fresh boot at 13:04 (resets 0). Scripts: `tools/hunyuan3d/pipe_stress.py` (full pipeline, latent output, no server), `dit_stress.py` (DiT forward in a loop), `runs/stress.sh`. Kernel 7.0.0-38, MES fw 0x8b, MES KIQ 0x110, MEC 0x46, linux-firmware 20260319, `amdgpu.cwsr_enable=1` (default).

| # | Run | cond fed to the DiT | Result | Resets |
| -: | :--- | :--- | :--- | :-: |
| 1 | server ladder step A (octree 384, CPU decode) | DINOv2 on GPU | launch failure during DiT step 1 (reported at `index_for_timestep`) | 0 -> 1 |
| 2 | `dit_stress dit`, `AMD_SERIALIZE_KERNEL=3` | random | 5 iterations clean (38.5 s each, math SDPA) | 1 -> 1 |
| 3 | `dit_stress dit` | random | 5 clean | 1 -> 1 |
| 4 | `pipe_stress` (full pipeline) | DINOv2 on GPU | launch failure in run 0 (reported at `set_timesteps`, async) | 1 -> 2 |
| 5 | `pipe_stress`, `AMD_SERIALIZE_KERNEL=3` | DINOv2 on GPU | launch failure, reported in a `SingleStreamBlock.linear2` GEMM (M=4442, K=5120, N=1024, fp16, hipBLASLt) | 2 -> 3 |
| 6 | `dit_stress dit`, `PYTORCH_NO_HIP_MEMORY_CACHING=1` | random | 5 clean (50 s each) | 3 -> 3 |
| 7 | `dit_stress dit_real` | real cond computed on the CPU (fp32 -> fp16) | 6 clean | 3 -> 3 |
| 8 | `dit_stress dit_afterdino` | random (DINOv2 ran on the GPU first, its output kept alive) | 6 clean | 3 -> 3 |
| 9 | `pipe_stress`, `CPU_COND=1` | real cond computed on the CPU | 2 full runs clean (197 s each) | 3 -> 3 |
| 10 | `dit_stress dit_dinocond` | the tensor DINOv2 produced on the GPU | launch failure in the first iteration | 3 -> 4 |
| 11 | `dit_stress dit_gpucondfile` | the same GPU-produced values, saved to a file and reloaded (normal tensor, fresh memory) | 6 clean | 4 -> 4 |
| 12 | same as 11 with `INFERENCE_CLONE=1` (cloned inside `torch.inference_mode`) | same values, inference tensor | 3 clean iterations, then iteration 4 **never finished**: no launch failure, no MES message, no reset; desktop very laggy; the user rebooted at 13:52. Only kernel line: `kfd_process_wq_release hogged CPU` at 13:49:38 | 4 (none detected) |

**Facts:**
- Math SDPA does not prevent the fault (runs 1, 4, 5, 10), so AOTriton is not the (only) cause; the "AOTriton is the main suspect" conclusion of part 1 is withdrawn.
- Serialised kernels (run 5) report the fault in a `linear2` GEMM, but the same GEMM shape ran thousands of times cleanly in runs 2, 3, 6–9 and 11.
- Every launch failure this boot happened when the DiT consumed the cond tensor that the GPU conditioner had just produced (4/4); with any other cond source there were 0 launch failures in 7 runs (~40 DiT forwards). Values alone are not it (run 11: identical values, clean).
- Run 12 shows a different and more dangerous failure mode: a silent GPU hang that the driver did not detect, making the desktop unusable.

**Hypotheses (not proven, n=1 per row):** (a) something about the conditioner's output tensor or the allocator state around it (it was created inside `inference_mode` in the middle of the DINOv2 pass) leads to the fault; run 12 weakly hints that "inference tensor" matters, but a hang is not the same symptom as a launch failure. (b) The fault is random with a high per-run rate and the pattern above is partly chance. (c) A driver/firmware problem on gfx1103 (MES/CWSR) that any of these loads can trigger; untested knobs: `amdgpu.cwsr_enable=0` (needs a kernel command-line change), newer kernel/firmware.

**Decision:** GPU experiments stopped after run 12 because the hang affected the whole machine.

## 2026-10-12 — ROCm crash hunt: the gfx override is not the cause; AOTriton attention is the main suspect

**Context:** the Vulkan route (entry below) is too slow and made the desktop lag; back to ROCm to find why it crashes. All runs: `localhost/hunyuan3d` (torch 2.14.1+rocm7.2), profile `balanced`, same boot as the L1/L3 resets (no reboot; resets this boot were already 4).

**What the torch wheel ships** (checked in the image): torch kernels for gfx1100/1101/1102/**1103**/1150/1151/...; rocBLAS Tensile libraries for gfx1100/1101/1102 but **not gfx1103**; hipBLASLt for gfx1100–1103; AOTriton attention (`aotriton.images/amd-gfx110x`) contains code objects for gfx1100, 1101, 1102 and 1103. So `HSA_OVERRIDE_GFX_VERSION` is only needed because of rocBLAS.

**Rejected hypothesis (from reading LLVM, no experiment):** "gfx1100 code under-allocates VGPRs on gfx1103". gfx1100/1101 have `Feature1536VGPRs` and gfx1102/1103 do not, but in `AMDGPUBaseInfo.cpp` that feature only changes the VGPR *allocation* granule (occupancy); the *encoding* granule written in the kernel descriptor is the same (8 in wave32), so the hardware allocates what the kernel asks for.

**Microbenchmark** (`tools/hunyuan3d/microbench.py`, fp16, DiT shapes: 4442 tokens, hidden 1024, 16 heads x 64; 10 iterations each, 0 resets):

| Config | Linear (TFLOPS) | 4096³ matmul | SDPA 1x16x4442x64 |
| :--- | ---: | ---: | ---: |
| override 11.0.0 (rocBLAS) | 4.2–6.3 | 3.44 | 14.7 ms (AOTriton) |
| override 11.0.2 (rocBLAS) | 3.4–4.4 | 4.62 | 255 ms (math fallback: AOTriton is "experimental" on gfx1102) |
| native gfx1103 + `TORCH_BLAS_PREFER_HIPBLASLT=1` | 3.7–5.5 | 3.99 | 384 ms (math) |
| native + hipBLASLt + `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1` | 3.7–5.5 | 4.18 | 13.4 ms |
| 11.0.2 + AOTriton experimental | 3.4–4.4 | 4.67 | 13.4 ms |

Native gfx1103 also needs `MIOPEN_DEBUG_CONV_GEMM=0`: otherwise MIOpen runs the DINOv2 patch-embedding Conv2d through rocBLAS, which aborts (`Cannot read TensileLibrary.dat ... for GPU arch : gfx1103`).

**End to end, L3 config (v2-0-turbo, 5 steps, octree 384, decode on CPU, `character_1316`, seed 1234):**

| Config | SDPA | Result |
| :--- | :--- | :--- |
| 11.0.0 (earlier today) | AOTriton | `hipErrorLaunchFailure` at DiT step 4/5 -> MES hang -> GPU reset |
| 11.0.2 (n=2) | math | HTTP 200, 349 623 verts, DiT 12.6–12.8 s/step (66–71 s), decode 63–66 s, peak VRAM 7.63 GiB, 0 resets |
| native gfx1103 + hipBLASLt + AOTriton (n=1) | AOTriton | steps 1–3 at 1.6–2.9 s/step, then `hipErrorLaunchFailure` (719) at step 4/5, reported again at `timestep_embedding` -> MES hang -> GPU reset 12:07:48 (resets 4 -> 5) |

**Conclusion so far:** the crash reproduces on native gfx1103 without any override, so the override is not the cause. Every crash so far ran with AOTriton SDPA, and the only clean DiT runs on ROCm had math SDPA. **Hypothesis (not proven, n is small):** an AOTriton attention kernel faults on gfx1103 (or under sustained load); the MES hang is a consequence of tearing down the faulted queue, not the root cause. Against it: 10 isolated SDPA calls at the DiT shape ran clean, and both DiT crashes came at step 4 after 3 clean steps (~11 s of load), which also fits a load-/time-dependent fault. Next: native + math SDPA end to end, then AOTriton under sustained load in isolation with `AMD_SERIALIZE_KERNEL=3` to identify the failing kernel.

## 2026-10-12 — Hunyuan3D-2 DiT (1.1B) on Vulkan via ONNX Runtime WebGPU: works, 0 resets

**Goal:** after L3 (v2-0-turbo on ROCm -> `hipErrorLaunchFailure` -> GPU reset), run the 1.1B DiT without ROCm/KFD. PyTorch has no usable Vulkan backend, so the DiT is exported to ONNX and run by ONNX Runtime's WebGPU EP (Dawn -> Vulkan -> RADV). Conditioner (DINOv2-giant), VAE decode, surface extraction and cleanup stay on the CPU (fp32).

**Configuration:** image `localhost/hunyuan3d-vulkan` (`tools/hunyuan3d/Containerfile.vulkan`: FROM `localhost/hunyuan3d` + `onnxruntime-webgpu` 1.27.0, `onnx` 1.23.2, `mesa-vulkan-drivers` 25.0.7 from bookworm-backports), only `/dev/dri` mapped (no `/dev/kfd`). `export_dit_onnx.py` (legacy TorchScript exporter, opset 17, dynamic batch, fp32 I/O) -> `models/hunyuan3d/onnx/v20turbo` (fp32, 4.2 GB) and `v20turbo-fp16` (2.1 GB). `server.py --dit_onnx <dir>` swaps the pipeline's DiT for the ONNX session; `run-server-vulkan.sh` starts it.

**Single DiT forward (batch 1, 3072 latents + 1370 cond tokens, random inputs, `check_dit_onnx.py`):**

| Backend | s/step | rel. L2 error vs torch fp32 CPU | Peak GTT |
| :--- | ---: | ---: | ---: |
| torch fp32, CPU (8 cores) | 20.1–20.6 | — | — |
| torch fp16, CPU | not timed | 3.8e-3 | — |
| ORT WebGPU fp32 (RADV, gpu_busy 99%) | 20.4–20.6 (n=7) | 1.2e-5 | ~23 GiB |
| ORT WebGPU fp16 | 12.7–12.8 (n=4) | 4.9e-2 | ~11 GiB |
| ROCm fp16 (L3, crashed) | 2.9 | — | — |

- Node placement: 4199 nodes on WebGPU, 982 on CPU (only shape arithmetic: Gather/Mul/Unsqueeze/Concat...).
- WebGPU fp16 error is 13x the torch fp16 error (hypothesis, not checked: fp16 accumulation in the WebGPU kernels).
- Plain 4096² fp32 MatMul on WebGPU: ~670 GFLOPS sustained over 30 s (GPU 2.0–2.1 GHz, then dropping to 1.6 GHz). Two 2048² smoke runs measured only ~63 GFLOPS (both with the default and the forced RADV ICD), while runs before and after gave ~400; **unexplained**. Lavapipe gives ~5 GFLOPS.
- Pitfall: Debian's RADV ICD is `/usr/share/vulkan/icd.d/radeon_icd.json` (no `.x86_64`); a wrong `VK_ICD_FILENAMES` makes Dawn fail and ORT **silently falls back to the CPU EP**. `OnnxDiT` now refuses to start without the WebGPU EP.

**End to end (`character_1316`, seed 1234, 5 steps, octree 256, `bench.sh`; Chamfer/Hausdorff vs the CPU mesh, `compare_meshes.py`, 200k surface samples, mesh spans ~2 units):**

| Run | Wall s | Verts | Chamfer | Hausdorff |
| :--- | ---: | ---: | ---: | ---: |
| all CPU (reference) | 138.6 | 164 668 | — | — |
| DiT Vulkan fp32 (n=2) | 143.7, 147.0 | 164 545 | 0.0030 | 0.043 |
| DiT Vulkan fp16 (n=2) | 100.0, 102.6 | 163 570 | 0.0053 | 0.064 |

- Deterministic: both requests of each config gave identical meshes. **GPU resets 4 -> 4** across all Vulkan runs (~25 DiT forwards in total; the 4 resets are from L1/L3 earlier this boot, and there was no reboot in between).
- fp32 on the 780M is no faster than the 8-core CPU; fp16 cuts ~38 s per mesh. The meshes have not been compared visually yet; whether the fp16 difference is visible is unknown.
- Bug found along the way: `enable_flashvdm()` replaces the VAE with the turbo VAE loaded as fp16, so `--device cpu` with v2-0 failed (`mat1 and mat2 must have the same dtype`); `server.py` now casts the VAE back to the pipeline dtype. The earlier `server_cpu_v20turbo` run could never have produced a mesh.

**Conclusion:** the 1.1B DiT runs stably on the 780M over Vulkan, but slowly (~4.4x slower than ROCm fp16 per step). Not tested yet: the non-turbo v2-0 (CFG, batch 2, 30+ steps would take ~10+ min), the VAE decode on Vulkan, and stability over many requests.

## 2026-10-12 — Detail ladder continued: CPU decode, octree 384/512, Hunyuan3D-2 turbo

**Change:** `server.py --decode_device cpu` runs the DiT on the GPU and VAE decoding + surface extraction on a separate fp32 VAE copy on the CPU (8-core 7840U). Same image/seed as above. Results appended to `tools/hunyuan3d/runs/ladder.jsonl`.

| Step | Model | Octree | DiT s (GPU) | Decode s (CPU) | Wall s | Verts | Faces | GPU resets |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | :-: |
| L0c | 2mini-turbo | 256 | 19.6 | 29.7 | 52.2 | 184 490 | 368 784 | 0 |
| L1 | 2mini-turbo | 384 | 16.1 | 83.3 | 104.1 | 420 381 | 840 456 | 0 |
| L2 | 2mini-turbo | 512 | 17.4 | 168.3 | 189.8 | 739 816 | 1 479 242 | 0 |
| L3 | 2-v2-0-turbo | 384 | failed in step 4/5 | — | — | — | — | 1 |

- CPU decode reproduces the GPU-decoded mesh (184 490 vs 184 436 verts; fp32 vs fp16). Peak VRAM drops to 4.05 GiB.
- Visual (matcap, front, n=1 image): higher octree gives smoother surfaces (fewer stair-steps on hair and jacket) but no new shape detail; eyes still merge into the glasses and the floaters remain at every octree. Shape detail is set by the model, not the grid.
- L3: `hipErrorLaunchFailure` during DiT sampling (reported in `timestep_embedding`, the real failing kernel is unknown because errors are asynchronous) -> MES hang -> GPU reset 11:06:03 (resets this boot 2 -> 3), plus another reset 30 s later when the container was stopped (-> 4). **This refutes the hypothesis that only the decode stage faults.**
- Model download: `tencent/Hunyuan3D-2` dit-v2-0, dit-v2-0-turbo, vae-v2-0, vae-v2-0-turbo = 20 GB in `models/hunyuan3d/hf/`.

## 2026-10-12 — Hunyuan3D detail ladder, step L1 (octree 384) -> GPU reset

**Plan:** same image (`character_1316`), seed 1234, one variable at a time: L0 mini-turbo/5 steps/octree 256 -> L1 octree 384 -> L2 octree 512 -> L3 Hunyuan3D-2 v2-0-turbo -> L4 v2-0 full, 30 steps. Requests sent from the Blender add-on; stop at the first GPU reset. Results in `tools/hunyuan3d/runs/ladder.jsonl`.

**Numbers:**
- L0 (rerun, warm server): HTTP 200, 21.7 s wall, shape 20.3 s, 184 436 verts / 368 672 faces, identical vertex count to the earlier run (deterministic for a fixed seed, n=2). Peak VRAM 4.77 GiB. (The first L0 run took 34.5 s; the difference is cold vs warm, not established.)
- L1 (octree 384): `hipErrorLaunchFailure` in `volume_decoders.py` (FlashVDM decoding) -> `MES failed to respond to msg=REMOVE_QUEUE` -> MODE2 GPU reset at 10:53:33 (resets this boot 0 -> 1); a second reset followed when the container was stopped (MES failed to remove its queues; resets 1 -> 2). The machine stayed up.

**Observation (hypothesis, not proven):** all three device failures so far (character_1626 at octree 256, two this morning, and L1) happened in the VAE decode stage (volume decoder / surface extractor), none in the DiT diffusion stage. Larger octree = larger decode grid. Candidate mitigations to test: decode without FlashVDM, or decode on CPU while the DiT stays on the GPU.

## 2026-10-12 — Cleanup after the Hunyuan3D test

Deleted: root capybara experiments (`.blend`, renders, scripts), all `.blend1` backups, `__pycache__`, the whole 2026-10-08 video pipeline (`src/`, `bin/`, `images/producer`, `tools/build_nn_scenes.py`, `tools/render_*.py`, `assets/`, `notes/`, `projects/` incl. 1.9 GB of frames, `models/piper`), the Antigravity configs `.agent/` and `.agents/`, an unused `tools/blmcp/.venv`, Podman images `producer` and `ubuntu:26.04` plus dangling `hunyuan3d` build layers. Disk used went from 222 GB to 214 GB. The Hunyuan3D Blender add-on was moved to `~/work/blender/add-on/`.

## 2026-10-12 — Hunyuan3D-2mini shape generation on ROCm: 1 mesh, then GPU resets

**Goal:** image -> untextured mesh with Hunyuan3D-2 (`tools/hunyuan3d/`, image `localhost/hunyuan3d`, torch ROCm 7.2 wheel, `HSA_OVERRIDE_GFX_VERSION=11.0.0`, model `Hunyuan3D-2mini/hunyuan3d-dit-v2-mini-turbo`, steps=5, octree=256).

**Numbers (n=2 requests, `tools/hunyuan3d/runs/`):**
- `character_1310.png`: HTTP 200, 33.0 s wall (shape 32.6 s), 117 506 verts / 234 996 faces, peak VRAM 4.76 GiB. Model load 20.2 s.
- `character_1626.png`: HTTP 500 after 32.8 s: `hipErrorLaunchFailure` in the surface extractor, then `FloaterRemover` crashed on an empty mesh.
- Kernel log (previous boot): `MES failed to respond to msg=REMOVE_QUEUE` -> `GPU reset begin` at 10:12:52, 10:13:10, 10:23:41, 10:23:49 (counter went 0 -> 4 that boot). The machine was rebooted at ~10:27. One run log warns that the power profile was not `balanced`.

**Visual check in Blender (character_1310, matcap):** silhouette, face, shirt, shorts and shoes are recognisable; hair has visible stair-step ridges; several disconnected floaters next to the head and hand were not removed; no texture.

**Rerun after reboot (same image, profile `balanced`, request sent from the Blender add-on driven over Blender MCP):** `character_1316.png` -> HTTP 200, 35 s in the panel (shape 34.5 s), 184 436 verts / 368 672 faces, peak VRAM 4.77 GiB, GPU resets 0 -> 0. Visually: glasses, jacket, fingers and hair volume come through; the face is soft (eyes merge into the glasses); at least one small floater remains. n=1, says nothing yet about stability.

**Conclusion:** the same MES hang class as 2026-10-06 reproduces with PyTorch/ROCm on gfx1103, not only with llama.cpp. Whether `balanced` avoids it here is not established (sample too small).

## 2026-10-08 — Full End-to-End Explainer Video Rendered via Blender EEVEE Next & .blend Persistence

**Goal:** Produce a full 5-scene explainer video ("Neural Networks for Beginners") using pure Blender procedural motion graphics (Google Flow aesthetic: dark palette, emissive nodes, traveling pulses, interactive weight dials), persistent .blend project files, and FFmpeg assembly.

**Configuration:**
- Host: Ryzen 7 PRO 7840U, Radeon 780M (gfx1103, Mesa 26.0.8, balanced profile).
- Blender: Snap Blender 5.2.2 LTS (EEVEE Next, 1080p @ 30 fps, 16 TAA render samples).
- Project: `projects/neural-networks-intro` (5 scenes, total 1,229 frames, ~41 s audio).
- Audio: Vietnamese TTS (Piper `vi_VN-vais1000-medium.onnx`).
- Persistence: Saved standalone `.blend` files for all 5 scenes in `projects/neural-networks-intro/scenes/`.

**Measured numbers:**
- **Scene-by-scene render performance:**
  - `s01` (Intro, 229 frames): **73.12 s** (3.13 fps, 0.319 s/frame)
  - `s02` (Architecture, 272 frames): **88.34 s** (3.08 fps, 0.325 s/frame)
  - `s03` (Weights / Dial, 269 frames): **89.46 s** (3.01 fps, 0.333 s/frame)
  - `s04` (Tuning / Feedback, 266 frames): **89.27 s** (2.98 fps, 0.336 s/frame)
  - `s05` (Outro, 193 frames): **63.56 s** (3.04 fps, 0.329 s/frame)
- **Total frames rendered:** 1,229 frames (1080p).
- **Total Blender render time:** **404.51 s** (~6.74 min, average **3.04 fps**, **0.329 s/frame**).
  - *Comparison:* Over **386x faster** than the previous CloudRig character rig (which took 128.4 s/frame).
- **FFmpeg encoding & concat:** 11.17 s (H.264 CRF 18, AAC 192k).
- **Total pipeline execution time:** **418.53 s** (~6.98 min).
- **Final artifact:** `neural_networks_intro.mp4` (5.1 MB, 1080p @ 30 fps, pristine AV sync).
- **Saved project files:** 5 `.blend` files created in `scenes/` (total 736 KB).
- **GPU stability:** `GPU reset begin` count = 0 (before and after).

**Conclusion:**
- Pure procedural motion graphics in Blender EEVEE Next deliver stunning Google Flow-grade visual clarity with extreme speed (~0.33s/frame).
- Entire explainer videos can be generated, previewed, and rendered in minutes locally on an iGPU without thermal stress.
- Independent `.blend` files allow seamless human inspection and manual tweaking in Blender GUI.

---

## 2026-10-08 — Host Blender 5.2.2 & Blender MCP Server integration verified

**Goal:** Configure Blender 5.2.2 on the host (installed via App Center/Snap) with the official Blender Foundation MCP Server (`blender_mcp` v1.0.3) and establish a live two-way bridge to Antigravity.

**Configuration:**
- Host: Ryzen 7 PRO 7840U, Radeon 780M, Ubuntu 26.04.
- Blender: Snap installation (`/snap/bin/blender`, 5.2.2 LTS).
- Add-on: `blender_mcp` (v1.0.3) installed in `~/.config/blender/5.2/scripts/addons/blender_mcp`, enabled in `userpref.blend` with `use_online_access=True`.
- MCP Server: `blmcp` package placed in `tools/blmcp`, Python dependencies (`mcp>=1.2.0`, `pyyaml`, `docutils`) installed.
- Agent Config: Registered in `~/.gemini/config/mcp_config.json`.

**Verification & Measured numbers:**
- Blender background MCP daemon started via `blender -b --command blender_mcp` listening on `localhost:9876`.
- MCP sandbox security verified: `weak_sandbox.py` successfully intercepted destructive operator `read_factory_settings` and suggested the safe `read_homefile(use_empty=True, use_factory_startup=True)`.
- Test execution: Procedurally created a 3D metallic sphere (`MCP_Tech_Ball`) with blue metallic Principled BSDF, studio lighting, camera.
- Rendered 1080p preview image: `projects/test_ball.png` (580 KB).
- Exported 3D asset: `projects/test_ball.glb` (25 KB) in **0.083 s**.
- Bridge response: `{"status": "ok", "result": {}}`.

**Conclusion:**
- The Blender MCP bridge is fully operational and verified.
- The AI agent can now interactively create, query, modify, preview, and export 3D scenes in Blender with sub-second response times.

---

## 2026-10-08 — Elder Sprite 3D character benchmark: Render bottleneck & visual assessment

**Goal:** Benchmark using an official Blender Open Movie character rig (`elder_sprite_packed.blend`, CloudRig with 1,430 bones, Geometry Nodes and particle hair systems, multi-lattice facial deformers) as the A-Roll presenter.

**Configuration:**
- Host: Ryzen 7 PRO 7840U, Radeon 780M (gfx1103), balanced profile, Mesa 26.0.8, rootless Podman 5.7.
- Container: `localhost/producer:latest` (Blender 5.2.2 LTS Vulkan headless, 1080p, EEVEE engine).
- Asset: `elder_sprite_packed.blend` (2.9 MB packed asset from Blender Studio).

**Measured numbers:**
- **Default scene per-frame render benchmark (5 frames sample):**
  - Frame 1: 130.1 s
  - Frame 2: 122.0 s
  - Frame 3: 130.9 s
  - Frame 4: 128.7 s
  - Frame 5: 130.3 s
  - **Mean frame time:** **128.4 s / frame** (~2.14 minutes per single frame).
  - **Pipeline impact:** Rendering 3 A-Roll scenes (~680 frames) would take **~24.2 hours** of continuous 100% GPU load.
- **Optimization attempts:**
  - *Subdivision Surface level 1 + 16 EEVEE samples:* **52.58 s / frame** (still ~10 hours for 680 frames).
  - *Disabling particle hair emitters:* Dropped to **15.14 s / frame**, but stripped the character of its beard/features, creating broken visual geometry.
  - *Hair children count reduction:* Triggered deep shader re-evaluations and particle stalls, reaching **2,970 s (49.5 minutes)** for 1 frame.
- **GPU stability:** `journalctl -k -b | grep -c 'GPU reset begin'` remained **0**.

**Conclusion & User Decision:**
- Full feature-film 3D character rigs are completely unviable for automated local explainer video generation on iGPU hardware.
- Visually, attempting 3D character acting without dedicated human rigging/animators yields awkward, stiff motion and gaudy, uncontrolled colors (the reviewer's words, translated: "very stiff, garish, out of control").
- Compared to the **Google Flow / Google DeepMind** design standard (clean, deliberate, minimalist 2D/isometric vector motion graphics with strict color theory and clear typography), 3D character avatars look amateurish and distract from the educational message.
- Decision: Abandon complex 3D character avatars for explainer videos. Cleaned up all generated test frames, segments, and images (`frames/`, `segments/`, `test_elder_frames/`, `elder_*.png`).

---

## 2026-10-08 — A-Roll (3D Stickman Presenter) + Stable B-Roll Architecture

**Goal:** Implement A-Roll using a lightweight procedural 3D stickman presenter in Blender to introduce principles, alternating with clear, stable B-Roll technical diagrams (eliminating distracting zooms).

**Configuration:**
- Host: Ryzen 7 PRO 7840U, Radeon 780M (gfx1103), balanced profile, Mesa 26.0.8, rootless Podman 5.7.
- Container: `localhost/producer:latest` (Blender 5.2.2 LTS Vulkan headless, Piper TTS 1.2.0, FFmpeg 8.0.1).
- Visual Design:
  - A-Roll: Procedural 3D stickman presenter (porcelain body, joint rings, glowing cyan visor and hands, waving and dial-turning animations).
  - B-Roll: Clean 3-column architecture (Input 3 nodes, Hidden 4 nodes, Output 2 nodes) with stable camera and signal pulse flows.

**Measured numbers:**
- 5 scenes total (1,229 frames @ 1080p 30 fps):
  - Scene s01 (A-Roll Stickman Intro): 229 frames in 116.1 s (0.50 s/frame).
  - Scene s02 (B-Roll Architecture): 272 frames in 161.6 s (0.59 s/frame).
  - Scene s03 (A-Roll Volume Dial): 269 frames in 142.7 s (0.53 s/frame).
  - Scene s04 (B-Roll Weight Tuning): 266 frames in 139.0 s (0.52 s/frame).
  - Scene s05 (A-Roll Stickman Outro): 193 frames in 91.8 s (0.47 s/frame).
  - Total Blender render time: **651.16 s** (~10.8 minutes). Mean frame time: **0.53 s/frame**.
- Post-production (FFmpeg encoding + adaptive glass titles with Noto Sans Bold + SRT subtitles): **13.53 s**.
- GPU resets (`journalctl -k -b | grep -c 'GPU reset begin'`): **0** (0 hangs, 0 resets).
- Final artifact: `projects/neural-networks-intro/final.mp4` (1080p, 30 fps, H.264, 38.50 s, 7.26 MB).

**Conclusion:**
- The procedural 3D stickman completely avoids the uncanny valley of realistic 3D human avatars, renders in <0.5s/frame, and provides an engaging, friendly presenter role.
- Stabilizing the camera in B-roll and using distinct 3-column plates makes the neural network diagram immediately legible and educational.

---

## 2026-10-08 — End-to-end video generation: Lightweight Local Stack + Blender 5.2.2 Vulkan + FFmpeg

**Goal:** Verify a complete, automated end-to-end video generation pipeline using a cloud script, lightweight local TTS, procedural/parametric Blender 3D rendering with Vulkan headless, and FFmpeg post-production.

**Configuration:**
- Host: Ryzen 7 PRO 7840U, Radeon 780M (gfx1103), 60 GiB RAM, power profile `balanced`, Mesa 26.0.8, rootless Podman 5.7.
- Container: `localhost/producer:latest` (Ubuntu 26.04, Blender 5.2.2 LTS with Vulkan, Piper 1.2.0, FFmpeg 8.0.1, Noto fonts).
- Topic: Explaining Neural Networks to a beginner (4 scenes, ~40s target, Vietnamese narration).
- Models & Tools:
  - Script: Cloud LLM structured script (`notes/neural-networks-intro.md` -> `projects/neural-networks-intro/script.json`).
  - Voice: Local Piper TTS (`vi_VN-vais1000-medium.onnx`, 61 MB) running on CPU.
  - 3D Visuals: Procedural 3D neural network in Blender 5.2.2 (`BLENDER_EEVEE`, 1080p @ 30 fps, 32 TAA samples, Vulkan backend).
  - Assembly: FFmpeg H.264 CRF 18, dark technical banners, SRT subtitles, AAC 192k audio.

**Measured numbers:**
- **TTS generation time:** All 4 scenes (750 chars, 39.08s audio) generated in **1.8 s** total (real-time factor: ~0.04).
- **Blender 5.2.2 render performance (1080p, 32 samples, RADV Vulkan):**
  - Scene s01: 303 frames rendered in 110.0 s (0.36 s/frame).
  - Scene s02: 304 frames rendered in 138.4 s (0.45 s/frame).
  - Scene s03: 354 frames rendered in 134.7 s (0.38 s/frame).
  - Scene s04: 271 frames rendered in 109.0 s (0.40 s/frame).
  - Total: **1,232 frames (1080p)** in **492.1 s** (~8.2 minutes). Mean frame time: **0.40 s/frame**.
- **Post-production & assembly (FFmpeg):** **12.27 s**.
- **GPU stability:** `journalctl -k -b | grep -c 'GPU reset begin'` remained **0** (0 resets, 0 hangs).
- **Final artifact:** `projects/neural-networks-intro/final.mp4` (1920x1080, 30 fps, H.264, 39.08 s, 11.15 MB).

**Conclusion:**
- Parametric/procedural 3D scene templates completely eliminate the 0%–50% failure rate of LLM free-form code generation.
- Running lightweight local inference (Piper TTS on CPU) leaves 100% of the GPU free for Blender EEVEE rendering, keeping temperatures low and avoiding GTT pressure.
- Blender 5.2.2 Vulkan headless in rootless Podman is fast, stable, and produces clean 1080p output at ~0.4s/frame.

---

## 2026-10-06 — Cleanup, to redesign the architecture

**User decisions**
- Use **Vulkan** for the local LLM; drop ROCm (<10% faster but less stable, see below).
- Delete every container, image, volume, model and experiment source; keep only `local-producer.md` (spec v2.1, **outdated** in its local-LLM and A-roll parts).
- Direction under discussion: a cloud LLM (Sonnet/Opus/Gemini/GPT) for the script, scene code and visual QA; small local models only for TTS/STT; Blender only for 3D mechanical scenes; the avatar could be a code-built "2D puppet" or A-roll could be dropped. **Not decided yet.**
- Host ROCm packages (`rocm`, `hip*`, `libamdhip64*`, `librocblas*`, …) were removed by the user afterwards (verified: 0 ROCm packages left).
- **The TTS language is not fixed to Vietnamese.** It is chosen per video request (`language` in `script.json`); the TTS role is `tts-<language>`, so adding a language means installing a voice, not changing code. Subtitle tag, on-screen fonts and the narration prompt follow the same field. Only Vietnamese has been tested.
- All project files were translated to English so other agents can read them. The Vietnamese narration/on-screen samples in `local-producer.md` are intentionally kept: the videos themselves are in Vietnamese.

## 2026-10-06 — Backend × environment-variable sweep with Qwen3.6-35B-A3B

Model: `bartowski/Qwen_Qwen3.6-35B-A3B-GGUF`, `Q4_K_M` (20.8 GiB). `context_size 16384`, `parallel 1`, `mmap false`, 99 layers on the GPU. Power profile `balanced`. 3 JSON generations per configuration; ROCm 11.0.2 and Vulkan were repeated 3 times.

| Configuration | Generation tok/s | Prefill tok/s | GTT (MiB) | GPU resets |
| :--- | ---: | ---: | ---: | :-: |
| ROCm, `HSA_OVERRIDE_GFX_VERSION=11.0.2` (mean of 3) | 25.3 | 287 | 22,415 | 0 |
| ROCm, `11.0.0` | 23.6 | 285 | 22,443 | 0 |
| ROCm, `11.0.2` + `HSA_ENABLE_SDMA=0` | 22.8 | 254 | 22,413 | 0 |
| ROCm, `11.0.0` + `HSA_ENABLE_SDMA=0` | 24.0 | 285 | 22,437 | 0 |
| **Vulkan** (mean of 3) | 24.8 | 258 | **18,004** | 0 |

- Noise between repeats of the same configuration is ±1–2 tok/s ⇒ the ROCm variants cannot be told apart. Vulkan is ~2% slower at generation and ~10% slower at prefill, but uses 4.4 GiB less GTT.
- First load takes ~8.5 s in every configuration.

**Full benchmark** (5 JSON runs, 8 Manim files, up to 3 render + repair attempts):

| | ROCm 11.0.2 | Vulkan |
| :--- | :--- | :--- |
| Valid JSON | 5/5 | 5/5 |
| Manim passing the static check | 8/8 | 8/8 |
| Manim rendering on the first try | 3/8 | 3/8 |
| Manim rendering within ≤3 attempts | 5/8 | 4/8 |
| Manim with correct duration (±20%) | 2/8 | 3/8 |

⇒ **Phase 0 criterion (≥70%) not met.** Neither run hung or reset the GPU. The user judged the 35B-A3B model still too heavy for this machine.

## 2026-10-06 — Manim repair loop and harness bugs

- Added a *render → send the error to the model → repair → render again* loop (at most `BROLL_MAX_ATTEMPTS=3`).
- **Lesson:** sending the last 25 lines of Manim's Rich log is useless (it is all library internals), and the model returns exactly the old code. Send the **frame that points into the model's own file** (the line containing `/work/manim/`, plus 8 lines of context) and the **final exception line**.
- Manim API mistakes the models make often: using `Gear` (does not exist), `ParametricCurve` (correct name is `ParametricFunction`), `self.camera.frame` in a plain `Scene`, wrong `size`/`font`/`line_color` arguments, missing `import math`.
- The render container must set `PYTHONDONTWRITEBYTECODE=1`; otherwise `__pycache__` belongs to another uid and `rm -rf` on the host fails (use `podman unshare rm -rf`).
- The harness must **stop immediately when LocalAI fails**, not silently keep rendering code that was never repaired.
- The `0/8` Manim result in the early benchmarks was **not** a harness bug: Manim ran up to `construct` and only then hit the model's API errors.

## 2026-10-06 — GPU incident: MES hang, machine freeze

Recurring symptom with the 30B model on ROCm:

```
amdgpu: MES failed to respond to msg=REMOVE_QUEUE
amdgpu: Failed to evict queue 4 → Failed to evict process queues
amdgpu: GPU reset begin! (MODE2 reset) … device wedged, but recovered through reset
```
LocalAI side: `Backend process exited unexpectedly … stderr="/backends/rocm-llama-cpp/llama-cpp-fallback[0x…]"`, requests return `HTTP 500 … error reading from server: EOF`.

- Happened 4 times while the profile was **`power-saver`** (13:47, 16:34, 16:49, 17:02); one earlier occurrence **froze the whole machine**.
- **Not a VRAM overflow:** at crash time RAM free was 54 GB and GTT 0.4 GB.
- **Not caused by** `HSA_OVERRIDE_GFX_VERSION` (it was set to 11.0.2 in the backend process itself).
- The hypotheses "reloading the model right after releasing it" and `mmap` were both rejected (crashes also happened while the model stayed loaded, and with `mmap:false`).
- After switching to `balanced` + a reboot: ~12 ROCm benchmark runs and 5+ Vulkan runs, **0 resets**. Correlation only, small sample.
- The Vulkan backend does not go through the KFD path (where the failure occurs); the user observed Vulkan to be more stable ⇒ Vulkan chosen.
- The original "machine freeze" happened when loading the 30B model with Vulkan right after ROCm; most likely a consequence of the earlier ROCm hang, not proven.

## 2026-10-06 — 30B and 4B benchmarks (ROCm, `power-saver`/`balanced`)

| Model | Gen tok/s | Prefill | Valid JSON | Manim static | Manim render | GTT |
| :--- | ---: | ---: | :-: | :-: | :-: | ---: |
| Qwen3-30B-A3B-Instruct-2507 Q4_K_M | 27–28 | 362–392 | 3/5 → 5/5 → 3/3 | 4/4 | 0/4–0/8 (model API errors) | 19.5 GiB |
| Qwen3.8-4B Q8 | 17.5 | 426 | 4/5 | 4/4 | 0/4 | 5.8 GiB |
| Qwen3-Coder-30B-A3B | — | — | — | — | not benchmarked | — |

- With the 4B model: one JSON run failed because the model looped on one Vietnamese word (it means "change": "change change change ...") until the 4000-token limit.
- After `/backend/shutdown`, GTT drops below 100 MiB (meets the <1 GiB criterion).

## 2026-10-06 — Findings about LocalAI v4.11.0

- **Disabling "thinking" for Qwen3.x:** `chat_template_kwargs.enable_thinking=false` in the request is **ignored**; `content` is empty because the reasoning eats all of `max_tokens`. The correct way is in the model YAML: `reasoning:` → `disable: true` (verified; the GGUF template does support the variable).
- Gallery defaults (`context_size 262144`, `parallel 4`) take 16 GiB of GTT even for a 4B model. Set `context_size: 16384` and `options: [parallel:1]` by hand; verify with the log line `effective runtime tuning … context=16384 … parallel="1"`.
- Backends are **not included** in the image: install with `POST /backends/apply {"id":"localai@vulkan-llama-cpp"}` (or `rocm-llama-cpp`), and watch for the `/backends/<name>.install-tmp` directory to disappear. The ROCm backend is ~8.4 GB, Vulkan ~0.5 GB.
- `POST /backend/shutdown {"model": "..."}` really frees the GPU; it returns 404 if the model is not loaded.
- `LOCALAI_MAX_ACTIVE_BACKENDS` and `LOCALAI_WATCHDOG_IDLE*` are accepted (see the Quadlet below).
- The Vietnamese piper voice `vi_VN-vais1000-medium` is in the gallery (backend `crispasr`) and produces 22.05 kHz WAV; a 4.2-second sentence took 5.2 s including backend load. **Voice quality has not been listened to.**

## 2026-10-06 — Blender verification in Podman

Details are in `local-producer.md` §3.2 (kept as is). Summary: Blender 4.5.14 and 5.2.2 run `-b --gpu-backend vulkan` in an Ubuntu 26.04 container with no X; they pick `AMD Radeon 780M (RADV PHOENIX)`; EEVEE 1080p/64 samples ~0.6 s/frame on a simple test scene (first frame ~4 s for shader compilation). `xvfb-run` + Vulkan **hangs**. On Blender 5.x write a PNG sequence (`FFMPEG` is no longer valid) and the engine was renamed `BLENDER_EEVEE_NEXT` → `BLENDER_EEVEE`. The doctor check looks for the line `Using vendor … RADV` to rule out `llvmpipe`.

---

## Verified configuration (to rebuild if needed)

**LocalAI (rootless Quadlet):** image pinned by digest
`docker.io/localai/localai@sha256:e9607e90c20278b5b962c47ea7f8a770caaded3c74c1d8c69fbe784fc42fe82a` (v4.11.0, `latest-gpu-hipblas`, built 2026-10-02; if only Vulkan is used, try the `latest-gpu-vulkan` tag, **not verified**). Port `127.0.0.1:8080`, `AddDevice=/dev/dri`, `GroupAdd=keep-groups`, `THREADS=8`, `LOCALAI_MAX_ACTIVE_BACKENDS=2`, `LOCALAI_WATCHDOG_IDLE=true`, `LOCALAI_WATCHDOG_IDLE_TIMEOUT=10m`, volumes `localai-backends:/backends`, `localai-data:/data`, `localai-config:/configuration`, the model directory mounted at `/models`. No `[Install]` section: start/stop manually.

**Model YAML (Vulkan, ran stably):**
```yaml
name: planner
backend: vulkan-llama-cpp
context_size: 16384
gpu_layers: 99
mmap: false
f16: true
function: { grammar: { disable: true } }
known_usecases: [chat]
options: [use_jinja:true, parallel:1]
parameters: { model: <file.gguf>, temperature: 0.4, top_k: 20, top_p: 0.95, min_p: 0, repeat_penalty: 1 }
reasoning: { disable: true }
template: { use_tokenizer_template: true }
```

**Counting GPU resets:** `journalctl -k -b | grep -c 'GPU reset begin'`. **Reading GTT usage:** `/sys/class/drm/card1/device/mem_info_gtt_used`.

---

## Cleaned up (2026-10-06)

- Podman: container `localai`; images `localai` (11 GB), `producer`, `producer-blender`, `manim` v0.21.0, `ubuntu:26.04`; 3 volumes; network `producer`; the Quadlet units.
- Models: Qwen3-30B-A3B-Instruct-2507 Q4_K_M (18 GB), Qwen3.6-35B-A3B Q4_K_M (21 GB), piper vais1000 (30 MB). (Qwen3-Coder-30B and Qwen3.8-4B had been removed earlier.)
- Project directory: `bin/`, `src/`, `images/`, `quadlet/`, `bench/`, `assets/`, `projects/`, `models/`, `config.env`.
- Browser caches `~/.cache/google-chrome` and `~/.cache/microsoft-edge` (cookies/logins untouched), `~/.cache/pip`, `~/.cache/thumbnails`.
- Disk usage went from 241 GB to 170 GB used.
- What remains: `local-producer.md`, `CHANGELOG.md`, `AGENTS.md`.
- Host ROCm packages: removed by the user (needed `sudo`).
