# 0001. Trunk-based development on `main`

| | |
| :--- | :--- |
| **Status** | Accepted |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Date** | 2026-11-05 |

## Context

The repository carried a long-lived `develop` branch alongside `main`, plus feature branches that lived for weeks.
The result was predictable: `main` and `develop` drifted, fixes landed on one and not the other, and the branch list
grew to dozens of open pull requests that could no longer be reviewed against each other. A solo-maintained R&D
project cannot pay the merge-conflict tax of a two-branch model, and the release process does not need a staging
branch because there is no scheduled release train yet.

## Decision

We develop on `main` only, with short-lived branches that are merged within days and deleted after merge.

- Every change arrives as a pull request with a Conventional Commit title (`feat:`, `fix:`, `docs:`, `chore:`, …).
- History on `main` is linear: squash-merge or rebase, never a merge commit.
- Branches are named `<type>/<short-slug>` and deleted after merge, locally and on the remote.
- A change that must not ship yet is hidden behind a flag or simply not merged; it does not live on a branch.

## Consequences

- One branch to keep green, one place to look for the current state.
- CI must be meaningful on every pull request, because `main` is always the release candidate. This is why
  `make check` is a single command that covers lint, types, tests and docs.
- Large changes must be split into reviewable pieces. That is a cost, and it is smaller than the drift it replaces.
- Users who built from `develop` have to move to `main`; the branch was deleted rather than frozen.

## Alternatives considered

- **Git Flow (`main` + `develop` + release branches)**: appropriate when several versions are supported in parallel.
  Here nothing is released yet, so the extra branch only duplicated state.
- **Long-lived feature branches**: keeps `main` pristine but delays integration and makes review harder as the branch
  ages; rejected after the cleanup showed 38 pull requests whose conflicts were mostly mechanical.

## What would reopen this

A supported-version matrix (for example maintaining a stable desktop release while `main` moves to the next major
version). At that point a release branch per supported version is justified, not a permanent `develop`.
