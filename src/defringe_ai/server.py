"""defringe-ai — MCP server + CLI, both thin front-ends over the workspace engine.

The workspace (on-disk asset + reversible edit chain) is the source of truth. Every
transform tool applies to the active workspace's HEAD and returns its status, so a
vision agent can chain edits, undo, and collapse — and a human can drive the exact
same workspace from the CLI.

  defringe-ai open ./art/octopus.png     # copy an asset in, start editing (human)
  defringe-ai serve --preview            # run the MCP server + browser gallery
  defringe-ai undo | redo | status | collapse | export out.png

Transforms (key_background, crop, defringe, …) are exposed as MCP tools for the agent.
"""

from __future__ import annotations

import argparse
import os
import socket
import threading

from mcp.server.fastmcp import FastMCP

from . import imageops as ops
from .board import Board
from .schemas import EdgeDetectTuneResult, IsolateResult, MaskState
from .workspace import HOME, Workspace, _get_active

# Uncommon defaults, deliberately off the 8000/8080/3000 beaten path so the server
# can run beside whatever an artist already has open. Auto-bumped if taken anyway.
DEFAULT_HTTP_PORT = 47823
DEFAULT_PREVIEW_PORT = 47824

mcp = FastMCP("defringe-ai")


# --- tool taxonomy ---------------------------------------------------------
# Tools are grouped by what they touch. `transform` and `shape` MUTATE PIXELS and
# are GATED: they refuse unless an edit session is active (call `edit` first, then
# `cancel` to revert or `commit` to keep). Everything else runs freely.
TAXONOMY = {
    "session":   ["edit", "cancel", "commit"],          # open/close an edit transaction
    "transform": ["key_background", "trim_alpha", "crop", "defringe", "upscale", "silhouette_mask"],
    "shape":     ["draw_shape", "draw_line"],           # draw primitives onto the image
    "annotate":  ["mark"],                               # drop debug/seed dots
    "isolate":   ["seed", "connect", "outline", "cutout", "isolate", "clear_seeds"],  # dots|pixels|segment -> matte
    "derive":    ["edge_detect", "edge_detect_tune"],    # extract a SIGNAL as a mask overlay — image untouched, undoable
    "arrange":   ["move", "select"],                     # canvas layout — not gated
    "workspace": ["open_asset", "list_workspaces", "list_shapes", "taxonomy", "status", "undo", "redo", "collapse", "export"],
}
GATED = set(TAXONOMY["transform"]) | set(TAXONOMY["shape"]) | set(TAXONOMY["annotate"])


def _apply(op: str, fn, workspace: str, **params) -> dict:
    """Apply a pixel-mutating op — but only inside an edit session (the gate)."""
    ws = Workspace.resolve(workspace, HOME)
    if not ws.in_session():
        raise ValueError(
            f"'{op}' is gated: this asset has no active edit session. "
            f'Call edit("<what you want to change>") first, then apply {op}; '
            f"cancel() to revert or commit() to keep."
        )
    return ws.apply(op, fn, params)


def _name(workspace: str) -> str:
    """Resolve a board asset name: the given one, or the active workspace."""
    return workspace or _get_active(HOME) or ""


@mcp.tool()
def open_asset(path: str, name: str = "") -> dict:
    """Copy an external asset into a workspace and make it the active edit target.
    Open several (each gets a name, defaulting to the filename) and shape them in
    parallel — address any by its `name`, or omit `name` on later tools to keep
    working the one you touched last."""
    st = Workspace.open_asset(path, HOME, name or None).status()
    Board(HOME).select(st["workspace"])          # new asset lands selected, on top
    return st


@mcp.tool()
def list_workspaces() -> dict:
    """List every open workspace and which one is currently active."""
    from .workspace import _get_active

    return {"workspaces": Workspace.list_all(HOME), "active": _get_active(HOME)}


# --- session (the transactional gate) --------------------------------------

@mcp.tool()
def taxonomy() -> dict:
    """The tool taxonomy and which categories are gated behind an edit session."""
    return {"categories": TAXONOMY, "gated": sorted(GATED)}


