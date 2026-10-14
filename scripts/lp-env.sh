# shellcheck shell=bash
# shellcheck disable=SC2034  # LP_MOUNTS and LP_GPU are read by the scripts that source this file
# Where the server keeps its data, shared by scripts/run-server.sh and the Makefile (source it; bash).
#   models   weights                -> Podman volume $MODELS_VOLUME   (portable across engines)
#   engines  engine packages        -> Podman volume $ENGINES_VOLUME  (GPU runtime + CLI builds for this machine)
#   library  job results, uploads   -> host directory $LIBRARY_DIR    (what the Library page shows)
#   state    config.json, logs      -> host directory $STATE_DIR      (server.log: the add-on's "Server Log")
# Named volumes live on the same disk as the Podman storage (~/.local/share/containers/storage/volumes), outside any
# image layer, and survive image rebuilds; `podman volume rm` (or `podman system prune --volumes`) deletes them.
LP_HOME=${LP_HOME:-$HOME/.local-producer}
LIBRARY_DIR=${LIBRARY_DIR:-$LP_HOME/library}
STATE_DIR=${STATE_DIR:-$LP_HOME/server}
MODELS_VOLUME=${MODELS_VOLUME:-local-producer-models}
ENGINES_VOLUME=${ENGINES_VOLUME:-local-producer-engines}

lp_volumes() {  # create what is missing; print nothing
    mkdir -p "$LIBRARY_DIR" "$STATE_DIR"
    local v
    for v in "$MODELS_VOLUME" "$ENGINES_VOLUME"; do
        podman volume exists "$v" || podman volume create "$v" >/dev/null
    done
}

lp_mountpoint() {  # host path of a volume
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
