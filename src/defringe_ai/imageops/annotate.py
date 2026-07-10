"""`Annotate` — non-structural marks burned into the pixels, for flagging locations.

Distinct from `Shape` (geometric primitives) and from the board's invisible mask dots
(non-destructive annotation that rides with the image). `mark` here is destructive: it
writes dots straight into the RGBA so a snapshot shows where the agent was looking.
"""

from __future__ import annotations

import cv2

from ._core import RGBA, Color


class Annotate:
    """Burn debug/seed dots into the image. RGBA -> RGBA."""

    @staticmethod
    def mark(img: RGBA, points, radius=4, color="black") -> RGBA:
        """Drop a tiny filled dot at each [x, y] point (top-left origin, x->right, y->down).
        For flagging seed points / locations to eyeball. Points outside the frame are skipped."""
        h, w = img.shape[:2]
        col = Color.parse(color)
        out = img.copy()
        for p in points:
            x, y = int(p[0]), int(p[1])
            if 0 <= x < w and 0 <= y < h:
                cv2.circle(out, (x, y), int(radius), col, -1, lineType=cv2.LINE_AA)
        return out