@mcp.tool()
def edit(intent: str, workspace: str = "") -> dict:
    """[session] Begin an edit transaction on an asset. You just describe *what you want
    to change* (`intent`); this saves a backup copy and opens the gate so transform /
    shape tools may run. End with cancel() to restore the backup, or commit() to keep."""
    st = Workspace.resolve(workspace, HOME).begin_edit(intent)
    Board(HOME).select(st["workspace"])
    return st


@mcp.tool()
def cancel(workspace: str = "") -> dict:
    """[session] Cancel the edit transaction: restore the asset from its backup, as if
    nothing happened, and close the gate."""
    return Workspace.resolve(workspace, HOME).cancel_edit()


@mcp.tool()
def commit(workspace: str = "") -> dict:
    """[session] Commit the edit transaction: keep the current image, discard the backup."""
    ws = Workspace.resolve(workspace, HOME)
    st = ws.commit_edit()
    label = st["chain"][-1] if st.get("chain") else "edit"
    Board(HOME).record_pixel_edit(st["workspace"], label)   # image-level undo step
    return st


@mcp.tool()
def list_shapes() -> dict:
    """The registered shapes, anchors, and named colours that draw_shape understands."""
    return {"shapes": list(ops.Shape.NAMES), "anchors": list(ops.Shape.ANCHORS), "colors": list(ops.Color.NAMED)}


@mcp.tool()
def mark(points: list[list[int]], radius: int = 4, color: str = "black", workspace: str = "") -> dict:
    """[annotate · gated] Drop a tiny filled dot at each [x, y] in `points` — for flagging
    seed points or locations to eyeball. Coords are (x, y), top-left origin, x→right,
    y→down. Points outside the frame are skipped. Gated: call edit(...) first."""
    st = _apply("mark", ops.Annotate.mark, workspace, points=points, radius=radius, color=color)
    return {**st, "marked": len(points), "points": points}


@mcp.tool()
def draw_shape(shape: str = "circle", x: int = -1, y: int = -1, width: int = -1, height: int = -1,
               color: str = "red", anchor: str = "center", fill: bool = False,
               thickness: int = 3, workspace: str = "") -> dict:
    """[shape · gated] Draw a registered primitive with one consistent spatial model.

      shape   : circle | ellipse | square | rectangle | triangle  (see list_shapes)
      x, y    : where the ANCHOR point sits, in pixels (top-left origin, x→right, y→down).
                Omit (leave -1) to use the image centre.
      width   : box width in px; omit -> half the short side.
      height  : box height in px; omit -> same as width (symmetric).
      anchor  : which part of the shape lands at (x,y): center (default), top_left,
                top, top_right, left, right, bottom_left, bottom, bottom_right.
      color   : 'red' | '#rrggbb[aa]' | 'r,g,b[,a]'.
      fill    : True = filled, False = outline (thickness px).

    Returns the workspace status plus `drew` (the resolved shape/anchor/center/bbox in
    pixels) and `clipped` — so you can see exactly what landed and adjust. Gated: call
    edit(...) first; cancel() to revert. Coordinate details in docs/coordinates.md."""
    ws = Workspace.resolve(workspace, HOME)
    if not ws.in_session():
        raise ValueError("'draw_shape' is gated: no active edit session. "
                         'Call edit("<what you want>") first; cancel()/commit() to end.')
    h, w = ws.current_array().shape[:2]
    g = ops.Shape.resolve_box(w, h, x=None if x < 0 else x, y=None if y < 0 else y,
                        width=None if width < 0 else width,
                        height=None if height < 0 else height, anchor=anchor)
    st = ws.apply("draw_shape", ops.Shape.draw_shape,
                  {"shape": shape, "box": g["box"], "color": color, "fill": fill, "thickness": thickness})
    return {**st, "drew": {"shape": shape, "anchor": anchor,
                           "center": list(g["center"]), "bbox": list(g["box"])},
            "clipped": g["clipped"]}


@mcp.tool()
def draw_line(x1: int, y1: int, x2: int, y2: int, color: str = "red",
              thickness: int = 2, dotted: bool = False, workspace: str = "") -> dict:
    """[shape - gated] Draw a straight line from (x1,y1) to (x2,y2) - (x,y) top-left
    origin, x->right, y->down. dotted=True gives a see-through dotted guide (good for
    crosshairs). Default colour red. Gated: call edit(...) first; cancel()/commit() to end."""
    st = _apply("draw_line", ops.Shape.draw_line, workspace,
                x1=x1, y1=y1, x2=x2, y2=y2, color=color, thickness=thickness, dotted=dotted)
    return {**st, "line": {"from": [x1, y1], "to": [x2, y2], "dotted": dotted, "color": color}}


