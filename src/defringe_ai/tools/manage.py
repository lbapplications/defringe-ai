"""[workspace] Agent-facing workspace controls: open, list, inspect, undo/redo, collapse, export.

(The module is ``manage`` to avoid clashing with the engine's ``workspace.py``; its taxonomy
category is still ``"workspace"``.)
"""

from __future__ import annotations

from .. import imageops as ops
from ..board import Board
from ..sessions import Sessions
from ..workspace import Workspace
from . import core

manage = core.category("workspace")


@manage
def open_asset(path: str, name: str = "") -> dict:
    """Mount an external asset and open an edit **session** on it — the entry point every other
    tool needs. Returns the workspace status plus a `session` id: carry that id into edit(),
    the transforms, move(), etc. so the server knows which asset you mean (there is no ambient
    'current asset'). Open several assets — each gets its own session — and shape them in
    parallel; `name` is just a human label (defaults to the filename), never the address."""
    ws = Workspace.open_asset(path, core.HOME, name or None)
    st = ws.status()
    if ws.renamed_from:                               # resume renamed the label — carry board state over
        Board(core.HOME).rename(ws.renamed_from, st["workspace"])
    Board(core.HOME).select(st["workspace"])          # new asset lands selected, on top
    session = core.open_session(st["workspace"])      # mount → session handle (C6)
    core.advance(session, ws)                          # seed the cursor at the opened state
    return {**st, "session": session}


@manage
def list_workspaces() -> dict:
    """List every open workspace and its live session id (the token to address it with)."""
    return {"workspaces": Workspace.list_all(core.HOME), "sessions": Sessions(core.HOME).by_name()}


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
def status(session: str = "") -> dict:
    """Current workspace state: HEAD, the edit chain, can_undo/redo, current file."""
    return core.workspace(session)[1].status()


@manage
def undo(session: str = "") -> dict:
    """Step HEAD back one edit. Reversible; redo is still available."""
    _, ws = core.workspace(session)
    st = ws.undo()
    core.advance(session, ws)
    return st


@manage
def redo(session: str = "") -> dict:
    """Step HEAD forward one edit (after an undo)."""
    _, ws = core.workspace(session)
    st = ws.redo()
    core.advance(session, ws)
    return st


@manage
def collapse(session: str = "") -> dict:
    """Verify: flatten the edit chain to the current image as the new base asset."""
    _, ws = core.workspace(session)
    st = ws.collapse()
    core.advance(session, ws)
    return st


@manage
def export(dest: str, session: str = "") -> dict:
    """Write the current image out to a path — the finished deliverable."""
    return core.workspace(session)[1].export(dest)
