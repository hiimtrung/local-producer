# Runtime configuration reference

| | |
| :--- | :--- |
| **Status** | Active |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Applies to** | all platforms |

This document details the configuration parameters, defaults, validation bounds, and environment variables
that control the local-producer runtime.

## User configuration: `RuntimeConfig`

Settings that users can customize via the web UI (**Server > Settings**) or through `PUT /v1/config` are defined by
`app.settings.RuntimeConfig`. These settings are persisted atomically as JSON in `<data_root>/server/config.json`.

| Field | Type | Default | Bounds | Description |
| :--- | :--- | :--- | :--- | :--- |
| `image_steps` | Integer | `4` | `1 <= n <= 50` | Default FLUX.2 denoising steps. 4 steps corresponds to the measured quality sweet spot. |
| `mesh_steps` | Integer | `8` | `1 <= n <= 50` | Default TRELLIS.2 flow steps per stage. |
| `mesh_resolution` | Integer | `512` | `512`, `1024`, `1536` | Target resolution for generated 3D meshes. |
| `job_timeout_s` | Integer | `7200` | `60 <= n <= 86400` | Maximum execution time in seconds before a stalled job is killed (default 2 hours). |
| `keep_jobs` | Integer | `200` | `10 <= n <= 5000` | Maximum number of finished job records and results retained in `library/jobs/`. |
| `keep_uploads` | Integer | `500` | `10 <= n <= 5000` | Maximum number of uploaded source images retained in `library/uploads/`. |

Changes to these fields are validated against Pydantic schema constraints. Submitting values outside the allowed bounds
raises a `422 Unprocessable Entity` response and leaves the existing configuration unmodified.

## Architectural hard limits

Hard limits protect server memory and compute stability. They are constants defined in code and cannot be modified via configuration:

| Constant | Value | Purpose |
| :--- | :--- | :--- |
| `MAX_BODY_BYTES` | 48 MiB (`48 * 2^20`) | Maximum HTTP request payload size (protects against memory exhaustion). |
| `MAX_IMAGE_BYTES` | 32 MiB (`32 * 2^20`) | Maximum decompressed size of uploaded image files. |
| `MAX_PROMPT_CHARS` | 4000 characters | Maximum length of text generation prompts. |

## Environment variables

Environment variables configure paths, runtime isolation, and thread counts.

### Data root and path overrides

| Variable | Default value | Purpose |
| :--- | :--- | :--- |
| `LP_HOME` | System default data root | Overrides the base data root path for models, engines, library, and server state. |
| `MODELS_DIR` | `<data_root>/models` | Overrides the location where model weights are stored and resolved. |
| `ENGINES_DIR` | `<data_root>/engines` | Overrides the location where engine packages are unpacked. |
| `LIBRARY_DIR` | `<data_root>/library` | Overrides where job results and uploads are persisted. |
| `DATA_DIR` | `<data_root>/server` | Overrides the directory containing `config.json`, logs, and `runtime.json`. |
| `WEB_DIR` | `<repo_root>/web/dist` | Overrides the directory containing precompiled web frontend static assets. |
| `ADDON_DIR` | `<repo_root>/blender/local_producer` | Overrides the location of the Blender add-on source files. |
| `U2NET_HOME` | `<data_root>/models/rembg` | Overrides the cache directory for rembg matting weights. |

### Process execution and security

| Variable | Default value | Purpose |
| :--- | :--- | :--- |
| `SERVER_TOKEN` | Empty (none) | Bearer authentication token for securing HTTP API endpoints. |
| `OMP_NUM_THREADS` | Derived compute cores | Sets OpenMP thread counts for native compute libraries. Derived from physical performance cores. |
| `PYTHONDONTWRITEBYTECODE` | `1` | Disables Python bytecode compilation inside runtime directories. |
| `PYTHONUNBUFFERED` | `1` | Forces real-time flushing of stdout and stderr into log files. |

For operational details on directory maintenance, consult [Native filesystem storage layout](storage.md).
