"""[isolate] Compound board+geometry actions: seed → connect/outline → matte (the cutout).

Its own taxonomy category, deliberately NOT part of the transform gate: `isolate`/`cutout`
are self-contained (each opens & commits its own edit where it touches pixels), and the
seed/connect flow reads and writes the board mask directly.
"""

from __future__ import annotations

from .. import imageops as ops
from ..board import Board
from ..schemas import IsolateResult, MaskState
from ..workspace import Workspace
from . import core

isolate_cat = core.category("isolate")


def _mask_state(name: str) -> MaskState:
    """Read the current mask counts for an asset into a MaskState result."""
    a = Board(core.HOME).sync().get("assets", {}).get(name, {})
    m = a.get("mask", {})
    return MaskState(workspace=name, dots=len(m.get("dots", [])),
                     outline=len(m.get("outline", [])), locked=bool(a.get("locked", False)))


@isolate_cat
def seed(points: list[list[int]], workspace: str = "") -> MaskState:
    """[isolate] Drop rough seed dots on the asset's invisible mask, in image-pixel space.

    Place points loosely around the subject's edge; precision isn't needed — `connect`
    snaps a boundary through them. `points` is a list of `[x, y]` pairs (top-left origin)."""
    name = core.name(workspace)
    board = Board(core.HOME)
    for p in points:
        board.add_dot(name, int(p[0]), int(p[1]))
    return _mask_state(name)


@isolate_cat
def connect(workspace: str = "") -> MaskState:
    """[isolate] Connect the mask's seed dots into a boundary polygon: convex hull, then
    snap inward through every dot (deterministic). Stored on the mask; run `isolate` next."""
    name = core.name(workspace)
    b = Board(core.HOME).sync()
    dots = b.get("assets", {}).get(name, {}).get("mask", {}).get("dots", [])
    Board(core.HOME).set_outline(name, ops.Geometry.hull_snap(dots))
    return _mask_state(name)


@isolate_cat
def outline(epsilon: float = 2.0, workspace: str = "") -> MaskState:
    """[isolate] Trace the subject's boundary straight from the pixels — the unseeded
    counterpart to `connect`. Finds the outer contour of the matte (alpha > 0), takes the
    largest, and simplifies it into a sparse polygon (Douglas–Peucker), so it hugs every
    concavity a seeded convex boundary flies over — with no dots placed.

    Needs a matte: the alpha must already mark the subject (run `key_background` or another
    isolate-prep first). `epsilon` is the simplify tolerance in pixels — larger drops more
    vertices for a coarser outline. Lands in `mask.outline`; run `isolate` next to cut it."""
    name = core.name(workspace)
    img = Workspace.resolve(name, core.HOME).current_array()
    poly = ops.Geometry.simplify_contour(img, epsilon)
    if len(poly) < 3:
        raise ValueError("no traceable outline — the alpha marks no subject; key/matte first")
    Board(core.HOME).set_outline(name, poly, label="outline")
    return _mask_state(name)


@isolate_cat
def isolate(workspace: str = "") -> IsolateResult:
    """[isolate] Cut out the subject: fill the connected boundary into alpha (transparent
    background). Self-contained — opens and commits its own edit. Run `connect` first."""
    name = core.name(workspace)
    b = Board(core.HOME).sync()
    outline = b.get("assets", {}).get(name, {}).get("mask", {}).get("outline", [])
    if len(outline) < 3:
        raise ValueError("no outline — call connect() first (needs >=3 seed dots)")
    ws = Workspace.resolve(name, core.HOME)
    ws.begin_edit("isolate (fill mask)")
    st = ws.apply("isolate", ops.Geometry.fill_polygon_alpha, {"polygon": outline})
    ws.commit_edit()
    Board(core.HOME).record_pixel_edit(name, "isolate")   # image-level undo step
    return IsolateResult(workspace=name, head=st["head"], steps=st["steps"],
                         current=st["current"], width=st["width"], height=st["height"],
                         chain=st["chain"])


def _seed_rect(rect, name: str, w: int, h: int) -> list[int]:
    """Resolve GrabCut's seed box: an explicit [x,y,w,h], else the mask's dots/outline bounding
    box, else the whole frame inset by ~6% so there's a background border to learn from."""
    if rect and len(rect) == 4:
        return [int(v) for v in rect]
    m = Board(core.HOME).sync().get("assets", {}).get(name, {}).get("mask", {})
    pts = (m.get("outline") or []) + (m.get("dots") or [])
    if len(pts) >= 2:
        xs = [int(p[0]) for p in pts]
        ys = [int(p[1]) for p in pts]
        return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    mx, my = int(w * 0.06), int(h * 0.06)             # inset frame → a bg border to seed from
    return [mx, my, w - 2 * mx, h - 2 * my]


@isolate_cat
def cutout(rect: list[int] = [], iterations: int = 5, workspace: str = "") -> IsolateResult:
    """[isolate] Auto-cut the subject from its background by iterated graph-cut segmentation
    (GrabCut). Seed with a rough box around the subject; it fits foreground/background colour
    models and cuts on colour **and** connectivity, so it separates the subject from
    same-coloured background a flat key can't. Keeps the largest segmented region (drops stray
    specks). Self-contained — opens and commits its own edit.

    Args:
        rect: Seed box `[x, y, w, h]` around the subject in image pixels. Empty → use the mask's
            dots/outline bounding box if seeded, else the whole frame inset by a margin.
        iterations: GrabCut refinement passes (1 usually suffices for a high-contrast subject).
    """
    name = core.name(workspace)
    ws = Workspace.resolve(name, core.HOME)
    h, w = ws.current_array().shape[:2]
    box = _seed_rect(rect, name, w, h)
    ws.begin_edit("cutout (segment)")
    st = ws.apply("cutout", ops.Transform.segment, {"rect": box, "iterations": int(iterations)})
    ws.commit_edit()
    Board(core.HOME).record_pixel_edit(name, "cutout")     # image-level undo step
    return IsolateResult(workspace=name, head=st["head"], steps=st["steps"],
                         current=st["current"], width=st["width"], height=st["height"],
                         chain=st["chain"])


@isolate_cat
def clear_seeds(workspace: str = "") -> MaskState:
    """[isolate] Remove all seed dots and the connected outline from the asset's mask."""
    name = core.name(workspace)
    Board(core.HOME).clear_dots(name)
    return _mask_state(name)
