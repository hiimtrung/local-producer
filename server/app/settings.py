"""Paths, hard limits and the runtime configuration (validated, persisted in <data>/config.json).

Hard limits are code constants on purpose: they protect the server and are not user-configurable. Everything a user
may change lives in RuntimeConfig; adding a setting means adding a validated field there (and to the web Settings
page, which renders the fields it gets from GET /v1/config/schema).
"""

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

MAX_IMAGE_BYTES = 32 * 2**20
MAX_BODY_BYTES = 48 * 2**20  # base64 of a 32 MiB image plus JSON
MAX_PROMPT_CHARS = 4000


@dataclass
class Paths:
    """Where things live. Defaults match the container (scripts/run-server.sh); tests point them at tmp dirs.

    models   weights, portable across engines (a Podman volume; native runs: any directory)
    engines  installed engine packages: GPU runtime libraries and CLI builds for one platform (another volume)
    library  job results and uploads, what the Library shows (a directory on the host disk)
    data     server state: runtime config and logs (a directory on the host disk, next to the library)"""

    models: str = field(default_factory=lambda: os.environ.get("MODELS_DIR", "/models"))
    engines: str = field(default_factory=lambda: os.environ.get("ENGINES_DIR", "/engines"))
    library: str = field(default_factory=lambda: os.environ.get("LIBRARY_DIR", "/library"))
    data: str = field(default_factory=lambda: os.environ.get("DATA_DIR", "/data"))
    app: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../server (or /opt/lp/server)

    @property
    def log(self) -> str:
        return os.path.join(self.data, "server.log")

    @property
    def jobs(self) -> str:
        return os.path.join(self.library, "jobs")

    @property
    def uploads(self) -> str:
        return os.path.join(self.library, "uploads")

    @property
    def config(self) -> str:
        return os.path.join(self.data, "config.json")

    @property
    def web(self) -> str:
        """The built web UI (web/dist, made by `make web-build`)."""
        return os.environ.get("WEB_DIR", os.path.join(os.path.dirname(self.app), "web", "dist"))

    @property
    def addon(self) -> str:
        """The Blender add-on package directory (served as a zip)."""
        return os.environ.get("ADDON_DIR", os.path.join(os.path.dirname(self.app), "blender", "local_producer"))


paths = Paths()


class RuntimeConfig(BaseModel):
    """Settings a user may change from the web UI (PUT /v1/config). Defaults are the measured sweet spots
    (CHANGELOG 2026-10-14)."""

    # defaults are always present in responses, as in schemas.ApiModel (settings does not import schemas)
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

    image_steps: int = Field(4, ge=1, le=50, title="Image steps", description="FLUX.2 denoising steps by default")
    mesh_steps: int = Field(8, ge=1, le=50, title="Mesh steps", description="TRELLIS.2 flow steps per stage")
    mesh_resolution: Literal[512, 1024, 1536] = Field(512, title="Mesh resolution", description="Default resolution")
    job_timeout_s: int = Field(7200, ge=60, le=86400, title="Job timeout (s)", description="A job is killed after")
    keep_jobs: int = Field(200, ge=10, le=5000, title="Jobs kept", description="Older job results are deleted")
    keep_uploads: int = Field(500, ge=10, le=5000, title="Uploads kept", description="Older uploads are deleted")


class ConfigStore:
    """Thread-safe access to RuntimeConfig, persisted atomically as JSON."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self._cfg: RuntimeConfig | None = None

    def get(self) -> RuntimeConfig:
        with self.lock:
            if self._cfg is None:
                self._cfg = self._load()
            return self._cfg

    def _load(self) -> RuntimeConfig:
        try:
            with open(paths.config) as f:
                return RuntimeConfig.model_validate_json(f.read())
        except (OSError, ValueError):
            return RuntimeConfig()

    def update(self, changes: dict[str, JsonValue]) -> RuntimeConfig:
        """Raises pydantic.ValidationError (a ValueError) when a change is invalid."""
        with self.lock:
            current = self._cfg or self._load()
            new = RuntimeConfig.model_validate({**current.model_dump(), **changes})
            os.makedirs(paths.data, exist_ok=True)
            tmp = paths.config + ".tmp"
            with open(tmp, "w") as f:
                json.dump(new.model_dump(), f, indent=2)
            os.replace(tmp, paths.config)
            self._cfg = new
            return new

    def reset_cache(self) -> None:
        with self.lock:
            self._cfg = None


config = ConfigStore()
