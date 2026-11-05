# Testing and verification

| | |
| :--- | :--- |
| **Status** | Active |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Applies to** | all platforms |

This guide covers the testing architecture, fixture design, continuous integration suite, and verification commands.

## Verification suite: `make check`

Before committing or opening a pull request, run the full verification gate:

```bash
make check
```

`make check` executes:
1. `lint`: Ruff formatting, shellcheck, gitleaks secret detection, and file hygiene via pre-commit.
2. `docs-check`: Documentation validation (structure, unique H1s, headers, link resolution, and English prose).
3. `typecheck`: Python type assertions (`mypy --strict`) and TypeScript verification (`tsc --noEmit`).
4. `test`: Pytest unit test suite and generated design token verification.
5. `lock-check`: Requirement lock parity checks between Linux and macOS.
6. `check-removal`: Ensures no legacy container artifacts or obsolete tool references remain in tracked files.
7. `web-build`: Complete production build of the TypeScript web UI into `web/dist`.

## Pytest layout and structure

Unit tests are organized under the top-level `tests/` directory:

| Test module | Focus |
| :--- | :--- |
| `tests/test_api.py` | FastAPI endpoint contracts, job submission, queue ordering, and error responses |
| `tests/test_engines.py` | Engine package registry, active package switching, and runner execution |
| `tests/test_model_setup.py` | Model catalog validation, checksum verification, and download handling |
| `tests/test_prompts.py` | Shared prompt framing templates and style options |
| `tests/test_addon.py` | Blender add-on HTTP client, version matching, and payload serialization |
| `tests/test_web_static.py` | Web UI asset integrity, Lucent vendor locks, and CSP configuration |
| `tests/test_runtime_env.py` | Data root path precedence, layout initialization, and child environment tables |
| `tests/test_supervisor.py` | Supervisor startup lifecycle, health polling, port fallback, and shutdown signals |
| `tests/test_sandbox.py` | Sandbox policy prefix generation and missing-tool refusal logic |
| `tests/test_lp.py` | CLI commands (`root`, `setup`, `up`, `down`, `status`, `doctor`) |

Run unit tests directly:

```bash
uv run pytest
```

## Mocking and fixtures: no GPU required

A primary architectural rule is that **unit tests never require a GPU and never access external networks**:

- **`fake_host` fixture:** Simulates different OS platforms (macOS, Linux), CPU architectures, and ROCm/Metal detection without inspecting host hardware.
- **Fake engine packages:** Tests use simulated runner binaries that return deterministic dummy outputs (such as placeholder PNGs or GLBs) to test pipelines and the queue end-to-end.
- **`tmp_path` directory isolation:** File operations are isolated to temporary directories created by pytest fixtures, preventing tests from modifying the developer's data root.

## Tests requiring hardware

Hardware-dependent verification is separated from the unit test suite:

- **Smoke test (`make smoke`):** Runs `scripts/smoke_test.py` against a running server (`http://127.0.0.1:13305`). It submits real text-to-image and 3D reconstruction jobs using the loaded native engine to prove hardware compute functionality.
- **Add-on manual tests:** Verified inside Blender by pointing the LocalProducer extension to the running server.

## Specialized check targets

### 1. Documentation verification: `make docs-check`

Runs `scripts/check_docs.py` to enforce documentation hygiene:
- Every document must have a standard header table with `Status`, `Owner`, and `Last verified` date.
- Exactly one `H1` heading per document, unique across the entire repository.
- No broken relative links or nonexistent anchor fragments.
- No orphaned documents unreachable from `docs/README.md`.
- English language only (quoted video content must include the comment `docs-check: allow-non-english`).

### 2. Lock file parity: `make lock-check`

Runs `scripts/lock-requirements.sh --check` to ensure:
- Platform lock files (`server/requirements.macos.txt` and `server/requirements.linux.txt`) are up to date with `server/requirements.in`.
- Both platform locks pin the exact same set of package names and version numbers.

### 3. Removal verification: `make check-removal`

Ensures that no legacy container files or container engine references exist in active documentation and source code:
- Verifies that deleted build artifacts do not exist in `git ls-files`.
- Runs `git grep` to assert that obsolete container tool keywords are absent outside archived documents.

## Continuous integration matrix

GitHub Actions runs on every pull request across two environments:
- **`ubuntu-24.04`:** Linux host runner.
- **`macos-14`:** macOS Apple silicon runner.

Both jobs execute the complete `make check` suite, confirming identical behavior across supported operating systems.
