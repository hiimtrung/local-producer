# Architecture Decision Records

| | |
| :--- | :--- |
| **Status** | Active — index of accepted decisions |
| **Owner** | maintainer (`@hiimtrung`) |
| **Last verified** | 2026-11-05 |
| **Applies to** | the whole repository |

An ADR records **one decision**: what was decided, what was rejected, and what would reopen it. ADRs are immutable
once accepted: a later decision supersedes an earlier one with a new ADR and a `Superseded by` line, it never edits
history. They are not plans and not tutorials; measurements belong in [`../analysis/`](../analysis/) and
[`CHANGELOG.md`](../../CHANGELOG.md).

## Index

| ADR | Title | Status | Date |
| :--- | :--- | :--- | :--- |
| [0001](./0001-trunk-based-main.md) | Trunk-based development on `main` | Accepted | 2026-11-05 |
| [0002](./0002-native-runtime-no-containers.md) | One native runtime, no containers | Accepted | 2026-11-05 |
| [0003](./0003-tauri-desktop-shell.md) | Tauri v2 as the desktop shell | Accepted | 2026-11-05 |
| [0004](./0004-one-baseline-artifact-and-compat-scan.md) | One baseline engine artifact per OS, compatibility decided by a scan | Accepted | 2026-11-05 |
| [0005](./0005-loopback-only-token.md) | Loopback-only server, token on by default | Accepted | 2026-11-05 |
| [0006](./0006-documentation-as-code.md) | Documentation is a layered tree, checked by CI | Accepted | 2026-11-05 |

## Template

Copy this block into `docs/adr/NNNN-kebab-title.md`, then add the row to the index above. `make docs-check` fails if
the index and the directory disagree.

```markdown
# NNNN. Short title in the imperative

| | |
| :--- | :--- |
| **Status** | Accepted / Superseded by [NNNN](./NNNN-....md) |
| **Owner** | maintainer |
| **Last verified** | YYYY-MM-DD |
| **Date** | YYYY-MM-DD |

## Context

The forces at play: measured facts, constraints, the problem that needs a decision. Link the analysis or changelog
entry rather than repeating numbers.

## Decision

One paragraph, present tense: "We do X." Then the specifics that make it checkable.

## Consequences

What becomes easier, what becomes harder, what must now be maintained. Include the cost honestly.

## Alternatives considered

Each rejected option with the reason it lost. This is the part that makes an ADR worth keeping.

## What would reopen this

The observation or event that should trigger a new ADR.
```
