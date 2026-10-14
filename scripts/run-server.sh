#!/usr/bin/env bash
# Start the local-producer server container (rootless Podman): server/app on 127.0.0.1:13305 (web UI, API, job queue)
# and the matting server on 127.0.0.1:8083. The image holds no GPU code: the engine package for this machine (GPU
# runtime + CLI builds) is installed at run time into the engines volume, the weights into the models volume (the
# web UI's Server > Engines / Models pages, the add-on's "Download Models", or `make setup`). Storage: scripts/lp-env.sh.
# ROCm on gfx1103 needs the host kernel parameter amdgpu cwsr_enable=0 (README.md); otherwise the engine is not loaded.
# Ports are published on 127.0.0.1 only: the server has no user accounts (optional SERVER_TOKEN, see server/app/security.py).
# The image is built on the first start; rebuild with BUILD=1. Stop: podman stop local-producer-gpu.
# Logs: $STATE_DIR/server.log (jobs), $STATE_DIR/container.log (startup, matting). Extra app.main options via SERVER_ARGS.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lp-env.sh
source "$root/scripts/lp-env.sh"
image=${IMAGE:-localhost/local-producer-gpu}
name=${NAME:-local-producer-gpu}
if [[ "$(uname -s)" == Darwin ]]; then
    echo "macOS: containers cannot reach Metal; the server will run natively with the MLX engine (coming soon)" >&2
    exit 1
fi
if [[ -n "${BUILD:-}" ]] || ! podman image exists "$image"; then
    podman build -t "$image" -f "$root/server/Containerfile" "$root"
fi
lp_volumes
lp_mounts
lp_gpu
if [[ -e /dev/kfd ]]; then
    echo "GPU resets + ring timeouts this boot (before): $(journalctl -k -b | grep -c -E 'GPU reset begin|ring .* timeout' || true)"
fi
podman run -d --rm --name "$name" -p 127.0.0.1:13305:13305 -p 127.0.0.1:8083:8083 \
    "${LP_GPU[@]}" --userns=keep-id --user "$(id -u):$(id -g)" --security-opt label=disable \
    --cap-drop=all --security-opt no-new-privileges \
    -e SERVER_ARGS="${SERVER_ARGS:-}" -e SERVER_TOKEN="${SERVER_TOKEN:-}" "${LP_MOUNTS[@]}" \
    "$image" >/dev/null
for _ in $(seq 60); do
    if curl -sf http://127.0.0.1:13305/health >/dev/null && curl -sf http://127.0.0.1:8083/health >/dev/null; then
        echo "ready: open http://127.0.0.1:13305 (web UI and API); matting on http://127.0.0.1:8083"
        echo "engine: $(curl -sf http://127.0.0.1:13305/v1/system | python3 -c 'import json,sys; e=json.load(sys.stdin)["engine"]; print(e["state"], e["id"], e["version"], e["problem"])')"
        echo "library: $LIBRARY_DIR, logs: $STATE_DIR"
        exit 0
    fi
    if ! podman container exists "$name"; then
        echo "the container exited; see $STATE_DIR/container.log" >&2
        exit 1
    fi
    sleep 1
done
echo "server did not become ready; podman logs $name" >&2
exit 1
