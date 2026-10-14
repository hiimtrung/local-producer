"""The pinned engine package catalog (catalog/engines.json) and its rules.

A package's downloads follow the same rules as the weights (model_setup.validate_items: https, allowlisted hosts,
size + SHA256, safe destinations). On top of that its runners and library directories must stay inside the package,
and it may only set plain environment variables, never ones that change how programs are loaded.
"""

import json
import os
import re
from typing import Self

from pydantic import Field, model_validator

from ..model_setup import ManifestItem, SetupError, safe_relpath, validate_items
from ..schemas import ApiModel
from .host import Accelerator, HostInfo

CATALOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "catalog", "engines.json"
)
NAME = r"^[a-z0-9][a-z0-9.-]{0,63}$"
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
FORBIDDEN_ENV = re.compile(r"^(LD_|DYLD_|PATH$|PYTHON|HOME$|SHELL$)")


class Platform(ApiModel):
    os: str
    arch: str
    accelerator: Accelerator
    gpu_targets: list[str] = Field(default_factory=list, description="Empty = any GPU of that stack")

    def mismatch(self, host: HostInfo) -> str:
        """Why this platform does not match the host, or ""."""
        if (self.os, self.arch) != (host.os, host.arch):
            return f"built for {self.os} {self.arch}, this machine is {host.os} {host.arch}"
        if self.accelerator != host.accelerator:
            return f"needs {self.accelerator}, this machine has {host.accelerator} ({host.gpu})"
        if self.gpu_targets and not set(self.gpu_targets) & set(host.gpu_targets):
            return f"built for {', '.join(self.gpu_targets)}, this GPU is {', '.join(host.gpu_targets) or 'unknown'}"
        return ""


class RunnerSpec(ApiModel):
    bin: str
    lib_dirs: list[str] = Field(default_factory=list)
    self_test: list[str] = Field(
        default_factory=lambda: ["--help"], description="Arguments that must exit 0 without touching the GPU"
    )


class PackageSpec(ApiModel):
    id: str = Field(pattern=NAME)
    version: str = Field(pattern=NAME)
    title: str
    description: str
    platform: Platform
    env: dict[str, str] = Field(default_factory=dict)
    lib_dirs: list[str] = Field(default_factory=list, description="Shared runtime libraries, before each runner's")
    runners: dict[str, RunnerSpec]
    items: list[ManifestItem]

    @model_validator(mode="after")
    def _paths_stay_inside(self) -> Self:
        for rel in [*self.lib_dirs, *(r.bin for r in self.runners.values())]:
            safe_relpath(rel)
        for runner in self.runners.values():
            for rel in runner.lib_dirs:
                safe_relpath(rel)
        for name in self.env:
            if not ENV_NAME.match(name) or FORBIDDEN_ENV.match(name):
                raise SetupError(f"{self.id}: environment variable {name} is not allowed")
        for name in self.runners:
            if not re.match(NAME, name):
                raise SetupError(f"{self.id}: bad runner name {name!r}")
        return self

    @property
    def download_size(self) -> int:
        return sum(int(it["size"]) for it in self.items)


class Planned(ApiModel):
    accelerator: Accelerator
    title: str
    description: str


class Catalog(ApiModel):
    version: int
    allowed_domains: list[str]
    packages: list[PackageSpec]
    planned: list[Planned] = Field(default_factory=list)

    def versions(self, pid: str) -> list[PackageSpec]:
        """Every catalog version of a package, newest first."""
        return sorted((p for p in self.packages if p.id == pid), key=lambda p: version_key(p.version), reverse=True)

    def find(self, pid: str, version: str | None = None) -> PackageSpec | None:
        """A given version, or the newest one."""
        found = self.versions(pid)
        if version is not None:
            found = [p for p in found if p.version == version]
        return found[0] if found else None


def version_key(version: str) -> tuple[tuple[int, str], ...]:
    """Natural order: 2026.10.15 < 2026.10.15b < 2026.11.1."""
    return tuple((int(part), "") if part.isdigit() else (-1, part) for part in re.findall(r"\d+|[a-z]+", version))


def load_catalog(path: str = CATALOG) -> Catalog:
    with open(path) as f:
        raw = json.load(f)
    if raw.get("version") != 1:
        raise SetupError("unsupported engine catalog version")
    cat = Catalog.model_validate(raw)
    ids = [(p.id, p.version) for p in cat.packages]
    if len(set(ids)) != len(ids):
        raise SetupError("duplicate package version in the engine catalog")
    for p in cat.packages:
        if any(it["kind"] == "convert" for it in p.items):
            raise SetupError(f"{p.id}: packages are downloads only")
        validate_items(p.items, cat.allowed_domains)
    return cat
