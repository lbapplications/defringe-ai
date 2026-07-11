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
