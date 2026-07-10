"""`Shape` — draw registered primitives + straight lines onto the image.

All shapes share one spatial model: an (x, y) anchor point + a (width, height) bounding
box + an `anchor` naming which part of the box lands at (x, y). Coords are pixels,
(x, y) top-left origin, x->right, y->down (see docs/coordinates.md).
"""

from __future__ import annotations

import cv2
import numpy as np

from ._core import RGBA, Color


class Shape:
    """Draw primitives (fill or stroke) + guide lines. RGBA -> RGBA."""

    NAMES = ("circle", "ellipse", "square", "rectangle", "triangle")

    # where in the box the anchor point sits: name -> (horizontal frac, vertical frac)
    ANCHORS = {
        "top_left": (0, 0), "top": (0.5, 0), "top_right": (1, 0),
        "left": (0, 0.5), "center": (0.5, 0.5), "right": (1, 0.5),
        "bottom_left": (0, 1), "bottom": (0.5, 1), "bottom_right": (1, 1),
    }

    @staticmethod
    def resolve_box(W, H, x=None, y=None, width=None, height=None, anchor="center") -> dict:
        """Turn (anchor point + size + anchor name) into a concrete pixel box.
        Defaults: size = half the short side, anchor point = image centre. height defaults
        to width (symmetric). Returns {box:(x0,y0,x1,y1), center:(cx,cy), clipped:bool}."""
        if anchor not in Shape.ANCHORS:
            raise ValueError(f"unknown anchor {anchor!r}; one of {list(Shape.ANCHORS)}")
        bw = (min(W, H) // 2) if width is None else int(width)
        bh = bw if height is None else int(height)
        ax = (W // 2) if x is None else int(x)
        ay = (H // 2) if y is None else int(y)
        fx, fy = Shape.ANCHORS[anchor]
        x0 = round(ax - bw * fx)
        y0 = round(ay - bh * fy)
        x1, y1 = x0 + bw, y0 + bh
        clipped = x0 < 0 or y0 < 0 or x1 > W or y1 > H
        return {"box": (x0, y0, x1, y1), "center": (x0 + bw // 2, y0 + bh // 2), "clipped": clipped}

    @staticmethod
    def draw_shape(img: RGBA, shape="circle", box=None, color=(255, 0, 0, 255),
                   fill=False, thickness=3) -> RGBA:
        """Draw one registered primitive inside a resolved pixel box (x0,y0,x1,y1)."""
        if shape not in Shape.NAMES:
            raise ValueError(f"unknown shape {shape!r}; registered: {list(Shape.NAMES)}")
        x0, y0, x1, y1 = (int(v) for v in box)
        col = Color.parse(color)
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

    @staticmethod
    def draw_line(img: RGBA, x1: int, y1: int, x2: int, y2: int,
                  color="red", thickness: int = 2, dotted: bool = False, gap: int = 0) -> RGBA:
        """Draw a straight line from (x1,y1) to (x2,y2). (x,y) top-left origin, x->right, y->down.

        solid  (dotted=False): one anti-aliased cv2 line.
        dotted (dotted=True):  filled dots stepped every `gap` px along the line (gap
                               defaults to ~3x thickness) - a see-through guide/crosshair.
        """
        out = img.copy()
        col = Color.parse(color)
        p1, p2 = (int(x1), int(y1)), (int(x2), int(y2))
        t = max(1, int(thickness))
        if not dotted:
            cv2.line(out, p1, p2, col, t, lineType=cv2.LINE_AA)
        else:
            dist = int(round(float(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))))
            step = gap if gap > 0 else max(3, t * 3)
            n = max(1, dist // step)
            for i in range(n + 1):
                f = i / n
                x = int(round(p1[0] + (p2[0] - p1[0]) * f))
                y = int(round(p1[1] + (p2[1] - p1[1]) * f))
                cv2.circle(out, (x, y), t, col, -1, lineType=cv2.LINE_AA)
        return out
