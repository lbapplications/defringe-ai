"""``Shape`` — draw registered primitives + straight lines onto the image.

All shapes share one spatial model: an ``(x, y)`` anchor point + a ``(width, height)``
bounding box + an ``anchor`` naming which part of the box lands at ``(x, y)``. Coords are
pixels, top-left origin, x->right, y->down (see ``harness_driver/coordinates.md``). cv2
does the rasterising; coordinate math is vectorised NumPy.
"""

from __future__ import annotations

import cv2
import numpy as np

from .utils import RGBA, Color


class Shape:
    """Draw primitives (fill or stroke) + guide lines. ``RGBA -> RGBA``."""

    NAMES = ("circle", "ellipse", "square", "rectangle", "triangle")

    # where in the box the anchor point sits: name -> (horizontal frac, vertical frac)
    ANCHORS = {
        "top_left": (0, 0), "top": (0.5, 0), "top_right": (1, 0),
        "left": (0, 0.5), "center": (0.5, 0.5), "right": (1, 0.5),
        "bottom_left": (0, 1), "bottom": (0.5, 1), "bottom_right": (1, 1),
    }

    @staticmethod
    def resolve_box(W, H, x=None, y=None, width=None, height=None, anchor="center") -> dict:
        """Resolve an (anchor point + size + anchor name) into a concrete pixel box.

        Args:
            W: Image width in pixels.
            H: Image height in pixels.
            x: Anchor point x (defaults to image centre).
            y: Anchor point y (defaults to image centre).
            width: Box width (defaults to half the short side).
            height: Box height (defaults to ``width``, i.e. symmetric).
            anchor: Which part of the box sits at ``(x, y)`` — one of :attr:`ANCHORS`.

        Returns:
            ``{"box": (x0, y0, x1, y1), "center": (cx, cy), "clipped": bool}`` where
            ``clipped`` is True if the box extends past the image bounds.

        Raises:
            ValueError: If ``anchor`` is not a registered anchor name.
        """
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
        """Draw one registered primitive inside a resolved pixel box.

        Args:
            img: Source RGBA image.
            shape: One of :attr:`NAMES`.
            box: The pixel box ``(x0, y0, x1, y1)`` to draw within (e.g. from
                :meth:`resolve_box`).
            color: Any spec :meth:`Color.parse` accepts.
            fill: Fill the shape if True, else stroke it.
            thickness: Stroke width in pixels (ignored when ``fill`` is True).

        Returns:
            A new RGBA array with the primitive drawn.

        Raises:
            ValueError: If ``shape`` is not a registered primitive.
        """
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
        """Draw a straight line, solid or dotted.

        Args:
            img: Source RGBA image.
            x1: Start x (top-left origin, x->right, y->down).
            y1: Start y.
            x2: End x.
            y2: End y.
            color: Any spec :meth:`Color.parse` accepts.
            thickness: Line/dot thickness in pixels.
            dotted: If True, step dots along the line (a see-through guide) instead of a
                solid stroke.
            gap: Dot spacing in pixels when ``dotted`` (defaults to ~3x ``thickness``).

        Returns:
            A new RGBA array with the line drawn.
        """
        out = img.copy()
        col = Color.parse(color)
        p1 = np.array([int(x1), int(y1)])
        p2 = np.array([int(x2), int(y2)])
        t = max(1, int(thickness))
        if not dotted:
            cv2.line(out, tuple(p1), tuple(p2), col, t, lineType=cv2.LINE_AA)
        else:
            dist = float(np.hypot(*(p2 - p1)))
            step = gap if gap > 0 else max(3, t * 3)
            n = max(1, int(round(dist)) // step)
            # vectorised dot centres along the segment; cv2 rasterises each
            pts = np.round(p1 + np.linspace(0.0, 1.0, n + 1)[:, None] * (p2 - p1)).astype(int)
            for x, y in pts:
                cv2.circle(out, (int(x), int(y)), t, col, -1, lineType=cv2.LINE_AA)
        return out
