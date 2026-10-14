"""Prompt framing options and composition, from the add-on's prompts.py (one source for add-on, server and web)."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from ..pipelines.prompting import Framing, FramingOptions, compose, framing_options
from ..schemas import ApiModel
from ..settings import MAX_PROMPT_CHARS

router = APIRouter()


class ComposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(max_length=MAX_PROMPT_CHARS)
    framing: Framing | None = None


class ComposedPrompt(ApiModel):
    prompt: str


@router.get("/v1/prompts/framing")
def framing() -> FramingOptions:
    return framing_options()


@router.post("/v1/prompts/compose")
def compose_prompt(req: ComposeRequest) -> ComposedPrompt:
    return ComposedPrompt(prompt=compose(req.prompt, req.framing))
