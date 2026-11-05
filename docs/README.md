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
| set up your development environment | [`development/setup.md`](./development/setup.md) |
| run the server headlessly via CLI | [`operations/run-headless.md`](./operations/run-headless.md) |
| find where data, weights and logs are stored | [`reference/storage.md`](./reference/storage.md) |
| understand the native runtime architecture | [`architecture/overview.md`](./architecture/overview.md) |
| inspect the native security model | [`architecture/security-model.md`](./architecture/security-model.md) |
| troubleshoot runtime and GPU problems | [`operations/troubleshooting.md`](./operations/troubleshooting.md) |
| know why there are no containers, and why a Tauri shell | [`adr/`](./adr/README.md) |
| see the measurements behind a decision | the two [analysis](./analysis/2026-11-desktop-architecture.md) studies and [`CHANGELOG.md`](../CHANGELOG.md) |
| know what is being built next, with acceptance criteria | [`plans/`](./plans/README.md) |
| read a superseded spec for its reasoning | [`archive/`](./archive/local-producer-v2.1.md) |

## Layers

| Layer | Answers | Directory | State |
| :--- | :--- | :--- | :--- |
| Architecture | "why is it built this way?" | `architecture/` | active — core pages landed with P1 |
| Operations | "how do I install / run / fix it?" | `operations/` | active — CLI and troubleshooting landed with P1 |
| Development | "how do I work on it?" | `development/` | active — setup and testing landed with P1 |
| Reference | "what are the exact paths, fields, endpoints?" | `reference/` | active — storage, config, and glossary landed with P1 |
| Decisions | "why this and not that?" | [`adr/`](./adr/README.md) | ADR 0001–0006 exist |
| Analysis | dated studies, not contracts | `analysis/` | three studies and records exist |
| Plans | "what is being built now, and how do we know it is done?" | [`plans/`](./plans/README.md) | P1 landed; P2 plan pending |
| Archive | superseded documents, kept for their reasoning | `archive/` | two files, both marked Superseded |

### Architecture

- [`architecture/overview.md`](./architecture/overview.md) — three tiers, what runs where, and what P1 changed.
- [`architecture/runtime-contract.md`](./architecture/runtime-contract.md) — data root per OS, layout tree, child environment table, ports, and `runtime.json`.
- [`architecture/security-model.md`](./architecture/security-model.md) — loopback invariant, token status, engine sandbox, and residual risk.

### Operations

- [`operations/run-headless.md`](./operations/run-headless.md) — CLI usage (`lp setup/up/status/logs/down/doctor`), `LP_HOME`, and systemd unit.
- [`operations/troubleshooting.md`](./operations/troubleshooting.md) — engine blocked, port conflicts, web build, venv, and GPU resets.
- [`operations/backup-and-migrate.md`](./operations/backup-and-migrate.md) — directory tree, safe deletions, `LP_HOME`, and migration paths.

### Development

- [`development/setup.md`](./development/setup.md) — clone, `make dev`, `make check`, `lp setup`, and the two virtual environments.
- [`development/testing.md`](./development/testing.md) — pytest layout, fixtures, what needs a GPU, CI matrix, and check gates.

### Reference

- [`reference/storage.md`](./reference/storage.md) — native filesystem storage layout, weights and engine sources.
- [`reference/configuration.md`](./reference/configuration.md) — `RuntimeConfig` parameters, validation bounds, and environment variables.
- [`reference/glossary.md`](./reference/glossary.md) — definitions of key project terms.

### Studies

- [`analysis/2026-11-desktop-architecture.md`](./analysis/2026-11-desktop-architecture.md) — one runtime contract,
  native on both platforms, shipped as a Tauri app; phases and acceptance criteria.
- [`analysis/2026-11-performance-bottlenecks.md`](./analysis/2026-11-performance-bottlenecks.md) — ranked GPU and UI
  bottlenecks with the measurements behind them.
- [`analysis/2026-11-p1-native-runtime.md`](./analysis/2026-11-p1-native-runtime.md) — dated record of the P1 native runtime
  execution plan and acceptance checklist (completed 2026-11-05).

### Plans

- [`plans/`](./plans/README.md) — index of active execution plans. P1 landed (preserved in `analysis/`); P2 plan pending.

### Archive

- [`archive/local-producer-v2.1.md`](./archive/local-producer-v2.1.md) — the v2.1 specification; superseded, kept
  for its measured Blender/ROCm facts.
- [`archive/spec-v3-gated-pipeline.md`](./archive/spec-v3-gated-pipeline.md) — a gated, template-driven pipeline
  proposal; never adopted.

### Planned pages

Listed so that new work has a canonical home; they are **not links**, because the files do not exist yet.

- `architecture/`: `engines`, `pipelines`, `data-model`
- `operations/`: `install-desktop`, `release-runbook`
- `development/`: `adding-a-pipeline`, `adding-a-page`
- `reference/`: `api`, `catalog`

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
