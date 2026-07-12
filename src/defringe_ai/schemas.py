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


class MergeResult(BaseModel):
    """The result of shipping an approved state to the user's real file (a commit, C10)."""

    workspace: str = Field(description="The asset that was merged.")
    merged: str = Field(description="The user's real file the approved state was written onto (in place).")
    commit: int = Field(description="Index of this commit in the cross-merge backup ledger.")
    commits: list[int] = Field(description="Every approved-commit index now in the ledger (restorable).")
    head: int = Field(description="Index of the current step — 0 after the fine edit chain collapses.")
    steps: int = Field(description="Total steps in the edit chain (1 right after a merge).")


class EdgeDetectTuneResult(BaseModel):
    """One step of the agent-in-the-loop edge-detection threshold search (binary search over
    the Canny hysteresis level). While `done` is False, LOOK at `current`, judge it, and call
    `edge_detect_tune(verdict=...)` again; when `done` is True the winning edge map is committed."""

    workspace: str = Field(description="The asset being tuned.")
    done: bool = Field(description="True once the search converged and the edge map is committed (undo restores the original).")
    probe: int = Field(description="Which probe this is (1-based); the search runs at most 3.")
    lo: int = Field(description="Low hysteresis threshold used for this candidate.")
    hi: int = Field(description="High hysteresis threshold used for this candidate.")
    bracket: list[int] = Field(description="The current search range [min, max] the level is being bisected within.")
    nos: int = Field(description="Count of 'more' verdicts so far — the search also stops at 2.")
    question: str = Field(description="What to judge about `current` before the next verdict (empty when done).")
    current: str = Field(description="Path to the candidate edge map to LOOK at (or the committed result when done).")
    head: int = Field(description="Index of the current step in the edit chain.")
    steps: int = Field(description="Total steps in the edit chain.")
    width: int = Field(description="Current image width in pixels.")
    height: int = Field(description="Current image height in pixels.")