# For every tool below, `workspace` is optional: name it to target a specific asset,
# or leave it blank to act on the last workspace touched.

@mcp.tool()
def key_background(bg: str = "white", lo: int = 40, hi: int = 90, workspace: str = "") -> dict:
    """Threshold a flat background to alpha with a soft lo..hi ramp.
    bg is 'white', 'black', '#rrggbb', or 'r,g,b'."""
    return _apply("key_background", ops.Transform.key_background, workspace, bg=bg, lo=lo, hi=hi)


@mcp.tool()
def trim_alpha(workspace: str = "") -> dict:
    """Crop to the content bounding box (alpha > 0)."""
    return _apply("trim_alpha", ops.Transform.trim_alpha, workspace)


@mcp.tool()
def crop(x: int, y: int, w: int, h: int, workspace: str = "") -> dict:
    """Carve a sub-rect out of the image (extract-region)."""
    return _apply("crop", ops.Transform.crop, workspace, x=x, y=y, w=w, h=h)


@mcp.tool()
def defringe(erode_px: int = 1, burn: float = 0.45, rim_lum: float = 135.0, workspace: str = "") -> dict:
    """Erode the alpha edge to drop the matte fringe, then burn the remaining edge
    pixels so a white/halo rim melts into a dark background."""
    return _apply("defringe", ops.Transform.defringe, workspace, erode_px=erode_px, burn=burn, rim_lum=rim_lum)


@mcp.tool()
def upscale(factor: float = 2.0, sharpen: float = 0.6, workspace: str = "") -> dict:
    """Lanczos3 resample + gentle sharpen. Holds linework; adds no real detail."""
    return _apply("upscale", ops.Transform.upscale, workspace, factor=factor, sharpen=sharpen)


@mcp.tool()
def silhouette_mask(workspace: str = "") -> dict:
    """Emit just the alpha shape (white RGB + original alpha) for CSS mask-image."""
    return _apply("silhouette_mask", ops.Transform.silhouette_mask, workspace)


@mcp.tool()
def edge_detect(lo: int = 100, hi: int = 200, workspace: str = "") -> dict:
    """[derive] Edge map (Canny) laid down as a **mask overlay**, not a pixel edit — the
    original image is untouched and stays HEAD. `lo`/`hi` are the hysteresis thresholds
    (100/200 classic; lower them to catch fainter edges, raise to keep only strong ones).
    The edges are swept into a vivid, transparency-keyed overlay (matrix_sweep) that rides
    on top of the image under the mask view. The edge *signal*, not an isolation; undo
    clears the overlay."""
    name = _name(workspace)
    if not name:
        raise ValueError("no active workspace — open an asset first")
    return _edge_detect_apply(name, lo, hi)


def _edge_overlay(img, lo: int, hi: int):
    """The edge mask overlay we render: thin **negative-of-the-image** lines (each edge
    pixel inverts what's beneath it, so it stays visible over any colour), keyed onto
    transparency. One place defines the look — both edge_detect and the tune search use it."""
    return ops.Transform.matrix_sweep(
        ops.Transform.edge_detect(img, lo, hi), mode="negative", base=img, bold=0, glow=0)


def _edge_detect_apply(name: str, lo: int, hi: int) -> dict:
    """Compute the edge map from the asset's current image and lay it down as a MASK
    OVERLAY VERSION (thin negative lines, transparency-keyed via matrix_sweep). The image is
    untouched — the original stays HEAD; the overlay is snapshotted into the asset's overlay
    chain and recorded as one timeline step, so the edit screen shows it under the mask view
    and undo restores the exact prior overlay (or none)."""
    ws = Workspace.resolve(name, HOME)
    Board(HOME).push_overlay(name, _edge_overlay(ws.current_array(), lo, hi), "edge → mask")
    return ws.status()


