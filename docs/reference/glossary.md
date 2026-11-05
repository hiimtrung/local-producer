# Local-producer glossary

| | |
| :--- | :--- |
| **Status** | Active |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Applies to** | all platforms |

This glossary defines standard terminology used across local-producer documentation, code, and interfaces.

### Data root
The canonical base directory on the host filesystem where mutable runtime assets, downloaded model weights,
engine packages, and generation results are stored. Defaults to `~/Library/Application Support/local-producer` on macOS
and `~/.local/share/local-producer` on Linux, overridable by the `LP_HOME` environment variable.

### Engine package
A self-contained directory containing native runtime libraries and binaries for a specific hardware compute platform
(for example, `rocm-gfx1103` on Linux or `metal-arm64` on Apple silicon). Engine packages are installed under
`<data_root>/engines/<id>/<version>/` and loaded dynamically without requiring server restarts.

### Headless
Operating the local-producer server and compute pipeline without a graphical desktop window or browser interface.
Headless mode is managed via the `scripts/lp` CLI and enables integration into automated scripts, remote rendering nodes,
or daemon processes.

### Job
An asynchronous compute task managed by the server's serial job queue (`server/app/jobs.py`).
Each job represents a single text-to-image, image edit, background removal, or 3D mesh reconstruction operation.
Jobs are assigned a unique 32-character hexadecimal identifier.

### Library
The persistent directory structure under `<data_root>/library/` holding input source uploads (`uploads/`) and
completed job outputs (`jobs/<id>/`), including generated images, parameters, execution logs, and exported GLB 3D files.
Also refers to the Library page in the web interface and the Library panel in the Blender add-on.

### Preflight
A series of runtime assertion checks executed before an engine package is activated or a job is started.
Preflight checks verify hardware requirements, such as driver parameters (for example, verifying `cwsr_enable=0` on gfx1103),
required system shared libraries, and sandbox availability.

### Profile
The sandboxing configuration applied to an isolated runner process.
On macOS, this refers to the Seatbelt profile string passed to `sandbox-exec` denying network access.
On Linux, it refers to the Bubblewrap command arguments (`--unshare-net --dev-bind / / --`).

### Runner
A native CLI executable provided by an engine package (specifically `sd-cli` for FLUX.2 or `trellis-cli` for TRELLIS.2)
invoked out-of-process by the server to execute compute workloads on the GPU.

### Sandbox
The OS-level isolation boundary applied to every engine runner process.
The sandbox strips network capabilities (`sandbox-exec` on macOS, `bwrap` on Linux) to prevent untrusted or exploited
model parser code from opening sockets or making network requests.

### Supervisor
The core Python process (`server/app/supervisor.py`) that manages the lifecycle of the API server and the matting worker.
The supervisor handles port allocation, health monitoring, atomic discovery file generation (`runtime.json`),
and clean process group termination upon shutdown.
