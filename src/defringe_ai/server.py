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
from .workspace import HOME, Workspace

# Uncommon defaults, deliberately off the 8000/8080/3000 beaten path so the server
# can run beside whatever an artist already has open. Auto-bumped if taken anyway.
DEFAULT_HTTP_PORT = 47823
DEFAULT_PREVIEW_PORT = 47824

mcp = FastMCP("defringe-ai")


# --- transform registry: name -> (function, param docstring) ---------------
# Each applies to the active workspace HEAD via workspace.apply.

def _apply(op: str, fn, **params) -> dict:
    return Workspace.active(HOME).apply(op, fn, params)


@mcp.tool()
def open_asset(path: str) -> dict:
    """Copy an external asset into a fresh workspace and make it the active edit target."""
    return Workspace.open_asset(path, HOME).status()


@mcp.tool()
def key_background(bg: str = "white", lo: int = 40, hi: int = 90) -> dict:
    """Threshold a flat background to alpha with a soft lo..hi ramp.
    bg is 'white', 'black', '#rrggbb', or 'r,g,b'."""
    return _apply("key_background", ops.key_background, bg=bg, lo=lo, hi=hi)


@mcp.tool()
def trim_alpha() -> dict:
    """Crop to the content bounding box (alpha > 0)."""
    return _apply("trim_alpha", ops.trim_alpha)


@mcp.tool()
def crop(x: int, y: int, w: int, h: int) -> dict:
    """Carve a sub-rect out of the image (extract-region)."""
    return _apply("crop", ops.crop, x=x, y=y, w=w, h=h)


@mcp.tool()
def defringe(erode_px: int = 1, burn: float = 0.45, rim_lum: float = 135.0) -> dict:
    """Erode the alpha edge to drop the matte fringe, then burn the remaining edge
    pixels so a white/halo rim melts into a dark background."""
    return _apply("defringe", ops.defringe, erode_px=erode_px, burn=burn, rim_lum=rim_lum)


@mcp.tool()
def upscale(factor: float = 2.0, sharpen: float = 0.6) -> dict:
    """Lanczos3 resample + gentle sharpen. Holds linework; adds no real detail."""
    return _apply("upscale", ops.upscale, factor=factor, sharpen=sharpen)


@mcp.tool()
def silhouette_mask() -> dict:
    """Emit just the alpha shape (white RGB + original alpha) for CSS mask-image."""
    return _apply("silhouette_mask", ops.silhouette_mask)


# --- workspace controls (agent-facing too) ---------------------------------

@mcp.tool()
def undo() -> dict:
    """Step HEAD back one edit. Reversible; redo is still available."""
    return Workspace.active(HOME).undo()


@mcp.tool()
def redo() -> dict:
    """Step HEAD forward one edit (after an undo)."""
    return Workspace.active(HOME).redo()


@mcp.tool()
def status() -> dict:
    """Current workspace state: HEAD, the edit chain, can_undo/redo, current file."""
    return Workspace.active(HOME).status()


@mcp.tool()
def collapse() -> dict:
    """Verify: flatten the edit chain to the current image as the new base asset."""
    return Workspace.active(HOME).collapse()


@mcp.tool()
def export(dest: str) -> dict:
    """Write the current image out to a path — the finished deliverable."""
    return Workspace.active(HOME).export(dest)


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

    sub.add_parser("undo")
    sub.add_parser("redo")
    sub.add_parser("status")
    sub.add_parser("collapse", help="verify: flatten the edit chain to the current asset")
    ep = sub.add_parser("export")
    ep.add_argument("dest")

    srv = sub.add_parser("serve", help="run the MCP server")
    srv.add_argument("--http", action="store_true", help="streamable HTTP instead of stdio")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT)
    srv.add_argument("--preview", action="store_true", help="also serve a browser gallery")
    srv.add_argument("--preview-port", type=int, default=DEFAULT_PREVIEW_PORT)

    args = p.parse_args()

    if args.cmd == "open":
        _print(Workspace.open_asset(args.path, HOME).status())
    elif args.cmd == "undo":
        _print(Workspace.active(HOME).undo())
    elif args.cmd == "redo":
        _print(Workspace.active(HOME).redo())
    elif args.cmd == "status":
        _print(Workspace.active(HOME).status())
    elif args.cmd == "collapse":
        _print(Workspace.active(HOME).collapse())
        print("  collapsed — the current image is now the verified base.")
    elif args.cmd == "export":
        st = Workspace.active(HOME).export(args.dest)
        print(f"  exported -> {st['exported']}")
    else:  # serve (default)
        http = getattr(args, "http", False)
        preview = getattr(args, "preview", False)
        host = getattr(args, "host", "127.0.0.1")
        if preview:
            from .preview import serve_preview

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
