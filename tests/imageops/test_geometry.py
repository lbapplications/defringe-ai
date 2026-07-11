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


def _matte(shape=(40, 40)):
    """A transparent RGBA with an opaque rectangle punched into the alpha."""
    a = np.zeros((*shape, 4), np.uint8)
    a[8:32, 6:34, :3] = 200
    a[8:32, 6:34, 3] = 255
    return a


def test_label_shapes_ranks_components_by_area():
    m = np.zeros((40, 40, 4), np.uint8)
    m[2:6, 2:6, 3] = 255              # small blob: 16 px at (2,2)
    m[10:30, 10:34, 3] = 255         # big blob: 20*24=480 px at (10,10)
    rows = Geometry.label_shapes(m)
    assert len(rows) == 2
    assert rows[0][0] == 480 and rows[1][0] == 16      # largest first
    area, x, y, w, h, cx, cy = rows[0]
    assert (x, y, w, h) == (10, 10, 24, 20)            # bbox of the big blob
    assert 20 <= cx <= 22 and 19 <= cy <= 21           # its centroid


def test_label_shapes_empty_foreground():
    assert Geometry.label_shapes(np.zeros((10, 10, 4), np.uint8)) == []


def test_find_contours_is_the_dense_boundary_walk():
    dense = Geometry.find_contours(_matte())
    # a 24x28 rectangle perimeter is ~100 boundary pixels — far more than 4 corners
    assert len(dense) > 40
    xs = [p[0] for p in dense]
    ys = [p[1] for p in dense]
    assert min(xs) <= 7 and max(xs) >= 32       # the walk hugs the opaque region's edge
    assert min(ys) <= 9 and max(ys) >= 30


def test_simplify_thins_the_found_contour():
    # find_contours is the raw stage; simplify is the same boundary, thinned by Douglas–Peucker
    m = _matte()
    dense = Geometry.find_contours(m)
    sparse = Geometry.simplify_contour(m, epsilon=2.0)
    assert len(sparse) == 4 and len(sparse) < len(dense)   # rectangle → 4 corners, far fewer
    # every kept vertex is an actual vertex of the dense walk (a subset, not invented points)
    dense_set = {tuple(p) for p in dense}
    assert all(tuple(p) in dense_set for p in sparse)


def test_find_contours_empty_when_fully_transparent():
    assert Geometry.find_contours(np.zeros((10, 10, 4), np.uint8)) == []


def test_simplify_contour_of_rectangle_is_four_corners():
    poly = Geometry.simplify_contour(_matte(), epsilon=2.0)
    assert len(poly) == 4                       # a rectangle simplifies to its 4 corners
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    assert min(xs) <= 7 and max(xs) >= 32       # bbox tracks the opaque region (~6..33)
    assert min(ys) <= 9 and max(ys) >= 30


def test_simplify_contour_epsilon_controls_vertex_count():
    # an L-shaped matte: a coarse epsilon drops the concave step
    a = np.zeros((40, 40, 4), np.uint8)
    a[6:34, 6:20, 3] = 255                      # vertical bar
    a[20:34, 6:34, 3] = 255                     # foot → an L with one concave corner
    fine = Geometry.simplify_contour(a, epsilon=1.0)
    coarse = Geometry.simplify_contour(a, epsilon=6.0)
    assert len(fine) >= 6                        # the L keeps its concave notch
    assert 3 <= len(coarse) < len(fine)          # a coarser tolerance drops the notch


def test_simplify_contour_empty_when_fully_transparent():
    assert Geometry.simplify_contour(np.zeros((10, 10, 4), np.uint8)) == []


def test_fill_polygon_alpha_cuts_out(rgba):
    poly = [[5, 5], [15, 5], [15, 15], [5, 15]]
    out = Geometry.fill_polygon_alpha(rgba, poly)
    assert out[10, 10, 3] == 255      # inside → opaque
    assert out[0, 0, 3] == 0          # outside → transparent


def test_fill_polygon_alpha_degenerate_is_transparent(rgba):
    out = Geometry.fill_polygon_alpha(rgba, [[1, 1], [2, 2]])
    assert (out[..., 3] == 0).all()
