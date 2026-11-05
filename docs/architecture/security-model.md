# Native security model

| | |
| :--- | :--- |
| **Status** | Active |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Applies to** | all platforms |

This document explains the security architecture of the native runtime, detailing how isolation,
sandboxing, network boundaries, and resource limits mitigate risks on user workstations.
For vulnerability reporting procedures and the formal policy, consult the project [Security policy](../../SECURITY.md).

## Loopback binding invariant

The local-producer server executes native code on the GPU and stores model files on the host filesystem.
To prevent unauthorized remote access, the server enforces strict network boundaries:

- **Loopback address:** The API server and the matting worker bind strictly to `127.0.0.1`.
- **No external interface exposure:** Services never bind to `0.0.0.0` or public network adapters.
- **Remote usage requirement:** Exposing the server across a local network or the internet is unsupported without a reverse proxy providing TLS termination and mutual authentication.

## Authentication and token status

An optional bearer token (`SERVER_TOKEN`) can be passed via the environment to protect API endpoints using constant-time comparison.
In the current phase, the supervisor does not generate a mandatory token by default when running headlessly on loopback.
The static web UI and the Blender add-on index repository (`/blender/index.json`) remain accessible without tokens to permit local installations.

## Engine process sandbox

The server executes binary runners (`sd-cli`, `trellis-cli`) to perform diffusion and 3D mesh reconstruction.
Because these runners parse complex binary files (GGUF, safetensors, PNGs), they are isolated to prevent network communication in the event of an exploit:

### macOS sandbox implementation

On macOS, engine processes are wrapped with `/usr/bin/sandbox-exec` using a restrictive Seatbelt profile:

```scheme
(version 1)(allow default)(deny network*)
```

This profile permits normal compute operations, file access, and Metal GPU acceleration while explicitly blocking all network socket operations.

### Linux sandbox implementation

On Linux systems, engine processes run through Bubblewrap (`bwrap`):

```bash
bwrap --unshare-net --dev-bind / / -- <runner> <args...>
```

Bubblewrap unshares the network namespace (`--unshare-net`) without requiring root privileges. This prevents child processes from establishing inbound or outbound connections.

### Blocking policy

Sandboxing is a mandatory requirement. If `/usr/bin/sandbox-exec` is unavailable on macOS, or if `bwrap` is missing or fails its runtime probe on Linux, engine initialization is **blocked**.
Executing engine CLIs unsandboxed requires explicit written authorization from maintainers.

## Residual filesystem risk

The native sandbox denies network access but permits filesystem read and write access for the invoking user.
Engine CLIs do not run in a complete filesystem chroot jail because they require direct access to model weights, temporary directories, system drivers (`/dev/dri`, `/dev/kfd`), and output folders.

The residual risk is that a vulnerable binary parser could read or overwrite files owned by the user running the server.
This risk is mitigated by:

1. **Strict catalog pinning:** Official weights and engine binaries are validated against pinned SHA256 hashes from immutable releases.
2. **Model inspection:** User-supplied models are restricted to `.gguf` and `.safetensors` headers; executable formats (such as PyTorch pickle weights) are strictly rejected.
3. **Network denial:** Even if memory corruption occurs, the sandboxed process cannot exfiltrate data over the network.

## Content Security Policy (CSP)

The web frontend is served with a strict Content Security Policy defined in `server/app/security.py`:

```http
default-src 'self';
script-src 'self' 'wasm-unsafe-eval';
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:;
connect-src 'self' ws:;
frame-ancestors 'none';
object-src 'none';
```

Key guarantees:
- **No external CDN dependencies:** All JavaScript, fonts, and assets are bundled locally in `web/dist`.
- **Restricted WebAssembly:** `'wasm-unsafe-eval'` permits WebAssembly runtime compilation required by 3D viewers (such as meshopt decoders) while maintaining full blocks on JavaScript `eval()`.
- **Clickjacking defense:** `frame-ancestors 'none'` prevents embedding the interface into unauthorized external iframes.

## Request limits and upload caps

To guard against resource exhaustion and denial of service, incoming requests are capped:

| Limit | Value | Enforcement |
| :--- | :--- | :--- |
| Maximum request body | 48 MiB | Capped before parsing JSON or base64 payloads |
| Maximum input image | 32 MiB | Checked against raw payload bytes |
| Maximum prompt length | 4000 characters | Enforced during Pydantic schema validation |
| Image validation | Magic byte inspection | Enforced before decoding image buffers |
| Identifier sanitization | Fixed hex regex `^[0-9a-f]{32}$` | Directory traversal via filenames is rejected |

For operational troubleshooting and sandbox diagnostics, see [Troubleshooting runtime issues](../operations/troubleshooting.md).
