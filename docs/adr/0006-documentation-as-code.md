# 0006. Documentation is a layered tree, checked by CI

| | |
| :--- | :--- |
| **Status** | Accepted |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Date** | 2026-11-05 |

## Context

Before this decision the repository had eleven Markdown files and no `docs/` directory. `README.md` was a front page,
an install guide, an architecture summary and a usage manual at once. `AGENTS.md` carried a second architecture
description that had already drifted from the code. `CHANGELOG.md` (1,300+ lines) was the only record of why the
architecture looked the way it did.

That layout has a predictable failure mode: the same fact is written in three places, reviews update one of them, and
a new contributor cannot tell which copy is current. The project also requires experiments to be recorded rather than
remembered, which is a documentation problem, not a code problem.

## Decision

The documentation is a layered tree under `docs/`, and its integrity is enforced by a script in CI.

- **Layers** follow Diátaxis — `architecture/` (why), `operations/` (how to do a task), `development/` (learn it),
  `reference/` (exact values) — plus `adr/` (one decision per page), `analysis/` (dated studies) and `archive/`
  (superseded documents, kept with a banner).
- **`docs/README.md` is the index and the routing table.** Every page must be reachable from it; an orphan page is a
  build failure.
- **One canonical page per topic.** Other documents link to it; `README.md` and `AGENTS.md` may carry one-line
  summaries, nothing more.
- **Every page starts with a header table**: `Status`, `Owner`, `Last verified` (the date the content was checked
  against the code, not edited), and `Applies to` when the scope is not the whole repository.
- **`scripts/check_docs.py` (`make docs-check`, part of `make check` and CI)** fails on a missing header, an orphan, a
  dead relative link or `#anchor`, a missing or duplicated `H1`, non-English prose, and an ADR missing from its index.
- **Root keeps seven files**, each with one job: `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CHANGELOG.md`, `CODE_OF_CONDUCT.md`, `LICENSE`. GitHub conventions win where they exist; those files stay at root.
- **Pages are written when the thing they describe exists.** Architecture and operation pages for the native runtime
  land with the change that creates it, not before.

## Consequences

- A fact has one address, so "which copy is right?" stops being a question.
- Decisions are answerable without archaeology: each ADR carries the rejected alternatives and the trigger that would
  reopen it.
- Docs rot becomes a red build. The cost is that adding a page means linking it from the index and giving it a header;
  that is the point.
- The checks are heuristics: the English check rejects CJK and Vietnamese-specific letters, not every borrowed word,
  and quoted video-language strings need an explicit `docs-check: allow-non-english` marker.
- `CHANGELOG.md` stays a chronological log and is not split; the studies it summarises move to `docs/analysis/`.

## Alternatives considered

- **One long `README.md` plus a wiki**: rejected — a wiki is outside review and outside CI, and it forks the source of
  truth.
- **A static site generator (MkDocs, Docusaurus)**: rejected — it adds a build toolchain and a theme to maintain for a
  tree that plain Markdown renders correctly on GitHub; the checks, not the renderer, are what keep it honest.
- **Numbered documentation (`01-intro.md`, `02-...`)**: rejected — order is the index's job, and numeric prefixes make
  links unstable when a page is inserted.
- **Deleting superseded specs**: rejected — deleting the only written spec would lose the reasoning behind the gates;
  `AGENTS.md` already distinguishes deleting failed code from keeping decisions.

## What would reopen this

A second maintained product or a public documentation site, where a generator and a navigation model start paying for
themselves. Link and header checks stay regardless of the renderer.

## Amendment 2026-11-05 — execution plans

A seventh layer, `plans/`, was added the day this ADR was accepted: one file per phase, holding the task list, the
interfaces, the measurements and an acceptance checklist. It is deliberately not part of `analysis/` (a plan is not a
study) and not an ADR (it is not a decision). A plan is deleted, or moved to `analysis/` as a dated record, when its
phase lands, so nothing in `plans/` describes finished work as if it were current. The header, link, orphan and
language checks apply unchanged.
