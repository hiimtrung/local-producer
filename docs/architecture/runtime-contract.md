# Native runtime contract

| | |
| :--- | :--- |
| **Status** | Active |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Applies to** | all platforms |

This document defines the runtime environment contract for local-producer, including filesystem locations,
process supervision, environment variables, port assignments, and CLI lifecycle operations.

## Data root resolution

All mutable runtime state, models, packages, and outputs reside within a single data root. The location is determined by `app.runtime_env.data_root()` in this order of precedence:

1. **`$LP_HOME`:** If set, this path is expanded and resolved as the root directory.
2. **macOS:** `~/Library/Application Support/local-producer`
3. **Linux / other:** `${XDG_DATA_HOME:-~/.local/share}/local-producer`

## Layout tree

Under the resolved data root, `app.runtime_env.Layout` defines five canonical directories:

```
<data_root>/
├── models/       # Shared weights (flux2/, trellis2/, rembg/) and user-added models (user/<id>/)
├── engines/      # Pinned native runner packages (<package>/<version>/) and active.json
├── library/      # Finished job outputs (jobs/<id>/) and uploads (uploads/<id>/)
├── server/       # Runtime state: runtime.json, runtime.log, server.log, config.json (mode 0700)
└── venv/         # Runtime Python 3.12 virtual environment (isolated from development venv)
```

The `server/` directory holds configuration and runtime state. When created by `Layout.ensure()`, its permissions are set to mode `0700` (`rwx------`) to protect sensitive state and tokens.

## Child environment contract

When `app.supervisor` or `scripts/lp` launches the API server, matting worker, or runner processes, it populates the environment using `app.runtime_env.child_env()`:

| Environment variable | Value | Purpose |
| :--- | :--- | :--- |
| `MODELS_DIR` | `<data_root>/models` | Location of model weights |
| `ENGINES_DIR` | `<data_root>/engines` | Location of installed engine packages |
| `LIBRARY_DIR` | `<data_root>/library` | Persistent output directory |
| `DATA_DIR` | `<data_root>/server` | Configuration and logging directory |
| `U2NET_HOME` | `<data_root>/models/rembg` | Background removal model cache |
| `PYTHONDONTWRITEBYTECODE` | `1` | Prevents writing `__pycache__` inside user data |
| `PYTHONUNBUFFERED` | `1` | Flushes stdout and stderr immediately to logs |
| `OMP_NUM_THREADS` | derived string | Performance cores on macOS (`hw.perflevel0.physicalcpu`), `min(8, sched_getaffinity)` on Linux, fallback `os.cpu_count() or 1` |
| `HOST_MODELS` | `<data_root>/models` | Informational path exposed in UI |
| `HOST_ENGINES` | `<data_root>/engines` | Informational path exposed in UI |
| `HOST_LIBRARY` | `<data_root>/library` | Informational path exposed in UI |
| `HOST_DATA` | `<data_root>/server` | Informational path exposed in UI |
| `SERVER_TOKEN` | pass-through if set | Authentication token for the API |

## Ports and endpoints

| Service | Address | Behavior |
| :--- | :--- | :--- |
| API Server & Web UI | `127.0.0.1:13305` | Default port. If unavailable, an ephemeral port is chosen and recorded in `runtime.json`. |
| Matting Worker | `127.0.0.1:8083` | Fixed port. If occupied, supervisor startup aborts with an error naming the port. |

All services bind exclusively to `127.0.0.1` (loopback). Binding to `0.0.0.0` or external network interfaces is prohibited.

## Runtime discovery: `runtime.json`

Once both the API server and matting worker respond with HTTP 200 to `/health`, the supervisor writes `<data_root>/server/runtime.json`.
The write is atomic: contents are written to a temporary file (`runtime.json.tmp.<pid>`), permissions are set to mode `0600` (`rw-------`), and the file is atomically renamed into place.

Example contents:

```json
{
  "url": "http://127.0.0.1:13305",
  "port": 13305,
  "pid": 48215,
  "version": "0.15.0",
  "started": "2026-11-05T08:00:00.000000Z"
}
```

Clients and tools read `runtime.json` to discover the active endpoint URL and process ID. On clean shutdown, the supervisor deletes `runtime.json` if and only if the recorded PID matches its own.

## Supervisor lifecycle and logging

The supervisor orchestrates services through defined phases:

1. **Initialization:** Ensures directory layout exists with correct permissions. Selects an available port for the API server.
2. **Child startup:** Spawns `matte_server.py` (unless `--no-matte`) in a new process group, followed by `app.main` in a separate process group.
3. **Health verification:** Polls `http://127.0.0.1:<port>/health` and `http://127.0.0.1:8083/health` at 500 ms intervals up to 180 seconds. If a child terminates prematurely or times out, all children are terminated and the supervisor exits with an error code.
4. **Publish state:** Atomically writes `runtime.json` and logs readiness.
5. **Supervision loop:** Monitors children. If any child exits unexpectedly, all remaining children are terminated.
6. **Graceful shutdown:** Upon receiving `SIGTERM` or `SIGINT`, sends `SIGTERM` to child process groups, waits up to 10 seconds for clean exit, falls back to `SIGKILL` if processes linger, and unlinks `runtime.json`.

All supervisor events and interleaved child outputs are recorded in `<data_root>/server/runtime.log` with ISO-8601 UTC timestamps and source tags (`[supervisor]`, `[api]`, `[matte]`).
The job queue additionally logs generation progress to `<data_root>/server/server.log`.

## Exit codes

| Code | Meaning |
| :--- | :--- |
| `0` | Clean termination following `SIGTERM` or `SIGINT` |
| `1` | Startup failure, port conflict, health check timeout, or missing dependencies |
| `N` | Exit code inherited from child process if a child exited prematurely |

## `scripts/lp` CLI commands

The `scripts/lp` executable provides management commands:

| Command | Action |
| :--- | :--- |
| `scripts/lp root` | Print the resolved data root directory |
| `scripts/lp setup` | Create layout, initialize runtime venv, and build web assets |
| `scripts/lp up [--foreground] [--no-matte]` | Launch the background or foreground supervisor |
| `scripts/lp down` | Gracefully terminate the running supervisor and workers |
| `scripts/lp status` | Report process health, active port, version, and loaded engine |
| `scripts/lp logs [--lines N] [-f] [--jobs]` | View latest entries from `runtime.log` or `server.log` |
| `scripts/lp exec ARGS...` | Run arbitrary commands within the runtime venv and environment |
| `scripts/lp doctor` | Run comprehensive diagnostics on layout, venv, engines, and sandbox |

See [Running headlessly with the CLI](../operations/run-headless.md) for operational examples.
