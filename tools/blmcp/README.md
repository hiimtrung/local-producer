# Blender MCP server (blmcp)

Not vendored: `./install.sh` installs [Blender Lab's MCP server](https://projects.blender.org/lab/blender_mcp)
(GPL-3.0) into `tools/blmcp/.venv`, pinned to a commit. Needs `uv`.

- Claude Code starts it from `.mcp.json` (`tools/blmcp/.venv/bin/python -m blmcp`).
- It talks to the "MCP" add-on inside a running Blender GUI on `localhost:9876`
  (install the add-on from the Blender Lab extensions repository, `https://lab.blender.org/`).
- Scripts can drive Blender without the MCP client:
  `tools/blmcp/.venv/bin/python -c 'from blmcp.tools_helpers.connection import send_code; print(send_code("import bpy\nresult = {\"v\": bpy.app.version_string}", True))'`
