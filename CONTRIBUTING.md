# Contributing

Thanks for helping. This page is the contract for every change; `AGENTS.md` adds the project's working conventions
(also for AI coding agents) and `SECURITY.md` the security rules.

## Ground rules

- **English only** in everything committed: code, comments, docs, commit messages, logs, prompts. The only exception
  is video content in the video's own language (see `AGENTS.md`).
- **Only source goes into git.** Weights, binaries, meshes, renders, logs and environments are git-ignored and stay
  out; the pre-commit hook blocks files over 2 MiB. Weights and engine packages are fetched from `server/catalog/` by
  each user.
- **Measure, don't estimate.** A change that claims a speed or quality effect brings numbers (sample size, noise) and,
  if it is an experiment, an entry in `CHANGELOG.md` (newest first: goal, setup, numbers, conclusion; hypotheses are
  labelled as such).
- **Security rules are not optional** (`SECURITY.md`): no shell in subprocess calls, validate every request field,
  pin and hash every download and dependency, never widen the network exposure of the server.
- **GPL-3.0-or-later.** By contributing you agree that your contribution is licensed under it (`LICENSE`). Do not add
  code copied from projects with incompatible licences.

## Setup

```bash
make dev          # uv sync + pre-commit install + npm ci in web/ (needs uv and Node.js 24)
make check        # what CI runs: lint, secret scan, file hygiene, type checks, unit tests, web build
```

GPU jobs need a machine with an engine package (`README.md`; today AMD gfx1103 + ROCm, `cwsr_enable=0`); unit tests
do not (they use a fake package).

## Workflow

1. Open an issue first for anything larger than a fix, so the approach is agreed before code is written.
2. Branch from the default branch: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `exp/<topic>` (experiments).
3. Keep pull requests small and focused; fill in the template. CI must be green; a code owner reviews.
4. Commit messages: [Conventional Commits](https://www.conventionalcommits.org/) (`feat(server): ...`,
   `fix(addon): ...`, `docs: ...`, `test: ...`, `chore(deps): ...`), imperative mood, body explains why.
5. Squash-merge; the branch is deleted after the merge.

## Code layout and style

| Path | What | Notes |
| :--- | :--- | :--- |
| `server/app/pipelines/` | one module per capability | add a `Pipeline[Params]` subclass (validated `Params`, `run`, optional `parse_progress`) and its request model `{kind: Literal[...], params: Params}`, register both in `__init__.py` (a test checks they agree), then `make api-types`: the job API, the typed web client, the Tools page (a form generated from its schema) and the history pick it up |
| `server/app/routes/` | one module per API area | register a new router in `routes/__init__.py`; validate every field with pydantic; every handler returns a pydantic model (`schemas.ApiModel`) so the API schema is complete; never accept paths or URLs from clients |
| `server/app/schemas.py` | models shared by queue, pipelines and routes | `Job`, `JobProgress`, `JobInfo`, `ImageRef`; a pipeline that reports a new fact adds a field to `JobInfo` |
| `server/app/settings.py` | hard limits and `RuntimeConfig` | a user-facing setting is a validated field there; the web Settings page renders it from the schema |
| `server/app/engines/` | engine packages | the platform-specific half: `host.py` detects the machine, `backends.py` holds per-stack code that ships with the server (preflight checks, GPU memory), `registry.py` installs / loads / reloads packages and gives pipelines their runners (`engines.runner("sd-cli")`); a pipeline names the runners it needs in `runners` |
| `server/catalog/` | pinned downloads | `models.json` weights (portable), `engines.json` engine packages; see below |
| `web/src/api/` | the typed API client | `types.gen.ts` is generated (`make api-types`, never edited); all HTTP goes through `client.ts`; `api.submit(kind, params)` is checked against that kind's params |
| `web/src/ui/` | atomic design | `atoms/` (Lucent controls with their prop types in `lucent.ts`, icons, text styles), `molecules/` (a form row, a progress capsule, a drop zone), `organisms/` (pickers, schema form, viewer, dialogs, tab bar), `templates/` (app shell, stage layout, document page); each layer imports only the layers below it and keeps its CSS next to it. Reuse before adding: a new piece goes in the lowest layer it fits |
| `web/src/pages/` | one component per page | takes `PageProps` (`query`, `navigate`), registered in `src/app/pages.ts` with its bottom-bar tab; its id goes into `PAGE_IDS` in `src/app/router.ts` |
| `web/src/hooks/`, `web/src/lib/` | data hooks, helpers | files through `useFileUrl` (works with a token); jobs through `useJob` |
| `web/vendor/lucent/` | the design system | pinned in `VENDOR.json` (size, SHA256); never edited by hand. npm packages are exact versions locked with integrity hashes, installed without install scripts (`web/.npmrc`); nothing loads from a CDN (CSP `script-src 'self'`) |
| `web/styles/tokens.css` | generated | `make web-tokens` after changing `web/vendor/lucent/tokens.json` |
| `blender/local_producer/` | Blender add-on | `prompts.py` and `client.py` must not import `bpy`; `prompts.py` is also used by the server |
| `scripts/`, `tests/` | developer scripts, pytest | new behaviour comes with a test; tests use no GPU and no network |

**UI rules:** TypeScript strict, no `any` (a cast needs a comment saying why it is safe); use the Lucent components
(`src/ui/atoms`) and tokens, never hard-coded colours or sizes (the one exception, the studio grey of the stage, is
documented in `web/src/styles/base.css`); glass only for floating controls (tab bar, parameter panel, overlays),
content on `bg` / `bg-elevated`; sentence case, buttons start with a verb, errors say how to fix them; English only.
`make web-dev` serves the API and the UI from the host and rebuilds on change.

**Python typing:** the server passes `mypy --strict` (`make typecheck`); annotate every function, no untyped `dict`
payloads across module boundaries (use a pydantic model or a `TypedDict`).

- Ruff is the linter and formatter (`pyproject.toml`: line length 120, security rules on). `make format` fixes most
  findings; a `# noqa` needs a reason on the same line.
- Shell scripts start with `set -euo pipefail` and pass shellcheck.
- Changing `server/catalog/*.json`: take URL, size and SHA256 from the upstream release page / Hugging Face API for
  a fixed revision (never `main`), run `make models-verify` (weights) or `make engines` (a package), and note the
  version change in `CHANGELOG.md`. A changed engine package gets a new `version`, so installed ones stay loadable.
- A new platform (CUDA, MLX): a package in `engines.json` with its `platform` and `runners`, and the stack's
  preflight / memory probe in `backends.py`; pipelines stay as they are when the runners keep their command line.
- Changing the add-on: bump `version` in `blender_manifest.toml` and `bl_info["version"]` together (a test checks
  they match), so Blender offers the update; keep the request format compatible with the server.
