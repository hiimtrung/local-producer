"""Pipeline registry. A new capability = a module with a Pipeline subclass and its job request model, registered in
PIPELINES and JobRequest below (see base.py); tests/test_api.py checks that the two lists agree."""

from typing import Annotated, Any

from pydantic import Field, RootModel

from .base import Pipeline
from .check import CheckJob, ModelTest
from .flux import EditJob, GenerateJob, ImageEdit, ImageGenerate
from .matte import MatteJob, RemoveBackground
from .trellis import ImageTo3D, MeshJob

PIPELINES: dict[str, Pipeline[Any]] = {
    p.kind: p for p in (ImageGenerate(), ImageEdit(), RemoveBackground(), ImageTo3D(), ModelTest())
}


class JobRequest(
    RootModel[Annotated[GenerateJob | EditJob | MatteJob | MeshJob | CheckJob, Field(discriminator="kind")]]
):
    """The body of POST /v1/jobs: {"kind": ..., "params": ...}, params checked against that pipeline's Params."""
