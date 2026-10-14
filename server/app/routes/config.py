"""Runtime configuration (settings.RuntimeConfig): read, schema for the web form, validated update."""

from fastapi import APIRouter, Body, HTTPException
from pydantic import JsonValue, ValidationError

from ..settings import RuntimeConfig, config

router = APIRouter()


@router.get("/v1/config")
def get_config() -> RuntimeConfig:
    return config.get()


@router.get("/v1/config/schema")
def config_schema() -> dict[str, JsonValue]:
    return RuntimeConfig.model_json_schema()


@router.put("/v1/config")
def put_config(changes: dict[str, JsonValue] = Body(...)) -> RuntimeConfig:
    """Partial update: only the fields sent change; the result is validated as a whole."""
    try:
        return config.update(changes)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False, include_input=False)) from None
