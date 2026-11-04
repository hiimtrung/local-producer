# shellcheck shell=bash
# shellcheck disable=SC2034  # LP_MOUNTS, LP_GPU, LP_ENV and LP_VENV are read by the scripts that source this file
# Where the server keeps its data, shared by scripts/run-server.sh and the Makefile (source it; bash).
#   models   weights                -> Podman volume $MODELS_VOLUME   (portable across engines)
#   engines  engine packages        -> Podman volume $ENGINES_VOLUME  (GPU runtime + CLI builds for this machine)
#   library  job results, uploads   -> host directory $LIBRARY_DIR    (what the Library page shows)
#   state    config.json, logs      -> host directory $STATE_DIR      (server.log: the add-on's "Server Log")
# Named volumes live on the same disk as the Podman storage (~/.local/share/containers/storage/volumes), outside any
# image layer, and survive image rebuilds; `podman volume rm` (or `podman system prune --volumes`) deletes them.
# macOS (LP_NATIVE=1): the server runs natively (containers cannot reach Metal, scripts/run-native.sh), so models and
# engines are plain directories $MODELS_DIR and $ENGINES_DIR, and the server's Python lives in $LP_VENV.
LP_HOME=${LP_HOME:-$HOME/.local-producer}
LIBRARY_DIR=${LIBRARY_DIR:-$LP_HOME/library}
STATE_DIR=${STATE_DIR:-$LP_HOME/server}
MODELS_VOLUME=${MODELS_VOLUME:-local-producer-models}
ENGINES_VOLUME=${ENGINES_VOLUME:-local-producer-engines}
if [[ "$(uname -s)" == Darwin ]]; then LP_NATIVE=1; else LP_NATIVE=; fi
MODELS_DIR=${MODELS_DIR:-$LP_HOME/models}
ENGINES_DIR=${ENGINES_DIR:-$LP_HOME/engines}
LP_VENV=${LP_VENV:-$LP_HOME/venv}

lp_volumes() {  # create what is missing; print nothing
    mkdir -p "$LIBRARY_DIR" "$STATE_DIR"
    if [[ -n "$LP_NATIVE" ]]; then
        mkdir -p "$MODELS_DIR" "$ENGINES_DIR"
        return
    fi
    local v
    for v in "$MODELS_VOLUME" "$ENGINES_VOLUME"; do
        podman volume exists "$v" || podman volume create "$v" >/dev/null
    done
}

lp_mountpoint() {  # host path of a volume
    if [[ -n "$LP_NATIVE" ]]; then
        case "$1" in "$MODELS_VOLUME") echo "$MODELS_DIR" ;; "$ENGINES_VOLUME") echo "$ENGINES_DIR" ;; esac
        return
    fi
    podman volume inspect --format '{{.Mountpoint}}' "$1"
}

# The podman run options that mount everything at the paths the image expects (app/settings.py).
lp_mounts() {
    LP_MOUNTS=(
        -v "$MODELS_VOLUME":/models -v "$ENGINES_VOLUME":/engines
        -v "$LIBRARY_DIR":/library -v "$STATE_DIR":/data
        -e HOST_MODELS="Podman volume $MODELS_VOLUME" -e HOST_ENGINES="Podman volume $ENGINES_VOLUME"
        -e HOST_LIBRARY="$LIBRARY_DIR" -e HOST_DATA="$STATE_DIR"
    )
}

# The environment of the native server (macOS): the same variables the image sets (server/Containerfile).
lp_native_env() {
    LP_ENV=(
        MODELS_DIR="$MODELS_DIR" ENGINES_DIR="$ENGINES_DIR" LIBRARY_DIR="$LIBRARY_DIR" DATA_DIR="$STATE_DIR"
        HOST_MODELS="$MODELS_DIR" HOST_ENGINES="$ENGINES_DIR" HOST_LIBRARY="$LIBRARY_DIR" HOST_DATA="$STATE_DIR"
        U2NET_HOME="$MODELS_DIR/rembg" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
        # rembg on the performance cores: M4 4P+6E, cat sample 1.48 s mean with 4 vs 1.62 s with 10 (n=4 each, CHANGELOG)
        OMP_NUM_THREADS="${OMP_NUM_THREADS:-$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null || echo 4)}"
    )
}

# GPU devices for the container: ROCm (/dev/kfd + /dev/dri) or NVIDIA (CDI, needs nvidia-container-toolkit).
lp_gpu() {
    if [[ -e /dev/kfd ]]; then
        LP_GPU=(--device /dev/kfd --device /dev/dri --group-add keep-groups)
    elif [[ -e /dev/nvidiactl ]]; then
        LP_GPU=(--device nvidia.com/gpu=all)
    else
        LP_GPU=()
    fi
}
