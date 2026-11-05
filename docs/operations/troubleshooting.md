# Troubleshooting runtime issues

| | |
| :--- | :--- |
| **Status** | Active |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Applies to** | all platforms |

This guide addresses common failures encountered when starting, running, or diagnosing local-producer.

## Diagnostics first: `lp doctor`

Before applying manual fixes, run the automated diagnostic tool:

```bash
scripts/lp doctor
```

`lp doctor` inspects data root layout permissions, Python environment packages, engine catalog status,
sandbox enforcement, and port availability.

## Engine execution blocked

Engine execution is strictly guarded by preflight assertions and sandbox requirements.

### 1. AMD ROCm gfx1103: `cwsr_enable` requirement

On AMD Radeon 780M / gfx1103 iGPUs, hardware compute waves cannot be preempted reliably under certain kernel versions.
Without disabling Compute Wave Save Restore (CWSR), long HIP generation jobs cause GPU ring timeouts and hardware resets.

**Symptom:**
Engine preflight reports that `cwsr_enable` is 1, and engine loading is blocked.

**Fix:**
Set the module option as root and reboot:

```bash
echo 'options amdgpu cwsr_enable=0' | sudo tee /etc/modprobe.d/amdgpu-cwsr.conf
sudo update-initramfs -u  # or your distribution equivalent
sudo reboot
```

After rebooting, verify:

```bash
cat /sys/module/amdgpu/parameters/cwsr_enable
```

The output must be `0`.

### 2. Missing Linux sandbox: `bwrap`

On Linux, engine CLIs must be executed under Bubblewrap to isolate network access.

**Symptom:**
`lp doctor` or the supervisor reports:
`bwrap is missing (apt install bubblewrap); running engine CLIs unsandboxed needs written approval`

**Fix:**
Install Bubblewrap using your system package manager:

```bash
# Ubuntu / Debian
sudo apt-get install bubblewrap

# Fedora / RHEL
sudo dnf install bubblewrap

# Arch Linux
sudo pacman -S bubblewrap
```

### 3. Missing or unconfigured engine package

**Symptom:**
`lp status` reports `no engine package loaded`.

**Fix:**
Install the platform engine package via the web UI under **Server > Engines**, or install from the CLI:

```bash
scripts/lp exec make engines
```

## Port conflicts

### 1. Matting port 8083 in use

The matting worker binds strictly to `127.0.0.1:8083`. If another process occupies this port, startup aborts.

**Diagnosis:**
Inspect what process holds port 8083:

```bash
# macOS
lsof -iTCP:8083 -sTCP:LISTEN

# Linux
ss -tulpn | grep :8083
```

**Fix:**
Terminate the conflicting process or shut down any lingering instances:

```bash
scripts/lp down
```

### 2. Primary API port 13305 taken

The API server attempts to bind `127.0.0.1:13305`. If occupied, the supervisor automatically selects an ephemeral port
and records it in `<data_root>/server/runtime.json`.
Check `scripts/lp status` or read `runtime.json` to identify the active URL.

## Missing or stale web build

**Symptom:**
Navigating to `http://127.0.0.1:13305` yields HTTP 404 or a blank screen.

**Fix:**
Compile the web frontend:

```bash
make web-build
```

Ensure Node.js 24 is installed. The build produces artifacts in `web/dist`.

## Virtual environment and dependency issues

If Python dependencies fail to load or report version mismatches:

**Fix:**
Rebuild the runtime virtual environment:

```bash
scripts/lp setup
```

To recreate the development virtual environment in the repository:

```bash
uv sync --reinstall
```

## GPU resets and kernel ring timeouts

If generation jobs abort with process termination or device lost errors, verify whether the kernel initiated a GPU reset:

```bash
# On Linux
journalctl -k -b | grep -c -E 'GPU reset begin|ring .* timeout'
```

If timeouts occur, ensure `cwsr_enable=0` is configured and that memory limits are not exceeded.

## Log file locations

When debugging unexpected crashes, examine the service logs:

| Log file | Purpose | Command |
| :--- | :--- | :--- |
| `<data_root>/server/runtime.log` | Supervisor events and interleaved stdout/stderr | `scripts/lp logs` |
| `<data_root>/server/server.log` | API server and GPU job execution traces | `scripts/lp logs --jobs` |
