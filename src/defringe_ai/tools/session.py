"""[session] Open and close an edit transaction — the gate transform/shape tools sit behind."""

from __future__ import annotations

from ..board import Board
from . import core

session = core.category("session")


@session
def edit(intent: str, session: str = "") -> dict:
    """[session] Begin an edit transaction on an asset. Pass the `session` you got from
    open_asset and describe *what you want to change* (`intent`); this saves a backup copy
    and opens the gate so transform / shape tools may run. End with cancel() to restore the
    backup, or commit() to keep."""
    name, ws = core.workspace(session)
    st = ws.begin_edit(intent)
    Board(core.HOME).select(name)
    core.advance(session, ws)
    return st


@session
def cancel(session: str = "") -> dict:
    """[session] Cancel the edit transaction: restore the asset from its backup, as if
    nothing happened, and close the gate."""
    _, ws = core.workspace(session)
    st = ws.cancel_edit()
    core.advance(session, ws)
    return st


@session
def commit(session: str = "") -> dict:
    """[session] Commit the edit transaction: keep the current image, discard the backup."""
    name, ws = core.workspace(session)
    st = ws.commit_edit()
    label = st["chain"][-1] if st.get("chain") else "edit"
    Board(core.HOME).record_pixel_edit(name, label)   # image-level undo step
    core.advance(session, ws)
    return st
