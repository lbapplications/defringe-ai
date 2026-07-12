"""[arrange] Canvas layout — place/select assets on the shared board. Not gated."""

from __future__ import annotations

from ..board import Board
from . import core

arrange = core.category("arrange")


@arrange
def move(x: int, y: int, scale: float = 0, session: str = "") -> dict:
    """Place an asset on the shared canvas: top-left x,y in px, and optional display
    scale (>0 to expand/contract; omit to leave scale unchanged). This is how I
    arrange the edit screen; a human can also drag/resize assets there."""
    name = core.name(session)
    b = Board(core.HOME).place(name, x=x, y=y, scale=scale or None)
    z = b["order"].index(name) if name in b["order"] else -1   # -1 when nothing is placeable yet
    return {"workspace": name, "placement": b["assets"].get(name), "z": z}


@arrange
def select(session: str = "") -> dict:
    """Select an asset and bring it to the front of the canvas (raise it above others)."""
    name = core.name(session)
    b = Board(core.HOME).select(name)
    return {"selected": b["selected"], "order": b["order"]}
