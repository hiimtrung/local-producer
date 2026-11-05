# Development environment setup

| | |
| :--- | :--- |
| **Status** | Active |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Applies to** | all platforms |

This document guides developers through setting up a complete local development environment for local-producer.

## Prerequisites

Ensure the following tools are installed on your host system:

- **Python packaging:** [uv](https://docs.astral.sh/uv/) (manages Python versions and dependencies).
- **Node.js:** Node.js 24 with npm (builds the TypeScript/React web frontend).
- **Build tools:** GNU make and standard POSIX shell utilities.
- **macOS specifics:** Xcode Command Line Tools (`xcode-select --install`) and CMake (`brew install cmake`) for compiling `trellis-cli`.
- **Linux specifics:** Bubblewrap (`bwrap`) for engine CLI sandboxing (`sudo apt-get install bubblewrap`).

## Initial setup

Clone the repository and initialize the project:

```bash
git clone https://github.com/hiimtrung/local-producer.git
cd local-producer

# 1. Install development tools, pre-commit hooks, and web packages
make dev

# 2. Run the full verification suite
make check

# 3. Initialize the runtime data root and runtime virtual environment
scripts/lp setup
```

## First run

Start the server stack locally:

```bash
scripts/lp up
```

Once ready, visit `http://127.0.0.1:13305` in your browser.
Open **Server > Engines** to install or inspect your platform engine runner, and **Server > Models** to download initial weights.

To stop the server:

```bash
scripts/lp down
```

## The two virtual environments explained

The repository intentionally uses two distinct Python virtual environments to isolate development dependencies from runtime execution:

```
local-producer/
├── .venv/                      # 1. Development virtual environment (uv sync)
│   └── bin/ (ruff, mypy, pytest, pre-commit, ...)
│
<data_root>/
└── venv/                       # 2. Runtime virtual environment (scripts/lp setup)
    └── bin/ (fastapi, uvicorn, onnxruntime, pydantic, ...)
```

### 1. Repository development environment (`.venv`)

- **Location:** `<repo_root>/.venv`
- **Created by:** `make dev` (via `uv sync`)
- **Purpose:** Contains all development tools: code formatters (`ruff`), static type checkers (`mypy`), test runners (`pytest`), git hooks (`pre-commit`), and build scripts.
- **Rule:** Never used to run production server processes or native engine jobs.

### 2. Runtime environment (`<data_root>/venv`)

- **Location:** Resolved within the platform data root (`~/Library/Application Support/local-producer/venv` on macOS, `~/.local/share/local-producer/venv` on Linux).
- **Created by:** `scripts/lp setup`
- **Purpose:** Contains the exact locked runtime dependencies needed by FastAPI, Uvicorn, and `matte_server.py`. Installed with `--require-hashes` from `server/requirements.macos.txt` or `server/requirements.linux.txt`.
- **Rule:** Free of development tools to mirror production desktop distributions exactly.

## Useful development commands

```bash
make test         # Run unit tests and generated token validation
make typecheck    # Check Python types (mypy --strict) and TypeScript types
make format       # Format Python code using ruff
make lint         # Run all pre-commit linters and security checks
make web-build    # Compile the React frontend into web/dist
make web-dev      # Run the web frontend in watch mode for active UI development
```

For testing workflows and continuous integration guidelines, consult [Testing and verification](testing.md).
