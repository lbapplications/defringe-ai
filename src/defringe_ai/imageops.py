"""Deterministic raster transforms, all on NumPy RGBA arrays (H, W, 4) uint8.

This is the MxNxRxGxB substrate: every op takes an ndarray and returns one, so
the pixel-level passes read as plain array math. `sharp`/Pillow are used only for
fast resample; the interesting passes (key, defringe) are raw NumPy + one cv2 call.
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

RGBA = np.ndarray  # (H, W, 4) uint8, alias for intent


# --- I/O -------------------------------------------------------------------

def load(path: str) -> RGBA:
    """Read any image as (H, W, 4) uint8 RGBA."""
    return np.asarray(Image.open(path).convert("RGBA"))


def save(img: RGBA, path: str) -> tuple[int, int]:
    """Write an RGBA array as PNG. Returns (width, height)."""
    Image.fromarray(img, mode="RGBA").save(path)
    h, w = img.shape[:2]
    return w, h


# --- helpers ---------------------------------------------------------------

def _luminance(rgb: np.ndarray) -> np.ndarray:
    """Rec.601 luminance, float32 (H, W)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return 0.299 * r + 0.587 * g + 0.114 * b


def _min3x3(a: np.ndarray) -> np.ndarray:
    """3x3 neighbourhood minimum == a single-step erosion of a uint8 plane."""
    return cv2.erode(a, np.ones((3, 3), np.uint8))


# --- tools -----------------------------------------------------------------

def key_background(
    img: RGBA,
    bg: str = "white",
    lo: int = 40,
    hi: int = 90,
) -> RGBA:
    """Threshold a flat background to alpha with a soft LO..HI ramp for AA edges.

    A per-pixel "foreground-ness" score is built, then mapped: alpha = 0 below LO,
    255 above HI, linear between.
      - bg="black": score = max(r,g,b)          (bright subject on black -> keep)
      - bg="white": score = 255 - luminance     (dark subject on white  -> keep)
      - bg="#rrggbb": score = distance from that colour, scaled to 0..255
    """
    rgb = img[..., :3].astype(np.float32)

    if bg == "black":
        score = rgb.max(axis=-1)
    elif bg == "white":
        score = 255.0 - _luminance(rgb)
    else:
        key = _parse_color(bg).astype(np.float32)
        dist = np.linalg.norm(rgb - key, axis=-1)      # 0..~441
        score = np.clip(dist / (441.673 / 255.0), 0, 255)

    ramp = np.clip((score - lo) * (255.0 / max(hi - lo, 1)), 0, 255)
    out = img.copy()
    out[..., 3] = ramp.astype(np.uint8)
    return out


def trim_alpha(img: RGBA) -> RGBA:
    """Crop to the bounding box of alpha > 0. Returns unchanged if fully transparent."""
    ys, xs = np.nonzero(img[..., 3])
    if len(xs) == 0:
        return img
    return img[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]


def crop(img: RGBA, x: int, y: int, w: int, h: int) -> RGBA:
    """Carve out a sub-rect (clamped to bounds)."""
    H, W = img.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    return img[y0:y1, x0:x1]


def defringe(
    img: RGBA,
    erode_px: int = 1,
    burn: float = 0.45,
    rim_lum: float = 135.0,
    transparent_below: int = 16,
) -> RGBA:
    """Kill the white matte fringe left by keying art off a light background.

    1) E = erode the alpha inward `erode_px` (3x3 MIN each step) -> shrinks matte.
    2) An edge pixel is one where the eroded alpha is not fully opaque (E < 250),
       OR it touches a near-transparent neighbour AND is bright (lum > rim_lum).
    3) Burn (darken) edge RGB by `burn` so the rim reads as a dark line that melts
       into a dark background instead of glowing. Alpha is replaced by E.
    """
    alpha = img[..., 3]
    e = alpha
    for _ in range(max(erode_px, 1)):
        e = _min3x3(e)

    neighbour_min = _min3x3(alpha)
    touches_transparent = neighbour_min < transparent_below
    lum = _luminance(img[..., :3].astype(np.float32))

    keep = e > 0
    edge = keep & ((e < 250) | (touches_transparent & (lum > rim_lum)))

    out = img.copy().astype(np.float32)
    out[edge, :3] *= burn
    out = out.astype(np.uint8)
    out[..., 3] = e
    return out


def upscale(img: RGBA, factor: float = 2.0, sharpen: float = 0.6) -> RGBA:
    """Lanczos3 resample + a gentle unsharp pass. Holds linework; adds no real detail."""
    h, w = img.shape[:2]
    pil = Image.fromarray(img, mode="RGBA").resize(
        (round(w * factor), round(h * factor)), Image.LANCZOS
    )
    if sharpen > 0:
        from PIL import ImageFilter

        pil = pil.filter(
            ImageFilter.UnsharpMask(radius=1.0, percent=int(sharpen * 100), threshold=1)
        )
    return np.asarray(pil)


def silhouette_mask(img: RGBA) -> RGBA:
    """Emit just the alpha shape (white RGB, original alpha) for CSS mask-image tricks."""
    out = np.zeros_like(img)
    out[..., :3] = 255
    out[..., 3] = img[..., 3]
    return out


# --- misc ------------------------------------------------------------------

def _parse_color(s: str) -> np.ndarray:
    """'#rrggbb' or 'r,g,b' -> uint8 array [r,g,b]."""
    s = s.strip()
    if s.startswith("#"):
        s = s[1:]
        return np.array([int(s[i: i + 2], 16) for i in (0, 2, 4)], np.uint8)
    return np.array([int(p) for p in s.split(",")[:3]], np.uint8)
