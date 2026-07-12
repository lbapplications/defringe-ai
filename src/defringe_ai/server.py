"""defringe-ai — MCP server + CLI, both thin front-ends over the workspace engine.

The workspace (on-disk asset + reversible edit chain) is the source of truth. Every
transform tool applies to the active workspace's HEAD and returns its status, so a
vision agent can chain edits, undo, and collapse — and a human can drive the exact
same workspace from the CLI.

  defringe-ai open ./art/octopus.png     # copy an asset in, start editing (human)
  defringe-ai serve --preview            # run the MCP server + browser gallery
  defringe-ai undo | redo | status | collapse | export out.png

The tools themselves live in the ``tools/`` package, one module per taxonomy category
(``tools/transform.py``, ``tools/isolate.py``, …); this module is the facade that gathers
them onto the MCP server and drives the CLI. `HOME` is proxied to ``tools.core`` so tests
can repoint the workspace root in one place.
"""

from __future__ import annotations

import argparse
import socket
import threading

from . import imageops as ops
from . import tools
from .board import Board
from .projection import Projection
from .registry import Registry
from .tools import GATED, TAXONOMY, core, mcp
# Re-export every tool as a module attribute, so the CLI, tests, and any caller can reach
# `server.<tool>` exactly as before the split into tools/.
from .tools.annotate import mark
from .tools.arrange import move, select
from .tools.derive import _edge_detect_apply, edge_detect, edge_detect_tune
from .tools.isolate import clear_seeds, connect, cutout, isolate, outline, seed
from .tools.manage import (
    collapse, export, list_shapes, list_workspaces, open_asset, redo, status, taxonomy, undo,
)
from .tools.merge import merge, revert_merge
from .tools.session import cancel, commit, edit
from .tools.shape import draw_line, draw_shape
from .tools.transform import (
    crop, defringe, key_background, silhouette_mask, trim_alpha, upscale,
)
from .workspace import Workspace, _get_active

# Uncommon defaults, deliberately off the 8000/8080/3000 beaten path so the server
# can run beside whatever an artist already has open. Auto-bumped if taken anyway.
DEFAULT_HTTP_PORT = 47823
DEFAULT_PREVIEW_PORT = 47824


def __getattr__(attr: str):
    """Proxy ``server.HOME`` to the single source of truth in ``tools.core`` — so the whole
    tool surface reads one live workspace root (tests repoint ``core.HOME`` and it reaches here)."""
    if attr == "HOME":
        return core.HOME
    raise AttributeError(f"module {__name__!r} has no attribute {attr!r}")


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

    mg = sub.add_parser("merge", help="ship the current state to the user's real file (approved commit)")
    mg.add_argument("workspace", nargs="?", default="", help="target workspace (default: active)")

    rv = sub.add_parser("revert_merge", help="restore a previously approved commit onto the real file")
    rv.add_argument("commit", type=int, help="a commit index from a prior merge's ledger")
    rv.add_argument("workspace", nargs="?", default="", help="target workspace (default: active)")

    srv = sub.add_parser("serve", help="run the MCP server")
    srv.add_argument("--http", action="store_true", help="streamable HTTP instead of stdio")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT)
    srv.add_argument("--preview", action="store_true", help="also serve a browser gallery")
    srv.add_argument("--preview-port", type=int, default=DEFAULT_PREVIEW_PORT)

    args = p.parse_args()
    HOME = core.HOME

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
    elif args.cmd in ("merge", "revert_merge"):
        name = args.workspace or _get_active(HOME) or ""
        loc = Registry(HOME).locate(name) if name else None
        if not loc:
            print("  REFUSED: no such workspace — open one first")
        else:
            pid, aid = loc
            proj = Projection(HOME, pid, aid)
            ws = Workspace.locate(name, HOME)
            if args.cmd == "merge":
                res = proj.merge(ws)
                print(f"  merged '{name}' → {res['merged']} (commit {res['commit']}; ledger {res['commits']})")
            else:
                res = proj.restore(ws, args.commit)
                print(f"  restored '{name}' ← commit {res['restored']} → {proj.real}")
            _print(ws.status())
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
