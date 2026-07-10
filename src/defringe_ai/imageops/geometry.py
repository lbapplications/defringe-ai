"""`Geometry` — dots -> outline -> matte: the deterministic isolation math.

The seeded-isolation path (repo tool #1). Rough seed dots become a concave boundary via
convex-hull-then-snap-inward, and the boundary fills into alpha as a cutout. Pure point/
polygon math + one `fillPoly`; no colour, no I/O — depends only on `_core.RGBA`.
"""

from __future__ import annotations

import cv2
import numpy as np

from ._core import RGBA


def _dedupe(points) -> list[tuple[int, int]]:
    out, seen = [], set()
    for p in points:
        q = (int(p[0]), int(p[1]))
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def _seg_dist(p, a, b) -> float:
    """Distance from point p to segment a->b (all (x, y))."""
    p, a, b = (np.asarray(v, np.float64) for v in (p, a, b))
    ab = b - a
    denom = float(ab @ ab)
    t = 0.0 if denom == 0 else float(np.clip((p - a) @ ab / denom, 0.0, 1.0))
    return float(np.hypot(*(p - (a + t * ab))))


class Geometry:
    """Turn seed points into a boundary polygon, then into an alpha matte."""

    @staticmethod
    def convex_hull(points) -> list[list[int]]:
        """Outermost enclosing polygon of a point set — the deterministic convex hull.

        Returns the hull vertices in cyclic (boundary) order, a subset of the input.
        Interior points are dropped (that's what 'convex' means)."""
        pts = _dedupe(points)
        if len(pts) < 3:
            return [list(p) for p in pts]
        hull = cv2.convexHull(np.array(pts, np.int32).reshape(-1, 1, 2), returnPoints=True)
        return [[int(p[0][0]), int(p[0][1])] for p in hull]

    @staticmethod
    def hull_snap(points, dig_ratio: float = 0.0) -> list[list[int]]:
        """Convex hull, then SNAP INWARD to recover concavities — deterministically.

        1. Convex hull = the outer boundary (ignores every concave/interior dot).
        2. Repeatedly take the not-yet-used dot closest to any current boundary edge and
           insert it into that edge, carving the outline inward toward it. Ties break by
           (distance, edge index, point index) so the result is a pure function of the input.

        `dig_ratio`: stop digging an edge once the nearest inside point is farther than
        `dig_ratio * edge_length` (keeps it near-convex). Default 0.0 = dig until every dot
        lies on the outline (the full hand-traced silhouette)."""
        pts = _dedupe(points)
        if len(pts) < 3:
            return [list(p) for p in pts]
        boundary = [tuple(v) for v in Geometry.convex_hull(pts)]
        used = set(boundary)
        remaining = [p for p in pts if p not in used]
        while remaining:
            best = None                                    # (dist, edge_i, point_i)
            for ei in range(len(boundary)):
                a, b = boundary[ei], boundary[(ei + 1) % len(boundary)]
                for pi, p in enumerate(remaining):
                    key = (_seg_dist(p, a, b), ei, pi)
                    if best is None or key < best:
                        best = key
            d, ei, pi = best
            if dig_ratio > 0:
                a, b = boundary[ei], boundary[(ei + 1) % len(boundary)]
                if d > dig_ratio * float(np.hypot(b[0] - a[0], b[1] - a[1])):
                    break
            boundary.insert(ei + 1, remaining.pop(pi))
        return [list(p) for p in boundary]

    @staticmethod
    def fill_polygon_alpha(img: RGBA, polygon) -> RGBA:
        """Cut out the subject: keep RGB, set alpha=255 inside the polygon and 0 outside.
        The deterministic isolation payoff — feed it hull_snap's outline to get a matte."""
        H, W = img.shape[:2]
        out = img.copy()
        mask = np.zeros((H, W), np.uint8)
        pts = np.array([[int(x), int(y)] for x, y in polygon], np.int32)
        if len(pts) >= 3:
            cv2.fillPoly(mask, [pts], 255, lineType=cv2.LINE_AA)
        out[..., 3] = mask
        return out
