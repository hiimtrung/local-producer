# LOCAL PRODUCER — SPEC PROPOSAL v3: GATED, TEMPLATE-DRIVEN PIPELINE

| | |
| :--- | :--- |
| **Status** | **Proposal, written to be compared later with other proposals.** Nothing here has been built or measured unless stated. It does not replace `local-producer.md` (v2.1, legacy). |
| **Date** | 2026-10-07 |
| **Basis** | Measurements in `CHANGELOG.md` (local 35B-A3B: first-try Manim render 3/8, ≤3 attempts 4–5/8, duration within ±20% only 2–3/8; GPU instability on ROCm). |
| **Machine** | Ryzen 7 PRO 7840U, Radeon 780M, 60 GiB RAM, rootless Podman. |

Language note: the video language is chosen per request (`language` in `script.json`). Vietnamese is the only language tested so far.

---

## 1. PROBLEM THIS PROPOSAL ADDRESSES

Picking a model by benchmarking many candidates does not scale (there are hundreds of thousands of models) and the measured result was poor anyway. This proposal moves quality out of the model and into (a) fixed, tested building blocks and (b) automatic gates, so that the system works with a limited machine and does not depend on a strong LLM.

## 2. CORE PRINCIPLES

1. **The LLM emits structured data, not free-form code.** It selects a scene type from a tested library and fills in parameters (e.g. tooth counts, rotation direction, labels). The renderer is our own deterministic code. A weaker model only means more retries; the output contract does not change.
2. **Every component sits behind a narrow interface with a contract test.** Changing a model is a config change. Each role (LLM, TTS, STT) has a small golden set (about 10 cases, **proposed size**) and a pass threshold. At most 3 candidates are tried per role, pre-filtered by licence and by fitting in 60 GiB RAM.
3. **One style contract for the whole video:** palette, fonts, layout grid, safe areas, motion speed, loudness target. Scenes fit together because they share the contract, not because a model happened to be consistent.
4. **Every step writes a schema-validated artifact with an input hash and must pass a gate before the next step runs.** Re-running re-renders only scenes whose inputs changed. When a gate fails, the run stops; it never continues with stale results.

## 3. PIPELINE AND GATES

| # | Step | Artifact | Gate |
| :-: | :--- | :--- | :--- |
| 1 | Fact sheet | Claims extracted from the note, each with its source span | Every number in a claim appears in the note |
| 2 | Outline + script | `script.json` | Schema; each narration sentence maps to a claim (grounding); per-scene length limits; pronunciation lexicon applied. **Human review** |
| 3 | TTS | `audio/*.wav`, `timing.json` | Round-trip with local Whisper: WER of the audio vs the narration under a threshold; loudness, silence and duration checks |
| 4 | Visual spec | Per-scene DSL (type, params, cue times aligned to narration) | Schema; scene type exists in the library; params inside valid ranges; total duration matches `timing.json` |
| 5 | Render | `broll/<id>.mp4` | Exit code; duration within tolerance; frames not blank/black; no text overflow or overlap (bounding-box check inside the scene code, no VLM); colours within the palette |
| 6 | Visual QA | Report | A VLM scores a few sampled frames against a rubric. **Advisory only, does not block**, because VLM judgement is unreliable |
| 7 | Assemble | `final.mp4`, `final.srt` | A/V sync; subtitle coverage; loudness; join points. **Human previews the result** |

Thresholds are **not yet chosen**; they must be set from measured pass rates on real videos.

## 4. STACK

| Layer | Choice | Notes |
| :--- | :--- | :--- |
| Orchestrator | Plain Python, file-based state, hash-keyed cache, Podman jobs | No agent framework: the flow is a fixed DAG |
| LLM | Cloud, behind one thin adapter using structured output | Strong model for the script, cheaper model for filling the DSL. Retries carry the validation error text, not library internals |
| 2D visuals | Manim CE with a scene-type library (gears, graphs, block diagrams, equations, comparisons) | The largest body of work |
| 3D visuals | Blender, **later phase**, parametric templates only | No LLM-written `bpy` |
| TTS | Local, behind an interface | Candidates from `local-producer.md` §7.4; **not yet listened to** |
| STT | Local Whisper | Used by gate 3 and for subtitle alignment |
| Assemble | FFmpeg as in `local-producer.md` §8.5 | Still valid |
| A-roll | **Dropped from the MVP**; a 2D puppet may come later | |
| LocalAI | Not required (no local LLM). TTS/Whisper can run directly in containers | Simpler and lighter |

Local LLM is not used (see `AGENTS.md`); `power-saver` / ROCm issues no longer apply to the main path.

## 5. PROS

- Quality lives in the scene library and gates, so a cheaper or different model does not collapse the result.
- Failures are caught early and localised; every step can be re-run on its own.
- Cloud cost should be small and predictable (short JSON outputs rather than long code plus repair loops). **Hypothesis, not measured.**
- The remaining local workload is light and does not depend on the iGPU.

## 6. CONS AND RISKS

- **High up-front cost:** the scene library must be written and tested by us. Every new kind of illustration is code work; the LLM cannot fill the gap.
- **Reduced freedom:** content outside the library gets no visual. An escape hatch (free-form Manim) is possible but needs a stricter gate and should only be used when unavoidable.
- **No longer fully offline:** note content goes to a cloud LLM. Privacy handling for sensitive notes is an open decision.
- **Vietnamese TTS quality is unknown.** This is the largest remaining risk; the Whisper gate measures correctness, not naturalness.
- Gates can be wrong in both directions (blocking good output, passing bad output); thresholds need tuning on real data.
- Manim suits maths and basic engineering; it is weak for photographic or 3D content.

## 7. PROPOSED ORDER OF WORK

1. Listen to 3 TTS candidates in Vietnamese and build the Whisper round-trip gate. If no voice is acceptable, stop and rethink.
2. Core: schemas, style contract, orchestrator, gates 1–3 and 7.
3. 3–5 scene types plus the render gate; produce one real video from one note.
4. Measure the pass rate of each gate on 3–5 videos, then tune thresholds and decide whether to widen the library.

## 8. OPEN DECISIONS

| # | Question | Recommended default |
| :-: | :--- | :--- |
| 1 | Accept sending note content to a cloud LLM? | Yes, with filtering for sensitive notes |
| 2 | Drop A-roll from the MVP? | Yes |
| 3 | Library-only visuals, or also a free-form code escape hatch? | Library first; add the escape hatch after measurements |
| 4 | Which cloud LLM(s) and which TTS voice? | Decide by the golden-set contract test (§2.2), not by open-ended benchmarking |
