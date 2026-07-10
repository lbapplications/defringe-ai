"""``Geometry`` — dots -> outline -> matte: the deterministic seeded-isolation math.

Rough seed dots become a concave boundary (convex hull, then snap inward), and the
boundary fills into alpha as a cutout. All point/edge math is **vectorised NumPy** — the
snap computes every point-to-edge distance as one broadcast, no per-point Python loop.
Depends only on ``utils`` (not even ``Color``).
"""

from __future__ import annotations

import cv2
import numpy as np

from .utils import RGBA


def _dedupe(points) -> np.ndarray:
    """Drop duplicate points, preserving first-seen order. Returns an ``(N, 2)`` int array."""
    arr = np.asarray(points, dtype=np.int64).reshape(-1, 2)
    if len(arr) == 0:
        return arr
    _, idx = np.unique(arr, axis=0, return_index=True)
    return arr[np.sort(idx)]


def _seg_dist_matrix(pts: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance from every point to every segment, vectorised.

    Args:
        pts: ``(P, 2)`` query points.
        a: ``(E, 2)`` segment start points.
        b: ``(E, 2)`` segment end points (paired with ``a``).

    Returns:
        An ``(E, P)`` array where ``[e, p]`` is the distance from point ``p`` to segment
        ``e``. Edge-major so a flattened ``argmin`` breaks ties by (edge, point).
    """
    ab = b - a                                   # (E, 2)
    ab2 = (ab * ab).sum(1)                        # (E,)
    ap = pts[None, :, :] - a[:, None, :]          # (E, P, 2)
    t = (ap * ab[:, None, :]).sum(2) / np.where(ab2[:, None] == 0, 1.0, ab2[:, None])
    t = np.clip(t, 0.0, 1.0)                       # (E, P)
    proj = a[:, None, :] + t[:, :, None] * ab[:, None, :]   # (E, P, 2)
    return np.linalg.norm(pts[None, :, :] - proj, axis=2)   # (E, P)


class Geometry:
    """Turn seed points into a boundary polygon, then into an alpha matte."""

    @staticmethod
    def convex_hull(points) -> list[list[int]]:
        """Compute the outermost enclosing polygon of a point set (the convex hull).

        Args:
            points: An iterable of ``[x, y]`` points (image-pixel space).

        Returns:
            The hull vertices in cyclic boundary order — a subset of the deduplicated
            input, with interior points dropped. Fewer than 3 unique points are returned
            as-is.
        """
        pts = _dedupe(points)
        if len(pts) < 3:
            return pts.tolist()
        hull = cv2.convexHull(pts.astype(np.int32).reshape(-1, 1, 2), returnPoints=True)
        return [[int(p[0][0]), int(p[0][1])] for p in hull]

    @staticmethod
    def hull_snap(points, dig_ratio: float = 0.0) -> list[list[int]]:
        """Trace a boundary through seed dots: convex hull, then snap inward.

        Starts from the convex hull (which ignores concave dots), then repeatedly inserts
        the not-yet-used dot closest to any current boundary edge into that edge, carving
        the outline inward until it passes through every dot. Deterministic: ties break by
        (distance, edge index, point index), so the same dots always give the same polygon.

        Args:
            points: Seed dots as ``[x, y]`` pairs (rough is fine — the boundary snaps to
                whatever the caller placed).
            dig_ratio: Stop digging an edge once its nearest inside point is farther than
                ``dig_ratio * edge_length`` (keeps the result near-convex). Default ``0.0``
                digs until every dot lies on the outline.

        Returns:
            The boundary polygon as an ordered list of ``[x, y]`` vertices. Fewer than 3
            unique points are returned as-is.
        """
        pts = _dedupe(points)
        if len(pts) < 3:
            return pts.tolist()
        boundary = [tuple(int(v) for v in p) for p in Geometry.convex_hull(pts)]
        used = {p for p in boundary}
        remaining = np.array([p for p in pts.tolist() if tuple(p) not in used], dtype=np.int64)

        while len(remaining):
            b = np.array(boundary, dtype=np.int64)              # (E, 2)
            nxt = np.roll(b, -1, axis=0)                        # edge i: b[i] -> nxt[i]
            d = _seg_dist_matrix(remaining, b, nxt)             # (E, P)
            flat = int(np.argmin(d))                            # first min in (edge, point) order
            ei, pi = divmod(flat, len(remaining))
            if dig_ratio > 0:
                edge_len = float(np.hypot(*(nxt[ei] - b[ei])))
                if d[ei, pi] > dig_ratio * edge_len:
                    break
            boundary.insert(ei + 1, tuple(int(v) for v in remaining[pi]))
            remaining = np.delete(remaining, pi, axis=0)
        return [list(p) for p in boundary]

    @staticmethod
    def fill_polygon_alpha(img: RGBA, polygon) -> RGBA:
        """Cut out the subject by filling a boundary polygon into the alpha channel.

        Args:
            img: The source ``(H, W, 4)`` RGBA image (RGB is preserved).
            polygon: The boundary as ``[x, y]`` vertices, e.g. from :meth:`hull_snap`.

        Returns:
            A new RGBA array with alpha = 255 inside the polygon and 0 outside. If the
            polygon has fewer than 3 vertices the result is fully transparent.
        """
        H, W = img.shape[:2]
        out = img.copy()
        mask = np.zeros((H, W), np.uint8)
        pts = np.array([[int(x), int(y)] for x, y in polygon], np.int32)
        if len(pts) >= 3:
            cv2.fillPoly(mask, [pts], 255, lineType=cv2.LINE_AA)
        out[..., 3] = mask
        return out
