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


def canny(img: RGBA, lo: int = 100, hi: int = 200) -> RGBA:
    """Canny edge map: white edges on opaque black (mirrors cv2.Canny(frame, lo, hi)).

    The hysteresis thresholds are `lo` (weak) and `hi` (strong) — the 100/200 default
    is the classic pairing. Runs across the RGB channels (max gradient), like feeding a
    colour frame straight into cv2.Canny. Output is a full RGBA snapshot so it flows
    through the edit chain like any other transform. This is the *edge signal*, not an
    isolation — closing the gaps + findContours + fill turns it into a cutout.
    """
    edges = cv2.Canny(img[..., :3], lo, hi)      # (H, W) uint8, 0 or 255
    out = np.zeros_like(img)
    out[..., :3] = edges[..., None]              # white where an edge fired
    out[..., 3] = 255                            # opaque so the black bg reads on the canvas
    return out


# --- shapes ----------------------------------------------------------------
# All shapes share one spatial model: an (x, y) anchor point + a (width, height)
# bounding box + an `anchor` naming which part of the box lands at (x, y). Coords are
# pixels, (x, y) top-left origin, x→right, y→down (see docs/coordinates.md).

SHAPES = ("circle", "ellipse", "square", "rectangle", "triangle")

_NAMED_COLORS = {
    "red": (255, 0, 0, 255), "green": (0, 200, 0, 255), "blue": (0, 90, 255, 255),
    "white": (255, 255, 255, 255), "black": (0, 0, 0, 255), "yellow": (255, 210, 0, 255),
    "orange": (255, 140, 0, 255), "cyan": (0, 200, 220, 255), "magenta": (230, 0, 200, 255),
    "gray": (128, 128, 128, 255), "grey": (128, 128, 128, 255), "transparent": (0, 0, 0, 0),
}

# where in the box the anchor point sits: name -> (horizontal frac, vertical frac)
_ANCHORS = {
    "top_left": (0, 0), "top": (0.5, 0), "top_right": (1, 0),
    "left": (0, 0.5), "center": (0.5, 0.5), "right": (1, 0.5),
    "bottom_left": (0, 1), "bottom": (0.5, 1), "bottom_right": (1, 1),
}


def parse_color(s) -> tuple:
    """'red' | '#rrggbb[aa]' | 'r,g,b[,a]' | already-a-tuple  ->  (R,G,B,A) uint8."""
    if isinstance(s, (tuple, list)):
        c = list(int(v) for v in s)
    elif s.strip().startswith("#"):
        h = s.strip()[1:]
        c = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
    elif "," in s:
        c = [int(v) for v in s.split(",")]
    else:
        key = s.strip().lower()
        if key not in _NAMED_COLORS:
            raise ValueError(f"unknown colour {s!r}; use a name, #hex, or r,g,b[,a]")
        return _NAMED_COLORS[key]
    if len(c) == 3:
        c.append(255)
    return tuple(c[:4])


def resolve_box(W, H, x=None, y=None, width=None, height=None, anchor="center") -> dict:
    """Turn (anchor point + size + anchor name) into a concrete pixel box.
    Defaults: size = half the short side, anchor point = image centre. height defaults
    to width (symmetric). Returns {box:(x0,y0,x1,y1), center:(cx,cy), clipped:bool}."""
    if anchor not in _ANCHORS:
        raise ValueError(f"unknown anchor {anchor!r}; one of {list(_ANCHORS)}")
    bw = (min(W, H) // 2) if width is None else int(width)
    bh = bw if height is None else int(height)
    ax = (W // 2) if x is None else int(x)
    ay = (H // 2) if y is None else int(y)
    fx, fy = _ANCHORS[anchor]
    x0 = round(ax - bw * fx)
    y0 = round(ay - bh * fy)
    x1, y1 = x0 + bw, y0 + bh
    clipped = x0 < 0 or y0 < 0 or x1 > W or y1 > H
    return {"box": (x0, y0, x1, y1), "center": (x0 + bw // 2, y0 + bh // 2), "clipped": clipped}


def mark(img: RGBA, points, radius=4, color="black") -> RGBA:
    """Drop a tiny filled dot at each [x, y] point (top-left origin, x→right, y→down).
    For flagging seed points / locations to eyeball. Points outside the frame are skipped."""
    h, w = img.shape[:2]
    col = parse_color(color)
    out = img.copy()
    for p in points:
        x, y = int(p[0]), int(p[1])
        if 0 <= x < w and 0 <= y < h:
            cv2.circle(out, (x, y), int(radius), col, -1, lineType=cv2.LINE_AA)
    return out


def draw_shape(img: RGBA, shape="circle", box=None, color=(255, 0, 0, 255),
               fill=False, thickness=3) -> RGBA:
    """Draw one registered primitive inside a resolved pixel box (x0,y0,x1,y1)."""
    if shape not in SHAPES:
        raise ValueError(f"unknown shape {shape!r}; registered: {list(SHAPES)}")
    x0, y0, x1, y1 = (int(v) for v in box)
    col = parse_color(color)
    t = -1 if fill else max(1, int(thickness))       # cv2: -1 fills
    out = img.copy()
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    if shape == "circle":
        cv2.circle(out, (cx, cy), min(x1 - x0, y1 - y0) // 2, col, t, lineType=cv2.LINE_AA)
    elif shape == "ellipse":
        cv2.ellipse(out, (cx, cy), ((x1 - x0) // 2, (y1 - y0) // 2), 0, 0, 360, col, t, lineType=cv2.LINE_AA)
    elif shape in ("square", "rectangle"):
        cv2.rectangle(out, (x0, y0), (x1, y1), col, t, lineType=cv2.LINE_AA)
    elif shape == "triangle":
        pts = np.array([[cx, y0], [x0, y1], [x1, y1]], np.int32)
        if fill:
            cv2.fillPoly(out, [pts], col, lineType=cv2.LINE_AA)
        else:
            cv2.polylines(out, [pts], True, col, max(1, int(thickness)), lineType=cv2.LINE_AA)
    return out


# --- misc ------------------------------------------------------------------

def _parse_color(s: str) -> np.ndarray:
    """'#rrggbb' or 'r,g,b' -> uint8 array [r,g,b]."""
    s = s.strip()
    if s.startswith("#"):
        s = s[1:]
        return np.array([int(s[i: i + 2], 16) for i in (0, 2, 4)], np.uint8)
    return np.array([int(p) for p in s.split(",")[:3]], np.uint8)
