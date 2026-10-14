"""Prompt framing shared with the Blender add-on: the single source is blender/local_producer/prompts.py (no bpy),
loaded here by path so the add-on, the server and the web UI compose identical prompts."""

import importlib.util
import os
import random
from typing import Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict

from ..schemas import ApiModel
from ..settings import paths


class PromptsModule(Protocol):
    """The parts of the add-on's prompts.py the server uses."""

    APOSE_EDIT: str
    FRAMING_TAIL: str

    def full_prompt(
        self, prompt: str, view: str = ..., framing: bool = ..., subject: str = ..., style: str = ...
    ) -> str: ...


Subject = Literal["character", "object"]
Style = Literal["stylized", "realistic"]
View = Literal["front", "three_quarter"]


class Framing(BaseModel):
    """Image-to-3D framing appended to a text-to-image prompt."""

    model_config = ConfigDict(extra="forbid")
    subject: Subject = "character"
    style: Style = "stylized"
    view: View = "three_quarter"


class SubjectOption(ApiModel):
    value: Subject
    label: str
    description: str | None = None


class StyleOption(ApiModel):
    value: Style
    label: str


class ViewOption(ApiModel):
    value: View
    label: str


class FramingOptions(ApiModel):
    subjects: list[SubjectOption]
    styles: list[StyleOption]
    views: list[ViewOption]
    apose_prompt: str


_module: PromptsModule | None = None


def prompts() -> PromptsModule:
    global _module
    if _module is None:
        path = os.path.join(paths.addon, "prompts.py")
        spec = importlib.util.spec_from_file_location("addon_prompts", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _module = cast(PromptsModule, module)
    return _module


def framing_options() -> FramingOptions:
    p = prompts()
    return FramingOptions(
        subjects=[
            SubjectOption(value="character", label="Character", description="People, animals, creatures: full body"),
            SubjectOption(value="object", label="Object", description="Props, machines, parts: one object"),
        ],
        styles=[StyleOption(value="stylized", label="Stylized"), StyleOption(value="realistic", label="Realistic")],
        views=[ViewOption(value="front", label="Front"), ViewOption(value="three_quarter", label="3/4")],
        apose_prompt=f"{p.APOSE_EDIT} {p.FRAMING_TAIL[0].upper()}{p.FRAMING_TAIL[1:]}",
    )


def compose(prompt: str, framing: Framing | None = None) -> str:
    """The prompt sent to FLUX.2: the user's text plus, when framing is given, the image-to-3D framing."""
    if framing is None:
        return prompt.strip()
    return prompts().full_prompt(prompt, framing.view, True, framing.subject, framing.style)


def resolve_seed(seed: int) -> int:
    return random.randint(0, 2**31 - 1) if seed < 0 else seed  # noqa: S311  not security relevant
