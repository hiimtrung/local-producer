# Common tasks. `make help` lists them. Python tooling runs through uv (https://docs.astral.sh/uv/).
SHELL := /bin/bash
IMAGE ?= localhost/local-producer-gpu
NAME ?= local-producer-gpu

.PHONY: help dev lint typecheck api-types web-install web-build web-tokens web-dev format test check addon server-build server-up server-down setup engines engines-status models models-status models-verify smoke

# A one-off container on the server image with the volumes, host directories and GPU devices (to detect the GPU)
# of the server (scripts/lp-env.sh).
RUN_TOOL = source scripts/lp-env.sh && lp_volumes && lp_mounts && lp_gpu && podman run --rm --userns=keep-id \
	--user "$$(id -u):$$(id -g)" --cap-drop=all --security-opt no-new-privileges "$${LP_GPU[@]}" \
	--security-opt label=disable "$${LP_MOUNTS[@]}" --entrypoint python $(IMAGE)

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

web-dev:  ## API + web UI on the host, rebuilt on change (http://127.0.0.1:13399; GPU jobs need the container)
	cd web && node build.mjs --watch & \
	source scripts/lp-env.sh && lp_volumes && cd server && MODELS_DIR="$$(lp_mountpoint $$MODELS_VOLUME)" \
	    ENGINES_DIR=$(CURDIR)/build/web-dev/engines LIBRARY_DIR=$(CURDIR)/build/web-dev/library \
	    DATA_DIR=$(CURDIR)/build/web-dev ../.venv/bin/python -m app.main --host 127.0.0.1 --port 13399

lint:  ## ruff, shellcheck, secret scan and file hygiene (the same hooks CI runs)
	uv run pre-commit run --all-files

format:  ## format Python code
	uv run ruff format .
	uv run ruff check --fix .

test:  ## unit tests (no GPU, no network) and generated-file checks
	uv run pytest
	uv run python scripts/gen_tokens_css.py --check

check: lint typecheck test web-build  ## everything CI checks

addon:  ## build dist/local_producer.zip
	blender/build_addon.sh

server-build:  ## build the GPU server image
	podman build -t $(IMAGE) -f server/Containerfile .

server-up:  ## start the server: web UI + API on http://127.0.0.1:13305, matting on 127.0.0.1:8083
	scripts/run-server.sh

server-down:  ## stop the server
	podman stop $(NAME)

setup: engines models  ## install the engine package for this machine, then the models

engines:  ## download, verify and load the engine package for this machine into the engines volume
	$(RUN_TOOL) -m app.engines.registry install

engines-status:  ## this machine, the installed engine packages and whether one loads
	$(RUN_TOOL) -m app.engines.registry status

models:  ## download and install the pinned models into the models volume (~24 GB, SHA256-verified)
	$(RUN_TOOL) -m app.model_setup download

models-status:  ## what is installed (fast: existence and size)
	$(RUN_TOOL) -m app.model_setup status

models-verify:  ## full SHA256 check of the installed models (a few minutes)
	$(RUN_TOOL) -m app.model_setup verify

smoke:  ## end-to-end check against the running server: A-pose edit -> matting -> TRELLIS.2 (Fast, ~5 min of GPU)
	uv run python scripts/smoke_test.py blender/local_producer/samples/cat.png build/smoke 512 3 6
