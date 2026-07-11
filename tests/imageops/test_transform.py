"""Transform — matte extraction + cleanup + edge detection. Assert on array properties
(shape, dtype, alpha counts, specific pixels), not golden images."""

from __future__ import annotations

import numpy as np
import pytest

from defringe_ai.imageops import Transform


def test_key_background_white(rgba):
    out = Transform.key_background(rgba, bg="white")
    assert out.shape == rgba.shape and out.dtype == np.uint8
    # the dark square stays opaque; the white ground goes transparent
    assert out[10, 10, 3] == 255
    assert out[0, 0, 3] == 0


def test_key_background_black():
    a = np.zeros((8, 8, 4), np.uint8)
    a[..., 3] = 255
    a[3:5, 3:5, :3] = 255      # bright patch on black
    out = Transform.key_background(a, bg="black")
    assert out[3, 3, 3] == 255
    assert out[0, 0, 3] == 0


def test_key_background_color_spec():
    a = np.zeros((6, 6, 4), np.uint8)
    a[..., :3] = (10, 20, 30)   # flat colour ground
    a[..., 3] = 255
    a[2:4, 2:4, :3] = (200, 200, 200)
    out = Transform.key_background(a, bg="10,20,30")
    assert out[0, 0, 3] == 0          # matches ground → transparent
    assert out[2, 2, 3] == 255        # far from ground → opaque


def test_trim_alpha_crops_to_content(rgba):
    keyed = Transform.key_background(rgba, bg="white")
    trimmed = Transform.trim_alpha(keyed)
    # content is the 8x8 dark square at 6..14
    assert trimmed.shape[:2] == (8, 8)


def test_trim_alpha_fully_transparent_returns_input():
    a = np.zeros((5, 5, 4), np.uint8)
    out = Transform.trim_alpha(a)
    assert out is a


def test_crop_clamped_and_outside(rgba):
    sub = Transform.crop(rgba, 6, 6, 8, 8)
    assert sub.shape[:2] == (8, 8)
    # rect entirely outside → empty
    empty = Transform.crop(rgba, 100, 100, 10, 10)
    assert empty.size == 0


def test_defringe_erodes_alpha(rgba):
    keyed = Transform.key_background(rgba, bg="white")
    before = int((keyed[..., 3] > 0).sum())
    out = Transform.defringe(keyed, erode_px=1)
    after = int((out[..., 3] > 0).sum())
    assert after < before          # eroded inward
    assert out.dtype == np.uint8


def test_upscale_with_and_without_sharpen(rgba):
    big = Transform.upscale(rgba, factor=2.0, sharpen=0.6)
    assert big.shape[:2] == (40, 40)
    plain = Transform.upscale(rgba, factor=1.5, sharpen=0.0)
    assert plain.shape[:2] == (30, 30)


def test_silhouette_mask(rgba):
    keyed = Transform.key_background(rgba, bg="white")
    sil = Transform.silhouette_mask(keyed)
    assert (sil[..., :3] == 255).all()            # RGB forced white
    np.testing.assert_array_equal(sil[..., 3], keyed[..., 3])   # alpha preserved


def test_edge_detect_fires_on_the_square(rgba):
    edges = Transform.edge_detect(rgba, lo=50, hi=150)
    assert edges.shape == rgba.shape
    assert (edges[..., 3] == 255).all()           # opaque black canvas
    # some edge pixels fired (white), around the square border
    assert (edges[..., 0] == 255).any()


def test_close_gaps_bridges_a_broken_edge(rgba):
    # two thick white blocks with a 2px gap between them → closing seals the gap shut
    m = np.zeros_like(rgba)
    m[..., 3] = 255
    m[5:15, 3:10, :3] = 255          # left block
    m[5:15, 12:18, :3] = 255         # right block
    assert m[10, 10, 0] == 0 and m[10, 11, 0] == 0        # 2px gap is dark before
    closed = Transform.close_gaps(m, radius=2)
    assert closed.shape == rgba.shape
    assert (closed[..., 3] == 255).all()
    assert closed[10, 10, 0] == 255 and closed[10, 11, 0] == 255   # gap bridged shut
    # closing preserves bulk: pixels far from any mark stay black
    assert closed[0, 0, 0] == 0


def test_close_gaps_leaves_isolated_speck(rgba):
    # closing connects; it does NOT remove a lone speck (that's opening) — documented behaviour
    m = np.zeros_like(rgba)
    m[..., 3] = 255
    m[5, 5, :3] = 255                # a single isolated white pixel
    closed = Transform.close_gaps(m, radius=1)
    assert closed[5, 5, 0] == 255    # still there


def _subject_scene(seed=1):
    """80x80: noisy blue background with a distinct red subject block at [30:50, 30:50]."""
    rng = np.random.default_rng(seed)
    a = np.zeros((80, 80, 4), np.uint8)
    a[..., 3] = 255
    a[..., 2] = rng.integers(180, 220, (80, 80))            # blue ground
    a[30:50, 30:50, 0] = rng.integers(180, 220, (20, 20))   # red subject
    a[30:50, 30:50, 2] = rng.integers(0, 40, (20, 20))
    return a


def test_segment_confines_to_rect_and_finds_subject():
    a = _subject_scene()
    out = Transform.segment(a, [26, 26, 28, 28], iterations=3)
    assert out[0, 0, 3] == 0                    # outside the seed rect → definite background
    assert out[40, 40, 3] == 255                # the subject block is segmented as foreground
    assert (out[..., :3] == a[..., :3]).all()   # RGB preserved, only alpha set


