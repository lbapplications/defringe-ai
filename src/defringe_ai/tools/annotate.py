"""[annotate · gated] Drop debug/seed dots onto the image — gated behind an edit session."""

from __future__ import annotations

from .. import imageops as ops
from . import core

annotate = core.category("annotate", gated=True)


@annotate
def mark(points: list[list[int]], radius: int = 4, color: str = "black", session: str = "") -> dict:
    """[annotate · gated] Drop a tiny filled dot at each [x, y] in `points` — for flagging
    seed points or locations to eyeball. Coords are (x, y), top-left origin, x→right,
    y→down. Points outside the frame are skipped. Gated: call edit(...) first."""
    st = core.apply("mark", ops.Annotate.mark, session, points=points, radius=radius, color=color)
    return {**st, "marked": len(points), "points": points}
