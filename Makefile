# Common tasks. `make help` lists them. Python tooling runs through uv (https://docs.astral.sh/uv/).
SHELL := /bin/bash

.PHONY: help dev lint typecheck api-types web-install web-build web-tokens web-dev format test check docs-check lock-check addon server-build server-up server-down setup engines engines-status models models-status models-verify smoke

RUN_TOOL = scripts/lp exec

help:  ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

dev:  ## create .venv and web/node_modules with the dev tools and install the git hooks
	uv sync
	uv run pre-commit install
	cd web && npm ci

web-install:  ## install the web UI's pinned npm packages (web/package-lock.json, no install scripts)
	cd web && npm ci

web-build:  ## type-check and build the web UI into web/dist (the server serves it)
	cd web && npx tsc --noEmit -p . && node build.mjs

api-types:  ## regenerate web/src/api/types.gen.ts from the server's pydantic models
	uv run python scripts/gen_api_types.py

typecheck:  ## mypy --strict on the server, tsc --strict on the web UI, generated API types up to date
	uv run mypy
	uv run python scripts/gen_api_types.py --check
	cd web && npx tsc --noEmit -p .

web-tokens:  ## regenerate web/styles/tokens.css from the Lucent tokens
	uv run python scripts/gen_tokens_css.py

web-dev:  ## API + web UI on the host, rebuilt on change (http://127.0.0.1:13399)
	cd web && node build.mjs --watch & \
	LP_HOME=$(CURDIR)/build/web-dev scripts/lp exec -m app.main --host 127.0.0.1 --port 13399

lint:  ## ruff, shellcheck, secret scan and file hygiene (the same hooks CI runs)
	uv run pre-commit run --all-files

format:  ## format Python code
	uv run ruff format .
	uv run ruff check --fix .

test:  ## unit tests (no GPU, no network) and generated-file checks
	uv run pytest
	uv run python scripts/gen_tokens_css.py --check

docs-check:  ## documentation tree: header tables, orphans, links and anchors, duplicate H1, English only
	uv run python scripts/check_docs.py

lock-check:  ## check that server lock files match requirements.in and agree across platforms
	scripts/lock-requirements.sh --check

check: lint docs-check typecheck test lock-check web-build  ## everything CI checks

addon:  ## build dist/local_producer.zip
	blender/build_addon.sh

server-build:  ## set up the server's Python environment and build the web UI
	scripts/lp setup

server-up:  ## start the server: web UI + API on http://127.0.0.1:13305, matting on 127.0.0.1:8083
	scripts/lp up

server-down:  ## stop the server
	scripts/lp down

setup: engines models  ## install the engine package for this machine, then the models

engines:  ## download, verify and load the engine package for this machine into the engines directory
	$(RUN_TOOL) -m app.engines.registry install

engines-status:  ## this machine, the installed engine packages and whether one loads
	$(RUN_TOOL) -m app.engines.registry status

models:  ## download and install the pinned models into the models directory (~24 GB, SHA256-verified)
	$(RUN_TOOL) -m app.model_setup download

models-status:  ## what is installed (fast: existence and size)
	$(RUN_TOOL) -m app.model_setup status

models-verify:  ## full SHA256 check of the installed models (a few minutes)
	$(RUN_TOOL) -m app.model_setup verify

smoke:  ## end-to-end check against the running server: A-pose edit -> matting -> TRELLIS.2 (Fast, ~5 min of GPU)
	uv run python scripts/smoke_test.py blender/local_producer/samples/cat.png build/smoke 512 3 6
