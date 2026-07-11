"""Geometry — dots → hull → snapped outline → alpha matte."""

from __future__ import annotations

import numpy as np

from defringe_ai.imageops import Geometry


def test_convex_hull_of_square_with_interior_point():
    # 4 corners + 1 interior; hull is the 4 corners (interior dropped)
    hull = Geometry.convex_hull([[0, 0], [10, 0], [10, 10], [0, 10], [5, 5]])
    assert len(hull) == 4
    for corner in ([0, 0], [10, 0], [10, 10], [0, 10]):
        assert corner in hull


def test_convex_hull_too_few_points_returned_asis():
    assert Geometry.convex_hull([[1, 1], [2, 2]]) == [[1, 1], [2, 2]]


def test_hull_snap_pulls_interior_dot_onto_boundary():
    pts = [[0, 0], [10, 0], [10, 10], [0, 10], [5, 5]]
    outline = Geometry.hull_snap(pts)
    # every dot (including the concave 5,5) ends up on the outline
    assert [5, 5] in outline
    assert len(outline) == 5


def test_hull_snap_dig_ratio_stops_early():
    pts = [[0, 0], [10, 0], [10, 10], [0, 10], [5, 5]]
    outline = Geometry.hull_snap(pts, dig_ratio=0.1)
    # a tight dig_ratio keeps it near-convex → the interior dot is NOT inserted
    assert [5, 5] not in outline


def test_hull_snap_too_few_points():
    assert Geometry.hull_snap([[1, 1]]) == [[1, 1]]


def test_fill_polygon_alpha_cuts_out(rgba):
    poly = [[5, 5], [15, 5], [15, 15], [5, 15]]
    out = Geometry.fill_polygon_alpha(rgba, poly)
    assert out[10, 10, 3] == 255      # inside → opaque
    assert out[0, 0, 3] == 0          # outside → transparent


def test_fill_polygon_alpha_degenerate_is_transparent(rgba):
    out = Geometry.fill_polygon_alpha(rgba, [[1, 1], [2, 2]])
    assert (out[..., 3] == 0).all()