# --- adaptive edge detection: an agent-in-the-loop binary search over the threshold -----
# The tool bakes in the SEARCH (log(n): middle first, halve each step); YOU bake in the
# JUDGEMENT (look at the candidate, say which way). Converges in <=3 probes or after 2
# 'more' verdicts, then commits the winning edge map in place (undo restores the original).
_TUNE_KEY = "edge_detect_tune"
_TUNE_LEVEL = (50, 300)     # search range for the hysteresis level (hi); lo is level//2
_TUNE_MAX_PROBES = 3
_TUNE_MAX_NOS = 2


def _tune_render(name: str, ws: Workspace, cand: int) -> dict:
    """Render the candidate edge map as a mask-overlay preview — the original image is
    untouched and stays HEAD. Pushes an overlay version WITHOUT recording a timeline step,
    since a search's probes shouldn't spam the undo timeline until it converges."""
    Board(HOME).push_overlay(
        name, _edge_overlay(ws.current_array(), cand // 2, cand), "edge → mask", record=False)
    return ws.status()


def _tune_question(cand: int, probe: int) -> str:
    return (f"Probe {probe}/{_TUNE_MAX_PROBES} — edges at lo={cand // 2}, hi={cand}. LOOK at the "
            f"edge map: is your subject cleanly outlined? Call edge_detect_tune(verdict=…): "
            f"'reduce' (too many / noisy edges), 'more' (subject not fully outlined), or "
            f"'good' (stop here).")


def _tune_result(name: str, st: dict, state: dict, done: bool) -> EdgeDetectTuneResult:
    cand = state["cand"]
    return EdgeDetectTuneResult(
        workspace=name, done=done, probe=state["probe"], lo=cand // 2, hi=cand,
        bracket=[state["lo_b"], state["hi_b"]], nos=state["nos"],
        question="" if done else _tune_question(cand, state["probe"]),
        current=st["current"], head=st["head"], steps=st["steps"],
        width=st["width"], height=st["height"],
    )


def _tune_commit(ws: Workspace, name: str, state: dict) -> EdgeDetectTuneResult:
    """Finalise the converged candidate as the mask overlay, record the single image-level
    undo step (so the whole search collapses to one 'edge → mask' action), and clear the
    search state."""
    st = _tune_render(name, ws, state["cand"])
    Board(HOME).record_overlay_step(name, "edge → mask")
    ws.scratch_clear(_TUNE_KEY)
    return _tune_result(name, st, state, done=True)


@mcp.tool()
def edge_detect_tune(verdict: str = "", workspace: str = "") -> EdgeDetectTuneResult:
    """[derive] Adaptive edge detection — find the threshold by LOOKING, not guessing. Call with no
    verdict to start: it renders the mid-range edge map and asks a question. You look at the
    result and call again with `verdict`: 'reduce' (too many / noisy edges → the search
    raises the threshold), 'more' (subject not fully outlined → it lowers the threshold), or
    'good' (stop now). It's a binary search — middle first, then halve the range each step —
    so it converges in at most 3 probes (or after 2 'more' verdicts). The winning edge map is
    committed in place; `undo` restores the original. This is the repo's loop in one tool:
    the tool owns the search, you own the judgement."""
    name = _name(workspace)
    if not name:
        raise ValueError("no active workspace — open an asset first")
    ws = Workspace.resolve(name, HOME)
    state = ws.scratch_get(_TUNE_KEY)

    # start (or restart) — verdict ignored when there's no live search
    if not verdict or state is None:
        lo_b, hi_b = _TUNE_LEVEL
        cand = (lo_b + hi_b) // 2
        st = _tune_render(name, ws, cand)
        state = {"lo_b": lo_b, "hi_b": hi_b, "cand": cand, "probe": 1, "nos": 0}
        ws.scratch_set(_TUNE_KEY, state)
        return _tune_result(name, st, state, done=False)

    # continue — steer the bracket around the candidate the agent just judged
    v = verdict.strip().lower()
    if v in ("good", "stop", "done", "keep"):
        return _tune_commit(ws, name, state)
    if v in ("reduce", "fewer", "too_many", "noisy", "yes"):
        state["lo_b"] = state["cand"]            # fewer edges → raise level → upper half
    elif v in ("more", "increase", "too_few", "sparse", "no"):
        state["hi_b"] = state["cand"]            # more edges → lower level → lower half
        state["nos"] += 1
    else:
        raise ValueError("verdict must be 'reduce', 'more', or 'good'")

    state["probe"] += 1
    state["cand"] = (state["lo_b"] + state["hi_b"]) // 2
    if state["probe"] > _TUNE_MAX_PROBES or state["nos"] >= _TUNE_MAX_NOS:
        return _tune_commit(ws, name, state)

    st = _tune_render(name, ws, state["cand"])
    ws.scratch_set(_TUNE_KEY, state)
    return _tune_result(name, st, state, done=False)


# --- isolate: seed -> connect -> matte (the deterministic cutout) -----------
# Its own taxonomy category: compound board+geometry actions. `isolate` is
# self-contained (it opens & commits its own edit where it touches pixels), so this
# category is NOT part of the transform gate — the seed/connect/isolate flow reads
# and writes the board mask directly.

def _mask_state(name: str) -> MaskState:
    """Read the current mask counts for an asset into a MaskState result."""
    a = Board(HOME).sync().get("assets", {}).get(name, {})
    m = a.get("mask", {})
    return MaskState(workspace=name, dots=len(m.get("dots", [])),
                     outline=len(m.get("outline", [])), locked=bool(a.get("locked", False)))


@mcp.tool()
def seed(points: list[list[int]], workspace: str = "") -> MaskState:
    """[isolate] Drop rough seed dots on the asset's invisible mask, in image-pixel space.

    Place points loosely around the subject's edge; precision isn't needed — `connect`
    snaps a boundary through them. `points` is a list of `[x, y]` pairs (top-left origin)."""
    name = _name(workspace)
    board = Board(HOME)
    for p in points:
        board.add_dot(name, int(p[0]), int(p[1]))
    return _mask_state(name)


@mcp.tool()
def connect(workspace: str = "") -> MaskState:
    """[isolate] Connect the mask's seed dots into a boundary polygon: convex hull, then
    snap inward through every dot (deterministic). Stored on the mask; run `isolate` next."""
    name = _name(workspace)
    b = Board(HOME).sync()
    dots = b.get("assets", {}).get(name, {}).get("mask", {}).get("dots", [])
    Board(HOME).set_outline(name, ops.Geometry.hull_snap(dots))
    return _mask_state(name)


@mcp.tool()
def outline(epsilon: float = 2.0, workspace: str = "") -> MaskState:
    """[isolate] Trace the subject's boundary straight from the pixels — the unseeded
    counterpart to `connect`. Finds the outer contour of the matte (alpha > 0), takes the
    largest, and simplifies it into a sparse polygon (Douglas–Peucker), so it hugs every
    concavity a seeded convex boundary flies over — with no dots placed.

    Needs a matte: the alpha must already mark the subject (run `key_background` or another
    isolate-prep first). `epsilon` is the simplify tolerance in pixels — larger drops more
    vertices for a coarser outline. Lands in `mask.outline`; run `isolate` next to cut it."""
    name = _name(workspace)
    img = Workspace.resolve(name, HOME).current_array()
    poly = ops.Geometry.simplify_contour(img, epsilon)
    if len(poly) < 3:
        raise ValueError("no traceable outline — the alpha marks no subject; key/matte first")
    Board(HOME).set_outline(name, poly, label="outline")
    return _mask_state(name)


@mcp.tool()
def isolate(workspace: str = "") -> IsolateResult:
    """[isolate] Cut out the subject: fill the connected boundary into alpha (transparent
    background). Self-contained — opens and commits its own edit. Run `connect` first."""
    name = _name(workspace)
    b = Board(HOME).sync()
    outline = b.get("assets", {}).get(name, {}).get("mask", {}).get("outline", [])
    if len(outline) < 3:
        raise ValueError("no outline — call connect() first (needs >=3 seed dots)")
    ws = Workspace.resolve(name, HOME)
    ws.begin_edit("isolate (fill mask)")
    st = ws.apply("isolate", ops.Geometry.fill_polygon_alpha, {"polygon": outline})
    ws.commit_edit()
    Board(HOME).record_pixel_edit(name, "isolate")   # image-level undo step
    return IsolateResult(workspace=name, head=st["head"], steps=st["steps"],
                         current=st["current"], width=st["width"], height=st["height"],
                         chain=st["chain"])


def _seed_rect(rect, name: str, w: int, h: int) -> list[int]:
    """Resolve GrabCut's seed box: an explicit [x,y,w,h], else the mask's dots/outline bounding
    box, else the whole frame inset by ~6% so there's a background border to learn from."""
    if rect and len(rect) == 4:
        return [int(v) for v in rect]
    m = Board(HOME).sync().get("assets", {}).get(name, {}).get("mask", {})
    pts = (m.get("outline") or []) + (m.get("dots") or [])
    if len(pts) >= 2:
        xs = [int(p[0]) for p in pts]
        ys = [int(p[1]) for p in pts]
        return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    mx, my = int(w * 0.06), int(h * 0.06)             # inset frame → a bg border to seed from
    return [mx, my, w - 2 * mx, h - 2 * my]


@mcp.tool()
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
    name = _name(workspace)
    ws = Workspace.resolve(name, HOME)
    h, w = ws.current_array().shape[:2]
    box = _seed_rect(rect, name, w, h)
    ws.begin_edit("cutout (segment)")
    st = ws.apply("cutout", ops.Transform.segment, {"rect": box, "iterations": int(iterations)})
    ws.commit_edit()
    Board(HOME).record_pixel_edit(name, "cutout")     # image-level undo step
    return IsolateResult(workspace=name, head=st["head"], steps=st["steps"],
                         current=st["current"], width=st["width"], height=st["height"],
                         chain=st["chain"])


@mcp.tool()
def clear_seeds(workspace: str = "") -> MaskState:
    """[isolate] Remove all seed dots and the connected outline from the asset's mask."""
    name = _name(workspace)
    Board(HOME).clear_dots(name)
    return _mask_state(name)


# --- workspace controls (agent-facing too) ---------------------------------

@mcp.tool()
def undo(workspace: str = "") -> dict:
    """Step HEAD back one edit. Reversible; redo is still available."""
    return Workspace.resolve(workspace, HOME).undo()


@mcp.tool()
def redo(workspace: str = "") -> dict:
    """Step HEAD forward one edit (after an undo)."""
    return Workspace.resolve(workspace, HOME).redo()


@mcp.tool()
def status(workspace: str = "") -> dict:
    """Current workspace state: HEAD, the edit chain, can_undo/redo, current file."""
    return Workspace.resolve(workspace, HOME).status()


@mcp.tool()
def collapse(workspace: str = "") -> dict:
    """Verify: flatten the edit chain to the current image as the new base asset."""
    return Workspace.resolve(workspace, HOME).collapse()


@mcp.tool()
def move(x: int, y: int, scale: float = 0, workspace: str = "") -> dict:
    """Place an asset on the shared canvas: top-left x,y in px, and optional display
    scale (>0 to expand/contract; omit to leave scale unchanged). This is how I
    arrange the edit screen; a human can also drag/resize assets there."""
    name = _name(workspace)
    b = Board(HOME).place(name, x=x, y=y, scale=scale or None)
    return {"workspace": name, "placement": b["assets"].get(name), "z": b["order"].index(name)}


@mcp.tool()
def select(workspace: str = "") -> dict:
    """Select an asset and bring it to the front of the canvas (raise it above others)."""
    name = _name(workspace)
    b = Board(HOME).select(name)
    return {"selected": b["selected"], "order": b["order"]}


@mcp.tool()
def export(dest: str, workspace: str = "") -> dict:
    """Write the current image out to a path — the finished deliverable."""
    return Workspace.resolve(workspace, HOME).export(dest)


# --- helpers ---------------------------------------------------------------

def _free_port(preferred: int, host: str = "127.0.0.1") -> int:
    """Return `preferred` if bindable, else the next free port above it."""
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"no free port near {preferred}")


# --- entrypoint ------------------------------------------------------------

def _print(status: dict) -> None:
    print(f"[{status['workspace']}] head={status['head']}/{status['steps'] - 1}  "
          f"chain: {' -> '.join(status['chain'])}")
    print(f"  current: {status['current']}  ({status['width']}x{status['height']})")


def main() -> None:
    p = argparse.ArgumentParser(prog="defringe-ai")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("open", help="copy an asset into a workspace and start editing")
    sp.add_argument("path")
    sp.add_argument("--name", default="", help="workspace name (default: the filename)")

    sub.add_parser("ls", help="list open workspaces")
    for name in ("undo", "redo", "status", "collapse"):
        cp = sub.add_parser(name)
        cp.add_argument("workspace", nargs="?", default="", help="target workspace (default: active)")
    ep = sub.add_parser("export")
    ep.add_argument("dest")
    ep.add_argument("workspace", nargs="?", default="", help="target workspace (default: active)")

    ed = sub.add_parser("edit", help="begin an edit session (describe the change)")
    ed.add_argument("intent")
    ed.add_argument("workspace", nargs="?", default="")
    for name in ("cancel", "commit"):
        cp = sub.add_parser(name, help=f"{name} the edit session")
        cp.add_argument("workspace", nargs="?", default="")
    shp = sub.add_parser("shape", help="draw_shape — gated: needs an active edit session")
    shp.add_argument("shape", nargs="?", default="circle")
    shp.add_argument("workspace", nargs="?", default="")
    shp.add_argument("--x", type=int, default=-1)
    shp.add_argument("--y", type=int, default=-1)
    shp.add_argument("--width", type=int, default=-1)
    shp.add_argument("--height", type=int, default=-1)
    shp.add_argument("--anchor", default="center")
    shp.add_argument("--color", default="red")
    shp.add_argument("--thickness", type=int, default=3)
    shp.add_argument("--fill", action="store_true")

    mk = sub.add_parser("mark", help="drop dots at points — gated; e.g. mark '100,100 200,150'")
    mk.add_argument("points", help='space-separated x,y pairs: "100,100 200,150 300,80"')
    mk.add_argument("workspace", nargs="?", default="")
    mk.add_argument("--radius", type=int, default=4)
    mk.add_argument("--color", default="black")

    cn = sub.add_parser("edge_detect", help="edge map (Canny) → mask overlay; image untouched, undo clears it")
    cn.add_argument("workspace", nargs="?", default="")
    cn.add_argument("--lo", type=int, default=100)
    cn.add_argument("--hi", type=int, default=200)

    ln = sub.add_parser("line", help="draw a line (x1 y1 x2 y2) - gated; --dotted for dotted")
    ln.add_argument("x1", type=int)
    ln.add_argument("y1", type=int)
    ln.add_argument("x2", type=int)
    ln.add_argument("y2", type=int)
    ln.add_argument("workspace", nargs="?", default="")
    ln.add_argument("--color", default="red")
    ln.add_argument("--thickness", type=int, default=2)
    ln.add_argument("--dotted", action="store_true")

    srv = sub.add_parser("serve", help="run the MCP server")
    srv.add_argument("--http", action="store_true", help="streamable HTTP instead of stdio")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT)
    srv.add_argument("--preview", action="store_true", help="also serve a browser gallery")
    srv.add_argument("--preview-port", type=int, default=DEFAULT_PREVIEW_PORT)

    args = p.parse_args()

    if args.cmd == "open":
        _print(Workspace.open_asset(args.path, HOME, args.name or None).status())
    elif args.cmd == "ls":
        active = _get_active(HOME)
        for w in Workspace.list_all(HOME):
            print(f"  {'* ' if w == active else '  '}{w}")
    elif args.cmd == "undo":
        _print(Workspace.resolve(args.workspace, HOME).undo())
    elif args.cmd == "redo":
        _print(Workspace.resolve(args.workspace, HOME).redo())
    elif args.cmd == "status":
        _print(Workspace.resolve(args.workspace, HOME).status())
    elif args.cmd == "collapse":
        _print(Workspace.resolve(args.workspace, HOME).collapse())
        print("  collapsed — the current image is now the verified base.")
    elif args.cmd == "export":
        st = Workspace.resolve(args.workspace, HOME).export(args.dest)
        print(f"  exported -> {st['exported']}")
    elif args.cmd == "edit":
        st = Workspace.resolve(args.workspace, HOME).begin_edit(args.intent)
        Board(HOME).select(st["workspace"])
        print(f"  edit session OPEN on '{st['workspace']}' — intent: {args.intent!r}  (backup saved)")
        _print(st)
    elif args.cmd == "cancel":
        _print(Workspace.resolve(args.workspace, HOME).cancel_edit())
        print("  cancelled — restored from backup, as if nothing happened.")
    elif args.cmd == "commit":
        st = Workspace.resolve(args.workspace, HOME).commit_edit()
        label = st["chain"][-1] if st.get("chain") else "edit"
        Board(HOME).record_pixel_edit(st["workspace"], label)   # image-level undo step
        _print(st)
        print("  committed — changes kept, backup discarded.")
    elif args.cmd == "shape":
        try:
            ws = Workspace.resolve(args.workspace, HOME)
            if not ws.in_session():
                raise ValueError("no active edit session — run `edit \"<intent>\"` first")
            h, w = ws.current_array().shape[:2]
            g = ops.Shape.resolve_box(w, h, x=None if args.x < 0 else args.x,
                                y=None if args.y < 0 else args.y,
                                width=None if args.width < 0 else args.width,
                                height=None if args.height < 0 else args.height, anchor=args.anchor)
            st = ws.apply("draw_shape", ops.Shape.draw_shape,
                          {"shape": args.shape, "box": g["box"], "color": args.color,
                           "fill": args.fill, "thickness": args.thickness})
            _print(st)
            print(f"  drew {args.shape} @ bbox {g['box']} (anchor {args.anchor})"
                  f"{'  ⚠ clipped' if g['clipped'] else ''}")
        except ValueError as e:
            print(f"  REFUSED: {e}")
    elif args.cmd == "mark":
        pts = [[int(v) for v in pair.split(",")] for pair in args.points.split()]
        try:
            ws = Workspace.resolve(args.workspace, HOME)
            if not ws.in_session():
                raise ValueError("no active edit session — run `edit \"<intent>\"` first")
            _print(ws.apply("mark", ops.Annotate.mark, {"points": pts, "radius": args.radius, "color": args.color}))
            print(f"  marked {len(pts)} point(s): {pts}")
        except ValueError as e:
            print(f"  REFUSED: {e}")
    elif args.cmd == "edge_detect":
        try:
            name = args.workspace or _get_active(HOME) or ""
            if not name:
                raise ValueError("no active workspace — open an asset first")
            _print(_edge_detect_apply(name, args.lo, args.hi))   # mask overlay; image untouched
            print(f"  edge map (lo={args.lo}, hi={args.hi}) → mask overlay; undo clears it")
        except ValueError as e:
            print(f"  REFUSED: {e}")
    elif args.cmd == "line":
        try:
            ws = Workspace.resolve(args.workspace, HOME)
            if not ws.in_session():
                raise ValueError("no active edit session - run `edit \"<intent>\"` first")
            _print(ws.apply("draw_line", ops.Shape.draw_line,
                            {"x1": args.x1, "y1": args.y1, "x2": args.x2, "y2": args.y2,
                             "color": args.color, "thickness": args.thickness, "dotted": args.dotted}))
            print(f"  line ({args.x1},{args.y1})->({args.x2},{args.y2}) "
                  f"{'dotted ' if args.dotted else ''}{args.color}")
        except ValueError as e:
            print(f"  REFUSED: {e}")
    else:  # serve (default)
        http = getattr(args, "http", False)
        preview = getattr(args, "preview", False)
        host = getattr(args, "host", "127.0.0.1")
        if preview:
            from .web.app import serve_preview

            pport = _free_port(getattr(args, "preview_port", DEFAULT_PREVIEW_PORT), host)
            threading.Thread(target=serve_preview, args=(HOME, host, pport), daemon=True).start()
            print(f"[preview] gallery: http://{host}:{pport}", flush=True)
        if http:
            mcp.settings.host = host
            mcp.settings.port = _free_port(getattr(args, "port", DEFAULT_HTTP_PORT), host)
            print(f"[mcp] streamable-http: http://{host}:{mcp.settings.port}/mcp", flush=True)
            mcp.run(transport="streamable-http")
        else:
            mcp.run()


if __name__ == "__main__":
    main()
