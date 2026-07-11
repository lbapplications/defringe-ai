"""[session] Open and close an edit transaction — the gate transform/shape tools sit behind."""

from __future__ import annotations

from ..board import Board
from ..workspace import Workspace
from . import core

session = core.category("session")


@session
def edit(intent: str, workspace: str = "") -> dict:
    """[session] Begin an edit transaction on an asset. You just describe *what you want
    to change* (`intent`); this saves a backup copy and opens the gate so transform /
    shape tools may run. End with cancel() to restore the backup, or commit() to keep."""
    st = Workspace.resolve(workspace, core.HOME).begin_edit(intent)
    Board(core.HOME).select(st["workspace"])
    return st


@session
def cancel(workspace: str = "") -> dict:
    """[session] Cancel the edit transaction: restore the asset from its backup, as if
    nothing happened, and close the gate."""
    return Workspace.resolve(workspace, core.HOME).cancel_edit()


@session
def commit(workspace: str = "") -> dict:
    """[session] Commit the edit transaction: keep the current image, discard the backup."""
    ws = Workspace.resolve(workspace, core.HOME)
    st = ws.commit_edit()
    label = st["chain"][-1] if st.get("chain") else "edit"
    Board(core.HOME).record_pixel_edit(st["workspace"], label)   # image-level undo step
    return st
