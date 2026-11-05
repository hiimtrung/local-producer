# Running headlessly with the CLI

| | |
| :--- | :--- |
| **Status** | Active |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Applies to** | all platforms |

This guide describes how to operate local-producer as a headless background service using the `scripts/lp` CLI.

## Quick CLI reference

The `scripts/lp` script provides commands to control setup, supervision, and inspection:

```bash
scripts/lp setup      # Prepare directories, initialize runtime venv, and build web assets
scripts/lp up         # Launch background supervisor and verify service health
scripts/lp status     # Show active endpoint, process ID, version, and engine state
scripts/lp logs -f    # Stream consolidated supervisor and service logs
scripts/lp down       # Gracefully stop supervisor, API, and matting processes
scripts/lp doctor     # Perform system diagnostics and preflight checks
```

## Detailed command usage

### 1. Preparing the environment: `lp setup`

Before starting the server for the first time or after updating dependencies, run setup:

```bash
scripts/lp setup
```

This command:
- Resolves the data root and creates required layout directories (`models/`, `engines/`, `library/`, `server/`, `venv/`).
- Populates the runtime virtual environment at `<data_root>/venv` using `uv` from platform locks (`requirements.macos.txt` or `requirements.linux.txt`).
- Builds the web frontend in `web/dist` if not already compiled.

To migrate an older installation from `~/.local-producer`, use:

```bash
scripts/lp setup --migrate
```

See [Backup and data migration](backup-and-migrate.md) for details on data migration.

### 2. Starting services: `lp up`

Launch the server stack in the background:

```bash
scripts/lp up
```

Options:
- `--foreground`: Run the supervisor attached to the current terminal instead of daemonizing into the background.
- `--no-matte`: Skip launching the background removal worker (`matte_server.py`) if memory is constrained.

When launched, `lp up` waits up to 180 seconds for both the API server and matting worker to report HTTP 200 on `/health`.
Upon success, it prints the active URL and the location of `runtime.log`.

### 3. Monitoring status: `lp status`

Check whether the server is running and healthy:

```bash
scripts/lp status
```

Sample output:

```
local-producer 0.15.0 is healthy (pid 48215)
  URL:    http://127.0.0.1:13305
  Engine: metal-arm64 v0.8.1 (loaded)
```

The command checks that the process ID from `runtime.json` is active and that the `/health` endpoint responds.
If the supervisor crashed or was terminated unexpectedly, `lp status` reports the stale PID and exits with code 1.

### 4. Viewing log streams: `lp logs`

Inspect real-time logs:

```bash
scripts/lp logs              # View last 10 lines of runtime.log
scripts/lp logs --lines 50   # View last 50 lines
scripts/lp logs -f           # Follow log output live
scripts/lp logs --jobs       # View generation job logs from server.log
```

`runtime.log` captures tagged log lines from the supervisor, the FastAPI server (`[api]`), and the background removal service (`[matte]`).

### 5. Stopping services: `lp down`

Shut down all processes cleanly:

```bash
scripts/lp down
```

The command sends `SIGTERM` to the supervisor's process group, allows up to 10 seconds for graceful shutdown, and verifies that loopback ports are freed.

### 6. System diagnostics: `lp doctor`

Diagnose system dependencies, sandbox capabilities, GPU preflight checks, and disk usage:

```bash
scripts/lp doctor
```

Sample output:

```
local-producer doctor:
  Data root:     /Users/user/Library/Application Support/local-producer
  Platform:      macos (arm64)
  Python venv:   Python 3.12.8 (/Users/user/Library/Application Support/local-producer/venv)
  Web UI:        built (/path/to/local-producer/web/dist)
  Engine:        metal-arm64 v0.8.1 (active)
  Sandbox:       sandbox-exec (/usr/bin/sandbox-exec)
  Disk free:     142.4 GB
```

## Overriding the data directory: `LP_HOME`

By default, data is stored in the standard operating system directory.
You can redirect all storage, configurations, and models by setting `LP_HOME`:

```bash
export LP_HOME="/mnt/fast-nvme/local-producer-data"
scripts/lp up
```

All `scripts/lp` commands respect the `LP_HOME` variable.

## Port selection and conflict handling

The API server requests port `13305` by default. If port `13305` is already bound by another process:
1. The supervisor selects an available ephemeral loopback port allocated by the OS.
2. The selected port is recorded in `<data_root>/server/runtime.json`.
3. Client tools and scripts automatically discover the port from `runtime.json`.

The matting worker always requires port `8083`. If port `8083` is occupied, startup fails with an actionable error.

## Systemd user service configuration (Linux)

> [!NOTE]
> The following systemd unit example is **untested** in production environments. Test thoroughly before relying on it for automated server management.

To run local-producer automatically under systemd user mode on Linux, create `~/.config/systemd/user/local-producer.service`:

```ini
[Unit]
Description=local-producer headless generation service
After=network.target

[Service]
Type=exec
WorkingDirectory=%h/local-producer
ExecStart=%h/local-producer/scripts/lp exec python -m app.supervisor --port 13305
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
```

Enable and start the service with:

```bash
systemctl --user daemon-reload
systemctl --user enable --now local-producer.service
```
