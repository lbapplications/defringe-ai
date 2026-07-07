"""defringe-ai MCP server.

Exposes the deterministic raster transforms as MCP tools. Every tool takes an
`image` reference (a filesystem path OR a session id returned by a prior tool),
writes a PNG into the output dir, and returns {session, path, width, height} so a
vision model can chain ops and re-read the result to self-correct.

Run:
  defringe-ai                       # stdio (local agent)
  defringe-ai --http --preview      # HTTP on a server + browser gallery
"""

from __future__ import annotations

import argparse
import os
import threading
import uuid

import numpy as np
from mcp.server.fastmcp import FastMCP

from . import imageops as ops

OUTPUT_DIR = os.environ.get("DEFRINGE_OUT", "out")
SESSIONS: dict[str, np.ndarray] = {}

mcp = FastMCP("defringe-ai")


# --- session plumbing ------------------------------------------------------

def _resolve(image: str) -> np.ndarray:
    """Turn an image reference (session id or path) into an RGBA array."""
    if image in SESSIONS:
        return SESSIONS[image]
    if os.path.exists(image):
        return ops.load(image)
    raise ValueError(f"unknown image reference: {image!r} (not a session id or a path)")


def _emit(img: np.ndarray, label: str) -> dict:
    """Persist a result, register a session, and return the agent-facing handle."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sid = f"{label}-{uuid.uuid4().hex[:8]}"
    path = os.path.join(OUTPUT_DIR, f"{sid}.png")
    w, h = ops.save(img, path)
    SESSIONS[sid] = img
    return {"session": sid, "path": path, "width": w, "height": h}


# --- tools -----------------------------------------------------------------

@mcp.tool()
def open_image(path: str) -> dict:
    """Load an image from disk into a session so later tools can reference it."""
    return _emit(ops.load(path), "open")


@mcp.tool()
def key_background(image: str, bg: str = "white", lo: int = 40, hi: int = 90) -> dict:
    """Threshold a flat background to alpha with a soft LO..HI ramp for AA edges.
    bg is 'white', 'black', '#rrggbb', or 'r,g,b'."""
    return _emit(ops.key_background(_resolve(image), bg=bg, lo=lo, hi=hi), "key")


@mcp.tool()
def trim_alpha(image: str) -> dict:
    """Crop to the content bounding box (alpha > 0)."""
    return _emit(ops.trim_alpha(_resolve(image)), "trim")


@mcp.tool()
def crop(image: str, x: int, y: int, w: int, h: int) -> dict:
    """Carve a sub-rect out of the image (extract-region)."""
    return _emit(ops.crop(_resolve(image), x, y, w, h), "crop")


@mcp.tool()
def defringe(
    image: str,
    erode_px: int = 1,
    burn: float = 0.45,
    rim_lum: float = 135.0,
) -> dict:
    """Erode the alpha edge `erode_px` px to drop the matte fringe, then burn the
    remaining edge pixels so a white/halo rim melts into a dark background."""
    return _emit(
        ops.defringe(_resolve(image), erode_px=erode_px, burn=burn, rim_lum=rim_lum),
        "defringe",
    )


@mcp.tool()
def upscale(image: str, factor: float = 2.0, sharpen: float = 0.6) -> dict:
    """Lanczos3 resample + gentle sharpen. Holds linework; adds no real detail."""
    return _emit(ops.upscale(_resolve(image), factor=factor, sharpen=sharpen), "upscale")


@mcp.tool()
def silhouette_mask(image: str) -> dict:
    """Emit just the alpha shape (white RGB + original alpha) for CSS mask-image."""
    return _emit(ops.silhouette_mask(_resolve(image)), "mask")


# --- entrypoint ------------------------------------------------------------

def main() -> None:
    global OUTPUT_DIR
    p = argparse.ArgumentParser(prog="defringe-ai")
    p.add_argument("--http", action="store_true", help="serve over streamable HTTP instead of stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--preview", action="store_true", help="also serve a browser gallery of the output dir")
    p.add_argument("--preview-port", type=int, default=8787)
    p.add_argument("--out", default=OUTPUT_DIR, help="output directory (default: ./out)")
    args = p.parse_args()

    OUTPUT_DIR = args.out
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.preview:
        from .preview import serve_preview

        threading.Thread(
            target=serve_preview, args=(OUTPUT_DIR, args.host, args.preview_port), daemon=True
        ).start()
        print(f"[preview] gallery: http://{args.host}:{args.preview_port}", flush=True)

    if args.http:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
