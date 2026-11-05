# 0003. Tauri v2 as the desktop shell

| | |
| :--- | :--- |
| **Status** | Accepted — implementation starts in P3 |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Date** | 2026-11-05 |

## Context

The product is a local GPU server with a React web UI, plus a Blender add-on that talks to the same API. Requiring a
terminal (`make server-up`) and a browser tab is acceptable for development and unacceptable for the stated goal: a
person installs an app, the app downloads its models, and images and meshes come out.

The UI already exists and is framework-independent (esbuild + React 18, no server-side rendering). Whatever shell is
chosen must therefore load an existing HTTP app, supervise the Python server, and stay out of the way of the GPU. It
must not require a Python installation, a Node installation, or a compiler on the user's machine.

## Decision

We ship a **Tauri v2** desktop application, macOS arm64 first, Linux later, no Windows in v1.

- The shell starts and supervises the Python server (see [0002](./0002-native-runtime-no-containers.md)), waits for
  `/v1/health`, then loads `http://127.0.0.1:<port>` in the system web view.
- The shell owns the user-facing lifecycle: quit confirmation while a job runs, kill-tree on exit, "delete my data".
- The web UI stays a plain web app; it must remain usable in a browser for development and headless use.
- macOS is the first target (arm64 only), with signing and notarization as a release gate. Linux is a `.deb` first,
  with AppImage as a fallback.
- The Blender add-on is a separate client of the same API; it is not embedded in the shell.

## Consequences

- Small installer and low idle memory compared with Electron, because the system web view is used instead of a bundled
  Chromium. This matters on a 16 GiB machine that gives most of its memory to models.
- **The rendering engine differs per OS**: WKWebView on macOS, WebKitGTK on Linux. `<model-viewer>`/three.js must be
  measured in WebKitGTK; if WebGL is unusable there, the fallback is the CPU renderer, which is slow. This risk is
  accepted and belongs to P6, not to the macOS v1.
- The Rust toolchain and the Tauri CLI enter the build; CI gains a desktop build job.
- Two processes to reason about (shell + Python server) instead of one. The supervisor contract and `runtime.json`
  exist to keep that manageable.
- Signing, notarization and hardened-runtime behaviour with downloaded dylibs are release work, not a detail.

## Alternatives considered

- **Electron**: rejected — a bundled Chromium adds hundreds of megabytes and substantial idle memory for a UI that is
  already a web app; the benefit (one rendering engine everywhere) does not outweigh the cost here.
- **A native Swift/AppKit app**: rejected — it would either duplicate the UI or embed a web view anyway, while adding a
  second UI codebase and locking out Linux.
- **Browser-only, no shell**: rejected — it is today's state and fails the "no Terminal" requirement: the server must
  be started, updated and stopped by something.
- **Tauri v1**: rejected — v2 is the current line, with the plugin and updater work this app needs.

## What would reopen this

WebKitGTK failing the WebGL measurement badly enough that the Linux UI is unusable, or a Tauri limitation that blocks
the supervisor/updater contract. In either case the shell is replaceable: the UI is an HTTP app, which is why this
decision is contained.
