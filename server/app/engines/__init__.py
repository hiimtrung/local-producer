"""Engine packages: the platform-specific half of the server, installed and loaded at runtime.

The server image (and a native install) holds only portable code: the API, the job queue, the web UI and the
CPU matting. Everything that depends on the GPU platform lives in an engine package (catalog/engines.json): the GPU
runtime libraries and the CLI builds the pipelines run ("runners": sd-cli, trellis-cli). A package is installed as a
unit under ENGINES_DIR/<id>/<version>/, checked and loaded by registry.py, and can be switched or reloaded while
the server runs; every job starts its CLI from the loaded package, so nothing needs a restart.

  host.py      what this machine is (OS, CPU architecture, GPU and its compute stack)
  backends.py  per-stack code that ships with the server: preflight checks, GPU memory probe
  catalog.py   the pinned package catalog
  registry.py  install, load, reload, remove; runner(name) for the pipelines

This module imports nothing on purpose: app.gpu imports backends, and registry imports app.gpu.
"""
