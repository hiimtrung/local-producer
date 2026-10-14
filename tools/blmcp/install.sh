#!/usr/bin/env bash
# Install Blender Lab's MCP server (blmcp) into tools/blmcp/.venv (not committed), pinned to a known commit.
# Blender side: install the "MCP" add-on from the Blender Lab extensions repository (https://lab.blender.org/),
# it listens on localhost:9876. .mcp.json starts this venv's server for Claude Code.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
commit=${BLMCP_COMMIT:-dbbf836ad4b1025f14a2b3b504c43903f39e0b04}
uv venv -q --allow-existing -p 3.12 "$here/.venv"
VIRTUAL_ENV="$here/.venv" uv pip install -q "git+https://projects.blender.org/lab/blender_mcp.git@$commit#subdirectory=mcp"
"$here/.venv/bin/python" -c "import blmcp; print('blmcp installed:', blmcp.__file__)"
