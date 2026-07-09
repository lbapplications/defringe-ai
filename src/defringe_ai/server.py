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
import socket
import threading

from mcp.server.fastmcp import FastMCP

from . import imageops as ops
from .board import Board
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
    "shape":     ["draw_shape"],                         # draw primitives onto the image
    "annotate":  ["mark"],                               # drop debug/seed dots
    "arrange":   ["move", "select"],                     # canvas layout — not gated
    "workspace": ["open_asset", "list_workspaces", "list_shapes", "status", "undo", "redo", "collapse", "export"],
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
    return Workspace.resolve(workspace, HOME).commit_edit()


@mcp.tool()
def list_shapes() -> dict:
    """The registered shapes, anchors, and named colours that draw_shape understands."""
    return {"shapes": list(ops.SHAPES), "anchors": list(ops._ANCHORS), "colors": list(ops._NAMED_COLORS)}


@mcp.tool()
def mark(points: list[list[int]], radius: int = 4, color: str = "black", workspace: str = "") -> dict:
    """[annotate · gated] Drop a tiny filled dot at each [x, y] in `points` — for flagging
    seed points or locations to eyeball. Coords are (x, y), top-left origin, x→right,
    y→down. Points outside the frame are skipped. Gated: call edit(...) first."""
    st = _apply("mark", ops.mark, workspace, points=points, radius=radius, color=color)
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
    g = ops.resolve_box(w, h, x=None if x < 0 else x, y=None if y < 0 else y,
                        width=None if width < 0 else width,
                        height=None if height < 0 else height, anchor=anchor)
    st = ws.apply("draw_shape", ops.draw_shape,
                  {"shape": shape, "box": g["box"], "color": color, "fill": fill, "thickness": thickness})
    return {**st, "drew": {"shape": shape, "anchor": anchor,
                           "center": list(g["center"]), "bbox": list(g["box"])},
            "clipped": g["clipped"]}


# For every tool below, `workspace` is optional: name it to target a specific asset,
# or leave it blank to act on the last workspace touched.

@mcp.tool()
def key_background(bg: str = "white", lo: int = 40, hi: int = 90, workspace: str = "") -> dict:
    """Threshold a flat background to alpha with a soft lo..hi ramp.
    bg is 'white', 'black', '#rrggbb', or 'r,g,b'."""
    return _apply("key_background", ops.key_background, workspace, bg=bg, lo=lo, hi=hi)


@mcp.tool()
def trim_alpha(workspace: str = "") -> dict:
    """Crop to the content bounding box (alpha > 0)."""
    return _apply("trim_alpha", ops.trim_alpha, workspace)


@mcp.tool()
def crop(x: int, y: int, w: int, h: int, workspace: str = "") -> dict:
    """Carve a sub-rect out of the image (extract-region)."""
    return _apply("crop", ops.crop, workspace, x=x, y=y, w=w, h=h)


@mcp.tool()
def defringe(erode_px: int = 1, burn: float = 0.45, rim_lum: float = 135.0, workspace: str = "") -> dict:
    """Erode the alpha edge to drop the matte fringe, then burn the remaining edge
    pixels so a white/halo rim melts into a dark background."""
    return _apply("defringe", ops.defringe, workspace, erode_px=erode_px, burn=burn, rim_lum=rim_lum)


@mcp.tool()
def upscale(factor: float = 2.0, sharpen: float = 0.6, workspace: str = "") -> dict:
    """Lanczos3 resample + gentle sharpen. Holds linework; adds no real detail."""
    return _apply("upscale", ops.upscale, workspace, factor=factor, sharpen=sharpen)


@mcp.tool()
def silhouette_mask(workspace: str = "") -> dict:
    """Emit just the alpha shape (white RGB + original alpha) for CSS mask-image."""
    return _apply("silhouette_mask", ops.silhouette_mask, workspace)


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
        from .workspace import _get_active

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
        _print(Workspace.resolve(args.workspace, HOME).commit_edit())
        print("  committed — changes kept, backup discarded.")
    elif args.cmd == "shape":
        try:
            ws = Workspace.resolve(args.workspace, HOME)
            if not ws.in_session():
                raise ValueError("no active edit session — run `edit \"<intent>\"` first")
            h, w = ws.current_array().shape[:2]
            g = ops.resolve_box(w, h, x=None if args.x < 0 else args.x,
                                y=None if args.y < 0 else args.y,
                                width=None if args.width < 0 else args.width,
                                height=None if args.height < 0 else args.height, anchor=args.anchor)
            st = ws.apply("draw_shape", ops.draw_shape,
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
            _print(ws.apply("mark", ops.mark, {"points": pts, "radius": args.radius, "color": args.color}))
            print(f"  marked {len(pts)} point(s): {pts}")
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
