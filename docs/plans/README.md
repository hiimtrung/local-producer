# Execution plans

| | |
| :--- | :--- |
| **Status** | Active — P1 is ready for execution; later phases are not written yet |
| **Owner** | maintainer (`@hiimtrung`) |
| **Last verified** | 2026-11-05 |
| **Applies to** | work in progress |

A plan turns one phase of [`../analysis/2026-11-desktop-architecture.md`](../analysis/2026-11-desktop-architecture.md)
into tasks an agent or a contributor can execute without guessing: exact files, interfaces, commands, measurements and
an acceptance checklist. A plan is **not** a contract and not a decision record: the decision lives in
[`../adr/`](../adr/README.md), the rationale and phase boundaries in the architecture analysis.

Rules:

1. One phase, one plan. If the scope cannot be finished and verified in one pull request series, split it.
2. A plan states what must be **measured**, not only what must be built, and it says how.
3. A plan is deleted (or moved to `../analysis/` as a dated record) when its phase lands. Do not keep finished plans
   as if they described the current code.
4. If a plan and the code disagree, the code wins and the plan is corrected in the same change.

## Plans

| Plan | Phase | Status | Depends on |
| :--- | :--- | :--- | :--- |
| [`2026-11-p1-native-runtime.md`](./2026-11-p1-native-runtime.md) | P1 — one contract, container deleted (no GPU) | Ready for execution | Nothing; starts from `main` at `8afc01a` or later |

Later phases (P2 engine artifacts and the compatibility scan, P3 Tauri shell, P4 onboarding, P5 distribution, P6 Linux
desktop) are defined in the architecture analysis and get their own plan when the previous phase is accepted.
