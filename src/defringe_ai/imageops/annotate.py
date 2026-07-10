"""``Annotate`` — non-structural marks burned into the pixels, for flagging locations.

Distinct from ``Shape`` (geometric primitives) and from the board's invisible mask dots
(non-destructive annotation that rides with the image). ``mark`` here is destructive: it
writes dots straight into the RGBA so a snapshot shows where the agent was looking.
"""

from __future__ import annotations

import cv2
import numpy as np

from .utils import RGBA, Color


class Annotate:
    """Burn debug/seed dots into the image. ``RGBA -> RGBA``."""

    @staticmethod
    def mark(img: RGBA, points, radius=4, color="black") -> RGBA:
        """Drop a filled dot at each point, for flagging seed/eyeball locations.

        Args:
            img: Source RGBA image.
            points: An iterable of ``[x, y]`` points (top-left origin). Points outside the
                frame are skipped.
            radius: Dot radius in pixels.
            color: Any spec :meth:`Color.parse` accepts.

        Returns:
            A new RGBA array with the dots burned in.
        """
        h, w = img.shape[:2]
        col = Color.parse(color)
        out = img.copy()
        pts = np.asarray(points, dtype=np.int64).reshape(-1, 2)
        in_frame = (pts[:, 0] >= 0) & (pts[:, 0] < w) & (pts[:, 1] >= 0) & (pts[:, 1] < h)
        for x, y in pts[in_frame]:
            cv2.circle(out, (int(x), int(y)), int(radius), col, -1, lineType=cv2.LINE_AA)
        return out
