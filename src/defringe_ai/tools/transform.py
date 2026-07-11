"""[transform · gated] Whole-image pixel edits — each refuses unless an edit session is open."""

from __future__ import annotations

from .. import imageops as ops
from . import core

# `workspace` is optional on every tool: name it to target a specific asset, or leave it
# blank to act on the last workspace touched.
transform = core.category("transform", gated=True)


@transform
def key_background(bg: str = "white", lo: int = 40, hi: int = 90, workspace: str = "") -> dict:
    """Threshold a flat background to alpha with a soft lo..hi ramp.
    bg is 'white', 'black', '#rrggbb', or 'r,g,b'."""
    return core.apply("key_background", ops.Transform.key_background, workspace, bg=bg, lo=lo, hi=hi)


@transform
def trim_alpha(workspace: str = "") -> dict:
    """Crop to the content bounding box (alpha > 0)."""
    return core.apply("trim_alpha", ops.Transform.trim_alpha, workspace)


@transform
def crop(x: int, y: int, w: int, h: int, workspace: str = "") -> dict:
    """Carve a sub-rect out of the image (extract-region)."""
    return core.apply("crop", ops.Transform.crop, workspace, x=x, y=y, w=w, h=h)


@transform
def defringe(erode_px: int = 1, burn: float = 0.45, rim_lum: float = 135.0, workspace: str = "") -> dict:
    """Erode the alpha edge to drop the matte fringe, then burn the remaining edge
    pixels so a white/halo rim melts into a dark background."""
    return core.apply("defringe", ops.Transform.defringe, workspace, erode_px=erode_px, burn=burn, rim_lum=rim_lum)


@transform
def upscale(factor: float = 2.0, sharpen: float = 0.6, workspace: str = "") -> dict:
    """Lanczos3 resample + gentle sharpen. Holds linework; adds no real detail."""
    return core.apply("upscale", ops.Transform.upscale, workspace, factor=factor, sharpen=sharpen)


@transform
def silhouette_mask(workspace: str = "") -> dict:
    """Emit just the alpha shape (white RGB + original alpha) for CSS mask-image."""
    return core.apply("silhouette_mask", ops.Transform.silhouette_mask, workspace)
