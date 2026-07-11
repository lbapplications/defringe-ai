"""Pydantic result models — the typed-return standard for MCP tools.

The standard (see ``harness_driver/tools.md``): a tool that mutates state returns a Pydantic
model, not a bare dict, so the shape is declared, validated, and self-documenting to the
agent. New tools follow this; older dict-returning tools migrate opportunistically.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MaskState(BaseModel):
    """The state of an asset's invisible mask layer after a seed/connect/clear op."""

    workspace: str = Field(description="The asset this mask belongs to.")
    dots: int = Field(description="Number of seed dots currently on the mask.")
    outline: int = Field(description="Number of vertices in the connected boundary (0 if not connected).")
    locked: bool = Field(description="Whether the asset is pinned (clicks drop dots, not drags).")


class IsolateResult(BaseModel):
    """The workspace state after an isolate (cutout) op."""

    workspace: str = Field(description="The asset that was cut out.")
    head: int = Field(description="Index of the current step in the edit chain.")
    steps: int = Field(description="Total steps in the edit chain.")
    current: str = Field(description="Path to the current (isolated) image snapshot.")
    width: int = Field(description="Current image width in pixels.")
    height: int = Field(description="Current image height in pixels.")
    chain: list[str] = Field(description="The ordered op names in the edit chain.")