def test_segment_keep_zero_skips_component_filter():
    a = _subject_scene()
    out = Transform.segment(a, [26, 26, 28, 28], iterations=3, keep=0)
    assert (out[..., 3] > 0).any()              # still segments; just no keep-largest pass


def test_segment_clamps_out_of_bounds_rect():
    a = _subject_scene()
    out = Transform.segment(a, [-10, -10, 999, 999], iterations=1)   # clamped to the frame
    assert out.shape == a.shape


def test_keep_largest_drops_noise():
    m = np.zeros((40, 40, 4), np.uint8)
    m[10:30, 10:30, :] = 255         # big subject (alpha + rgb)
    m[2, 2, :] = 255                 # a speck
    m[36, 36, :] = 255               # another speck
    out = Transform.keep_largest(m, keep=1)
    assert out[20, 20, 3] == 255     # subject kept
    assert out[2, 2, 3] == 0 and out[36, 36, 3] == 0    # specks cleared to transparent
    assert out[20, 20, 0] == 255     # RGB untouched


def test_keep_largest_min_area_retains_above_threshold():
    m = np.zeros((40, 40, 4), np.uint8)
    m[10:30, 10:30, 3] = 255         # big (400 px)
    m[2:5, 2:5, 3] = 255             # medium (9 px)
    m[36, 36, 3] = 255               # tiny (1 px)
    out = Transform.keep_largest(m, keep=1, min_area=5)
    assert out[20, 20, 3] == 255 and out[3, 3, 3] == 255   # big + the ≥5px medium survive
    assert out[36, 36, 3] == 0                              # the 1px speck is dropped


def _components(m):
    import cv2
    return cv2.connectedComponents((m[..., 0] > 0).astype(np.uint8), connectivity=8)[0] - 1


def test_bridge_gaps_links_nearest_fragments():
    # two separated blobs → nearest-neighbour linking fuses them into ONE component
    m = np.zeros((40, 40, 4), np.uint8)
    m[..., 3] = 255
    m[6:10, 5:9, :3] = 255            # blob A
    m[6:10, 16:20, :3] = 255         # blob B (≈8px gap)
    assert _components(m) == 2
    br = Transform.bridge_gaps(m, max_link=20)
    assert _components(br) == 1       # a 1px bridge now joins A—B
    assert (br[..., 3] == 255).all()


def test_bridge_gaps_leaves_far_speck_orphaned():
    # a speck beyond max_link from everything gets no bridge → stays its own component
    m = np.zeros((60, 60, 4), np.uint8)
    m[..., 3] = 255
    m[6:10, 5:9, :3] = 255            # blob A
    m[6:10, 14:18, :3] = 255         # blob B (near A)
    m[55, 55, :3] = 255              # a lone speck, >30px from A/B
    assert _components(m) == 3
    br = Transform.bridge_gaps(m, max_link=15)
    assert _components(br) == 2       # A—B joined; the far speck remains isolated


def test_bridge_gaps_single_fragment_is_noop():
    m = np.zeros((20, 20, 4), np.uint8)
    m[..., 3] = 255
    m[5:9, 5:9, :3] = 255            # one blob → nothing to link
    br = Transform.bridge_gaps(m)
    assert _components(br) == 1
    assert np.array_equal(br[..., 0], m[..., 0])


def test_matrix_sweep_keys_black_out_and_glows(rgba):
    edges = Transform.edge_detect(rgba, lo=50, hi=150)
    ov = Transform.matrix_sweep(edges, color="#35ff7d", bold=1, glow=2.0)
    assert ov.shape == rgba.shape
    # black background -> fully transparent; the edge core -> fully opaque
    assert ov[..., 3].min() == 0
    assert ov[..., 3].max() == 255
    # surviving pixels carry the vivid colour (green dominates R and B)
    lit = ov[..., 3] > 200
    assert lit.any()
    g = ov[lit]
    assert (g[:, 1] > g[:, 0]).all() and (g[:, 1] > g[:, 2]).all()


def test_matrix_sweep_no_glow_no_bold_is_crisp(rgba):
    edges = Transform.edge_detect(rgba, lo=50, hi=150)
    ov = Transform.matrix_sweep(edges, bold=0, glow=0.0)
    # with no halo, alpha is strictly binary: on the edge or fully transparent
    assert set(np.unique(ov[..., 3])).issubset({0, 255})


def test_matrix_sweep_negative_inverts_the_base(rgba):
    edges = Transform.edge_detect(rgba, lo=50, hi=150)
    ov = Transform.matrix_sweep(edges, mode="negative", base=rgba, bold=0, glow=0.0)
    lit = ov[..., 3] > 0
    assert lit.any()
    # every lit pixel is the photographic negative of the base at that spot
    exp = 255 - rgba[..., :3].astype(int)
    assert (ov[..., :3].astype(int)[lit] == exp[lit]).all()


def test_matrix_sweep_white_mode(rgba):
    edges = Transform.edge_detect(rgba, lo=50, hi=150)
    ov = Transform.matrix_sweep(edges, mode="white", bold=0, glow=0.0)
    lit = ov[..., 3] > 0
    assert (ov[..., :3][lit] == 255).all()
