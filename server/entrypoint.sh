#!/bin/bash
# Run the matting server and the GPU job server side by side; stop both when either exits or on SIGTERM (podman stop).
# SERVER_ARGS: extra server.py options, split on whitespace on purpose.
set -u
# Keep the container's own output after it exits (the container runs with --rm): /data = models/server/.
exec > >(tee -a /data/container.log) 2>&1
python -W ignore /opt/lp/server/matte_server.py --port 8083 &
matte=$!
# shellcheck disable=SC2086
python -m app.main --port 13305 ${SERVER_ARGS:-} &
gpu=$!
# Wait for these two PIDs only: a bare `wait` would also wait for the tee above, which never ends.
trap 'kill "$matte" "$gpu" 2>/dev/null' TERM INT
wait -n "$matte" "$gpu"
status=$?
kill "$matte" "$gpu" 2>/dev/null
wait "$matte" "$gpu"
exit "$status"
