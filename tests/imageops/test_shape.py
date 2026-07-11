"""Shape — the anchor/box model + primitive rasterising + lines."""

from __future__ import annotations

import numpy as np
import pytest

from defringe_ai.imageops import Shape


def test_resolve_box_defaults_center():
    g = Shape.resolve_box(100, 80)
    # width defaults to half the short side (80//2=40), height mirrors width, centred
    assert g["box"] == (30, 20, 70, 60)
    assert g["center"] == (50, 40)
    assert g["clipped"] is False


def test_resolve_box_explicit_anchor_and_clip():
    g = Shape.resolve_box(50, 50, x=0, y=0, width=20, height=10, anchor="top_left")
    assert g["box"] == (0, 0, 20, 10)
    clip = Shape.resolve_box(50, 50, x=45, y=45, width=20, height=20, anchor="top_left")
    assert clip["clipped"] is True


def test_resolve_box_unknown_anchor_raises():
    with pytest.raises(ValueError):
        Shape.resolve_box(10, 10, anchor="nowhere")


@pytest.mark.parametrize("shape", ["circle", "ellipse", "square", "rectangle", "triangle"])
@pytest.mark.parametrize("fill", [True, False])
def test_draw_each_shape(rgba, shape, fill):
    box = Shape.resolve_box(20, 20, x=10, y=10, width=10, height=10)["box"]
    out = Shape.draw_shape(rgba, shape=shape, box=box, color="red", fill=fill, thickness=2)
    assert out.shape == rgba.shape
    # red was drawn somewhere
    red = (out[..., 0] == 255) & (out[..., 1] == 0) & (out[..., 2] == 0)
    assert red.any()


def test_draw_shape_unknown_raises(rgba):
    with pytest.raises(ValueError):
        Shape.draw_shape(rgba, shape="hexagon", box=(0, 0, 5, 5))


def test_draw_line_solid_and_dotted(rgba):
    solid = Shape.draw_line(rgba, 0, 0, 19, 19, color="blue", thickness=2)
    assert solid.shape == rgba.shape
    dotted = Shape.draw_line(rgba, 0, 0, 19, 0, color="green", thickness=2, dotted=True)
    assert dotted.shape == rgba.shape
    dotted_gap = Shape.draw_line(rgba, 0, 5, 19, 5, color="green", dotted=True, gap=4)
    assert dotted_gap.shape == rgba.shape
