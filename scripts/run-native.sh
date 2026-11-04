#!/usr/bin/env bash
# The local-producer server on macOS (Apple silicon), natively: containers cannot reach Metal, so server/app on
# 127.0.0.1:13305 (web UI, API, job queue) and the matting server on 127.0.0.1:8083 run as host processes under one
# supervisor, which stops both when either exits (like the container). Same layout as the container otherwise:
# models and engines in plain directories, library and state as on Linux (scripts/lp-env.sh). The engine package's
# CLIs start under a network-denying sandbox (server/app/engines/registry.py).
#   scripts/run-native.sh start     set up what is missing, start, wait until ready (make server-up)
#   scripts/run-native.sh stop      stop the server and any job's CLI (make server-down)
#   scripts/run-native.sh status    is it running
#   scripts/run-native.sh setup     only create / update the Python environment and build the web UI
#   scripts/run-native.sh python …  run the server's Python in server/ with the server's environment (Makefile tools)
# The Python environment ($LP_VENV, Python 3.12 like the image) is installed with uv from the hashed
# server/requirements-macos.txt and rebuilt when that file changes. Logs: $STATE_DIR/server.log (jobs),
# $STATE_DIR/native.log (startup, matting). Extra app.main options via SERVER_ARGS; SERVER_TOKEN as in the container.
# Written for the bash 3.2 that macOS ships.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lp-env.sh
source "$root/scripts/lp-env.sh"
pidfile="$STATE_DIR/native.pid"
lock="$root/server/requirements-macos.txt"

die() {
    echo "$*" >&2
    exit 1
}

setup_python() {
    local want stamp="$LP_VENV/.requirements.sha256"
    want="$(shasum -a 256 "$lock" | cut -c1-64)"
    if [[ -x "$LP_VENV/bin/python" && "$(cat "$stamp" 2>/dev/null)" == "$want" ]]; then
        return
    fi
    command -v uv >/dev/null || die "uv is needed for the server's Python environment: https://docs.astral.sh/uv/"
    echo "setting up the server's Python environment in $LP_VENV"
    uv venv --quiet --python 3.12 --allow-existing "$LP_VENV"
    uv pip sync --quiet --python "$LP_VENV/bin/python" --require-hashes "$lock"
    echo "$want" >"$stamp"
}

setup_web() {  # build web/dist when it is missing or older than its sources
    local index="$root/web/dist/index.html"
    if [[ -f "$index" ]] && [[ -z "$(find "$root/web/src" "$root/web/styles" "$root/web/vendor" -newer "$index" \
        -type f -print -quit)" ]]; then
        return
    fi
    command -v npm >/dev/null || die "Node.js 24 with npm is needed to build the web UI"
    echo "building the web UI"
    if [[ ! -d "$root/web/node_modules" ]]; then
        (cd "$root/web" && npm ci --ignore-scripts --no-audit --silent)
    fi
    (cd "$root/web" && npx tsc --noEmit -p . && node build.mjs)
}

running() {
    [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

kill_tree() {  # a process and all its descendants, children first (a job's sd-cli / trellis-cli included)
    local child
    for child in $(pgrep -P "$1" 2>/dev/null); do
        kill_tree "$child"
    done
    kill "$1" 2>/dev/null || true
}

supervise() {  # runs detached (start); stops both servers when either exits or on SIGTERM
    cd "$root/server"
    "$LP_VENV/bin/python" -W ignore matte_server.py --host 127.0.0.1 --port 8083 &
    local matte=$!
    # shellcheck disable=SC2086  # SERVER_ARGS: extra options, split on whitespace on purpose
    "$LP_VENV/bin/python" -m app.main --host 127.0.0.1 --port 13305 ${SERVER_ARGS:-} &
    local gpu=$!
    trap 'kill_tree "$matte"; kill_tree "$gpu"' TERM INT
    while kill -0 "$matte" 2>/dev/null && kill -0 "$gpu" 2>/dev/null; do
        sleep 1
    done
    kill_tree "$matte"
    kill_tree "$gpu"
    wait
}

start() {
    if running; then
        echo "already running (pid $(cat "$pidfile")): http://127.0.0.1:13305"
        return
    fi
    [[ "$(uname -m)" == arm64 ]] || echo "warning: no engine package for Intel Macs; the GPU pages will stay empty" >&2
    lp_volumes
    setup_python
    setup_web
    lp_native_env
    echo "== $(date '+%Y-%m-%d %H:%M:%S') native start" >>"$STATE_DIR/native.log"
    nohup env "${LP_ENV[@]}" "$0" _supervise >>"$STATE_DIR/native.log" 2>&1 &
    echo $! >"$pidfile"
    # The first start downloads rembg's matting model (~180 MB) before the matting server answers.
    local said=
    for _ in $(seq 900); do
        if [[ -z "$said" ]] && curl -sf http://127.0.0.1:13305/health >/dev/null; then
            [[ -d "$MODELS_DIR/rembg/models/isnet-general-use" ]] && [[ -n "$(find "$MODELS_DIR/rembg" -name '*.onnx')" ]] ||
                echo "server up; waiting for the matting model download (first start only, ~180 MB)"
            said=1
        fi
        if curl -sf http://127.0.0.1:13305/health >/dev/null && curl -sf http://127.0.0.1:8083/health >/dev/null; then
            echo "ready: open http://127.0.0.1:13305 (web UI and API); matting on http://127.0.0.1:8083"
            echo "engine: $(curl -sf http://127.0.0.1:13305/v1/system | "$LP_VENV/bin/python" -c \
                'import json,sys; e=json.load(sys.stdin)["engine"]; print(e["state"], e["id"], e["version"], e["problem"])')"
            echo "models: $MODELS_DIR, engines: $ENGINES_DIR, library: $LIBRARY_DIR, logs: $STATE_DIR"
            return
        fi
        running || die "the server exited; see $STATE_DIR/native.log"
        sleep 1
    done
    die "the server did not become ready; see $STATE_DIR/native.log"
}

stop() {
    if ! running; then
        echo "not running"
        rm -f "$pidfile"
        return
    fi
    local pid
    pid="$(cat "$pidfile")"
    kill_tree "$pid"
    for _ in $(seq 20); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
    done
    rm -f "$pidfile"
    echo "stopped"
}

case "${1:-start}" in
    start) start ;;
    stop) stop ;;
    status) if running; then echo "running (pid $(cat "$pidfile"))"; else echo "not running"; exit 1; fi ;;
    setup) lp_volumes && setup_python && setup_web ;;
    python)
        shift
        lp_volumes
        setup_python
        lp_native_env
        cd "$root/server"
        exec env "${LP_ENV[@]}" "$LP_VENV/bin/python" "$@"
        ;;
    _supervise) supervise ;;
    *) die "usage: $0 [start|stop|status|setup|python ARGS...]" ;;
esac
