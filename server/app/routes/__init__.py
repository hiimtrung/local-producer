"""HTTP routes, one module per area. main.create_app() includes every router listed in ROUTERS."""

from . import addon, config, engines, jobs, models, prompts, setup, system

ROUTERS = [
    system.router,
    setup.router,
    engines.router,
    models.router,
    config.router,
    jobs.router,
    prompts.router,
    addon.router,
]
