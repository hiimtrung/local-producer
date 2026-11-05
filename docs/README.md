# Documentation

| | |
| :--- | :--- |
| **Status** | Active — index of the documentation tree; pages marked *planned* do not exist yet |
| **Owner** | maintainer (`@hiimtrung`) |
| **Last verified** | 2026-11-05 |
| **Applies to** | the whole repository |

This tree follows the Diátaxis split — **architecture** explains why, **operations** tells you how to do a task,
**development** teaches, **reference** lists exact values — plus two layers this project needs: **decisions** (ADRs)
and **analysis** (dated measurement reports). Start with the question you have, not with the first file.

## Start here

| If you want to… | Read |
| :--- | :--- |
| understand what the project is and what works today | [`README.md`](../README.md) |
| know the rules for changing the repository | [`AGENTS.md`](../AGENTS.md), [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
| find where data, weights and logs are stored | [`reference/storage.md`](./reference/storage.md) |
| know why there are no containers, and why a Tauri shell | [`adr/`](./adr/README.md) |
| see the measurements behind a decision | the two [analysis](./analysis/2026-11-desktop-architecture.md) studies and [`CHANGELOG.md`](../CHANGELOG.md) |
| know what is being built next, with acceptance criteria | [`plans/`](./plans/README.md) |
| read a superseded spec for its reasoning | [`archive/`](./archive/local-producer-v2.1.md) |

## Layers

| Layer | Answers | Directory | State |
| :--- | :--- | :--- | :--- |
| Architecture | "why is it built this way?" | `architecture/` | planned — lands with P1 |
| Operations | "how do I install / run / fix it?" | `operations/` | planned — parts land with P1, the rest with P5 |
| Development | "how do I work on it?" | `development/` | planned — lands with P1 |
| Reference | "what are the exact paths, fields, endpoints?" | `reference/` | [`storage.md`](./reference/storage.md) exists; the rest lands with P1 |
| Decisions | "why this and not that?" | [`adr/`](./adr/README.md) | ADR 0001–0006 exist |
| Analysis | dated studies, not contracts | `analysis/` | two studies exist |
| Plans | "what is being built now, and how do we know it is done?" | [`plans/`](./plans/README.md) | P1 is ready for execution |
| Archive | superseded documents, kept for their reasoning | `archive/` | two files, both marked Superseded |

### Studies

- [`analysis/2026-11-desktop-architecture.md`](./analysis/2026-11-desktop-architecture.md) — one runtime contract,
  native on both platforms, shipped as a Tauri app; phases and acceptance criteria.
- [`analysis/2026-11-performance-bottlenecks.md`](./analysis/2026-11-performance-bottlenecks.md) — ranked GPU and UI
  bottlenecks with the measurements behind them.

### Plans

- [`plans/2026-11-p1-native-runtime.md`](./plans/2026-11-p1-native-runtime.md) — P1: supervisor, `lp`, locks, container
  removal, CI on both OSes, with the acceptance checklist. This is the file to hand to the executing agent.

### Archive

- [`archive/local-producer-v2.1.md`](./archive/local-producer-v2.1.md) — the v2.1 specification; superseded, kept
  for its measured Blender/ROCm facts.
- [`archive/spec-v3-gated-pipeline.md`](./archive/spec-v3-gated-pipeline.md) — a gated, template-driven pipeline
  proposal; never adopted.

### Planned pages

Listed so that new work has a canonical home; they are **not links**, because the files do not exist yet.

- `architecture/`: `overview`, `runtime-contract`, `engines`, `pipelines`, `data-model`, `security-model`
- `operations/`: `install-desktop`, `run-headless`, `troubleshooting`, `backup-and-migrate`, `release-runbook`
- `development/`: `setup`, `testing`, `adding-a-pipeline`, `adding-a-page`
- `reference/`: `api`, `configuration`, `catalog`, `glossary`

The target layout, the page standard and the migration order are described in
[`analysis/2026-11-desktop-architecture.md`](./analysis/2026-11-desktop-architecture.md) and its companion
[`analysis/2026-11-performance-bottlenecks.md`](./analysis/2026-11-performance-bottlenecks.md); the decisions already
taken are in the [ADR index](./adr/README.md).

## Owners

One owner per layer. Ownership means "review changes and keep `Last verified` honest", not "write everything".

| Area | Owner |
| :--- | :--- |
| Architecture, decisions (ADRs) | maintainer |
| Operations (install, run, release) | maintainer |
| Development and reference | maintainer |
| Analysis and `CHANGELOG.md` | whoever ran the experiment, with the maintainer as reviewer |

## Rules for a page

The full standard is in the ADR index and enforced by `scripts/check_docs.py` (`make docs-check`). In short:

1. Every page starts with the header table: `Status`, `Owner`, `Last verified`, `Applies to` when it matters.
2. One canonical page per topic; other documents link to it instead of restating it.
3. No number without a source — measurements cite the `CHANGELOG.md` entry.
4. `Last verified` changes when the content is checked against the code, not when a typo is fixed.
5. Superseded pages are kept with a banner and a link to what replaced them; code is still deleted, not archived.
6. kebab-case file names, one `H1` per file, relative links only.
7. English only (see `AGENTS.md`); video-language strings are quoted examples, not prose.
