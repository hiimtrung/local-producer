"""local-producer GPU server: FLUX.2-klein-4B and TRELLIS.2 on ROCm, a job queue, model setup and the web UI.

Layout: settings (paths, limits, runtime config), security (token, headers), gpu (one CLI process at a time),
storage (uploads, job files), jobs (queue), pipelines/ (one module per capability), routes/ (one module per API
area), model_setup (pinned downloads). main.create_app() wires them together.
"""

__version__ = "0.3.0"
