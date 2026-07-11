"""Annotate — burned-in dots, with out-of-frame points skipped."""

from __future__ import annotations

import numpy as np

from defringe_ai.imageops import Annotate


def test_mark_in_frame_dot(rgba):
    out = Annotate.mark(rgba, [[10, 10]], radius=2, color="red")
    red = (out[..., 0] == 255) & (out[..., 1] == 0) & (out[..., 2] == 0)
    assert red.any()
    assert out.shape == rgba.shape


def test_mark_skips_out_of_frame(rgba):
    # both points outside the 20x20 frame → nothing drawn, image unchanged
    out = Annotate.mark(rgba, [[-5, -5], [100, 100]], radius=3, color="red")
    np.testing.assert_array_equal(out, rgba)


def test_mark_empty_points(rgba):
    out = Annotate.mark(rgba, [], radius=3)
    np.testing.assert_array_equal(out, rgba)
