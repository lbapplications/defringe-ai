"""Deterministic raster tools, organised into orthogonal class sets — one idea per class.

    Io         RGBA read/write                                    (utils)
    Color      colour parsing shared by the drawing tools         (utils)
    Transform  matte extraction + pixel cleanup                   key_background, trim_alpha,
                                                                  crop, defringe, upscale,
                                                                  silhouette_mask, canny
    Shape      draw primitives + the anchor/box model             draw_shape, draw_line
    Annotate   seed dots burned into the pixels                   mark
    Geometry   dots -> outline -> matte (the seeded isolation)    convex_hull, hull_snap,
                                                                  fill_polygon_alpha

Each class is a stateless namespace of @staticmethods over RGBA (H,W,4) uint8 arrays. The
sets are independent: tool classes depend only on `utils`, never on each other (Geometry
doesn't even touch Color). Add a new tool to the ONE class whose idea it fits — see
`.claude/rules/tools.md`.
"""

from .utils import RGBA, Color, Io
from .annotate import Annotate
from .geometry import Geometry
from .shape import Shape
from .transform import Transform

__all__ = ["RGBA", "Io", "Color", "Transform", "Shape", "Annotate", "Geometry"]
