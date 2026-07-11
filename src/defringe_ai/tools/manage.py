"""[workspace] Agent-facing workspace controls: open, list, inspect, undo/redo, collapse, export.

(The module is ``manage`` to avoid clashing with the engine's ``workspace.py``; its taxonomy
category is still ``"workspace"``.)
"""

from __future__ import annotations

from .. import imageops as ops
from ..board import Board
from ..workspace import Workspace, _get_active
from . import core

manage = core.category("workspace")


@manage
def open_asset(path: str, name: str = "") -> dict:
    """Copy an external asset into a workspace and make it the active edit target.
    Open several (each gets a name, defaulting to the filename) and shape them in
    parallel — address any by its `name`, or omit `name` on later tools to keep
    working the one you touched last."""
    ws = Workspace.open_asset(path, core.HOME, name or None)
    st = ws.status()
    if ws.renamed_from:                               # resume renamed the label — carry board state over
        Board(core.HOME).rename(ws.renamed_from, st["workspace"])
    Board(core.HOME).select(st["workspace"])          # new asset lands selected, on top
    return st


@manage
def list_workspaces() -> dict:
    """List every open workspace and which one is currently active."""
    return {"workspaces": Workspace.list_all(core.HOME), "active": _get_active(core.HOME)}


@manage
def taxonomy() -> dict:
    """The tool taxonomy and which categories are gated behind an edit session — derived
    from the tool modules themselves (each category is a module under ``tools/``)."""
    return {"categories": core.taxonomy_map(), "gated": sorted(core.gated_set())}


@manage
def list_shapes() -> dict:
    """The registered shapes, anchors, and named colours that draw_shape understands."""
    return {"shapes": list(ops.Shape.NAMES), "anchors": list(ops.Shape.ANCHORS), "colors": list(ops.Color.NAMED)}


@manage
def status(workspace: str = "") -> dict:
    """Current workspace state: HEAD, the edit chain, can_undo/redo, current file."""
    return Workspace.resolve(workspace, core.HOME).status()


@manage
def undo(workspace: str = "") -> dict:
    """Step HEAD back one edit. Reversible; redo is still available."""
    return Workspace.resolve(workspace, core.HOME).undo()


@manage
def redo(workspace: str = "") -> dict:
    """Step HEAD forward one edit (after an undo)."""
    return Workspace.resolve(workspace, core.HOME).redo()


@manage
def collapse(workspace: str = "") -> dict:
    """Verify: flatten the edit chain to the current image as the new base asset."""
    return Workspace.resolve(workspace, core.HOME).collapse()


@manage
def export(dest: str, workspace: str = "") -> dict:
    """Write the current image out to a path — the finished deliverable."""
    return Workspace.resolve(workspace, core.HOME).export(dest)
