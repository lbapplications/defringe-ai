"""[shape · gated] Draw primitives onto the image — gated behind an edit session."""

from __future__ import annotations

from .. import imageops as ops
from ..workspace import Workspace
from . import core

shape = core.category("shape", gated=True)


@shape
def draw_shape(shape: str = "circle", x: int = -1, y: int = -1, width: int = -1, height: int = -1,
               color: str = "red", anchor: str = "center", fill: bool = False,
               thickness: int = 3, workspace: str = "") -> dict:
    """[shape · gated] Draw a registered primitive with one consistent spatial model.

      shape   : circle | ellipse | square | rectangle | triangle  (see list_shapes)
      x, y    : where the ANCHOR point sits, in pixels (top-left origin, x→right, y→down).
                Omit (leave -1) to use the image centre.
      width   : box width in px; omit -> half the short side.
      height  : box height in px; omit -> same as width (symmetric).
      anchor  : which part of the shape lands at (x,y): center (default), top_left,
                top, top_right, left, right, bottom_left, bottom, bottom_right.
      color   : 'red' | '#rrggbb[aa]' | 'r,g,b[,a]'.
      fill    : True = filled, False = outline (thickness px).

    Returns the workspace status plus `drew` (the resolved shape/anchor/center/bbox in
    pixels) and `clipped` — so you can see exactly what landed and adjust. Gated: call
    edit(...) first; cancel() to revert. Coordinate details in docs/coordinates.md."""
    ws = Workspace.resolve(workspace, core.HOME)
    if not ws.in_session():
        raise ValueError("'draw_shape' is gated: no active edit session. "
                         'Call edit("<what you want>") first; cancel()/commit() to end.')
    h, w = ws.current_array().shape[:2]
    g = ops.Shape.resolve_box(w, h, x=None if x < 0 else x, y=None if y < 0 else y,
                        width=None if width < 0 else width,
                        height=None if height < 0 else height, anchor=anchor)
    st = ws.apply("draw_shape", ops.Shape.draw_shape,
                  {"shape": shape, "box": g["box"], "color": color, "fill": fill, "thickness": thickness})
    return {**st, "drew": {"shape": shape, "anchor": anchor,
                           "center": list(g["center"]), "bbox": list(g["box"])},
            "clipped": g["clipped"]}


@shape
def draw_line(x1: int, y1: int, x2: int, y2: int, color: str = "red",
              thickness: int = 2, dotted: bool = False, workspace: str = "") -> dict:
    """[shape - gated] Draw a straight line from (x1,y1) to (x2,y2) - (x,y) top-left
    origin, x->right, y->down. dotted=True gives a see-through dotted guide (good for
    crosshairs). Default colour red. Gated: call edit(...) first; cancel()/commit() to end."""
    st = core.apply("draw_line", ops.Shape.draw_line, workspace,
                    x1=x1, y1=y1, x2=x2, y2=y2, color=color, thickness=thickness, dotted=dotted)
    return {**st, "line": {"from": [x1, y1], "to": [x2, y2], "dotted": dotted, "color": color}}
