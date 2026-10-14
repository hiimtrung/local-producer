#!/usr/bin/env bash
# Pack blender/local_producer/ into dist/local_producer.zip for Blender's "Install from Disk..." (legacy add-on zip).
# The raw (un-matted) sample is left out; only the RGBA sample the add-on uses is shipped.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$root/dist"
rm -f "$root/dist/local_producer.zip"
cd "$root/blender"
zip -qr "$root/dist/local_producer.zip" local_producer -x '*/__pycache__/*' '*_raw.png'
echo "$root/dist/local_producer.zip"
