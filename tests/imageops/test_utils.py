"""Io round-trip + Color parsing."""

from __future__ import annotations

import numpy as np
import pytest

from defringe_ai.imageops import Color, Io


def test_io_roundtrip(tmp_path, rgba):
    p = str(tmp_path / "x.png")
    w, h = Io.save(rgba, p)
    assert (w, h) == (20, 20)
    back = Io.load(p)
    assert back.shape == (20, 20, 4)
    assert back.dtype == np.uint8
    np.testing.assert_array_equal(back, rgba)


def test_io_load_forces_rgba(tmp_path):
    from PIL import Image

    p = str(tmp_path / "rgb.png")
    Image.new("RGB", (4, 3), (10, 20, 30)).save(p)
    img = Io.load(p)
    assert img.shape == (3, 4, 4)
    assert (img[..., 3] == 255).all()


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("red", (255, 0, 0, 255)),
        ("#00ff00", (0, 255, 0, 255)),
        ("#01020304", (1, 2, 3, 4)),
        ("10,20,30", (10, 20, 30, 255)),
        ("10,20,30,40", (10, 20, 30, 40)),
        ((5, 6, 7), (5, 6, 7, 255)),
        ([5, 6, 7, 8], (5, 6, 7, 8)),
    ],
)
def test_color_parse(spec, expected):
    assert Color.parse(spec) == expected


def test_color_parse_unknown_name_raises():
    with pytest.raises(ValueError):
        Color.parse("chartreuse-ish")


def test_color_parse_rgb_hex_and_csv():
    np.testing.assert_array_equal(Color.parse_rgb("#0a141e"), np.array([10, 20, 30], np.uint8))
    np.testing.assert_array_equal(Color.parse_rgb("1,2,3"), np.array([1, 2, 3], np.uint8))
