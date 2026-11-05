# 0005. Loopback-only server, token on by default

| | |
| :--- | :--- |
| **Status** | Accepted — implementation starts in P1 |
| **Owner** | maintainer |
| **Last verified** | 2026-11-05 |
| **Date** | 2026-11-05 |

## Context

The server has no accounts. Its token (`SERVER_TOKEN`) is optional and off by default. The API can upload images,
delete jobs, download results and — the part that matters — **add a model from any http(s) link or an uploaded file**
into the models directory, where an engine CLI will parse it.

On a loopback-only server that is a local-trust model: the user is the only caller. Exposed on a LAN it becomes
"anyone on this network can write a file of their choosing into a directory that a GPU binary parses", which is
precisely the scenario the engine sandbox exists for. Plain HTTP would also send the token in cleartext on a network
the user does not control (hotel, cafe, shared office).

The Blender add-on is a second local client: it needs to find the port and authenticate without the user copying a
token by hand.

## Decision

We bind to `127.0.0.1` only and turn authentication on by default.

- The server listens on loopback. There is no LAN mode in v1 and no `0.0.0.0` binding option in the UI.
- The token is generated on first start, stored in the data root with owner-only permissions, and required for every
  state-changing request.
- The shell and any local client obtain the token through `GET /v1/session` on loopback, or read it from
  `<data>/runtime.json`. The browser UI uses a `SameSite=Strict` cookie; requests are checked against an allowed
  `Origin`.
- The Blender add-on reads `runtime.json` (port + token) instead of a hard-coded `127.0.0.1:13305`, so a port change
  does not require editing preferences.
- If a "share on the network" mode is ever added, the token remains mandatory, the bound interface is an explicit
  choice, and the cleartext-HTTP warning is shown — never "open without a token".

## Consequences

- The API's threat model stays "local user", which is the only model the code was written for. No account system, no
  password reset, no user database.
- The add-on can connect with zero configuration, which removes the most common support question.
- The token must not leak into logs or error responses; that becomes a test, not a convention.
- Remote rendering and team use are impossible without a later, explicit mode. That is accepted for v1.

## Alternatives considered

- **LAN with an optional token (today's behaviour)**: rejected — "optional token" is the configuration that gets
  shipped with the token off.
- **LAN + token + TLS with a self-signed certificate**: rejected for v1 — certificate trust on every client is a
  product problem of its own; it belongs to the same later mode as LAN, not to the first release.
- **No token at all, relying on loopback**: rejected — any local process (including a browser page via a form post
  that escapes the Origin check) could drive the API. The token is cheap and makes that class of bug non-exploitable.
- **Unix domain socket instead of HTTP**: rejected — the Blender add-on and the browser UI both speak HTTP; a socket
  would need a proxy and would add a second transport to maintain.

## What would reopen this

A concrete request to drive the server from another machine (a render box, or team use). That request reopens the
transport question as a whole — interface selection, TLS, and token lifecycle — rather than loosening this decision.
