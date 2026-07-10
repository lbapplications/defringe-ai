# Rule: tools — the class-set taxonomy + the gate

**Scope — read before** adding or editing an image tool.

## Tools are orthogonal class sets, one idea per class (`imageops/`)

| Class (`imageops/…`) | Idea | Methods |
|---|---|---|
| `Io` (`_core`) | RGBA read/write | `load`, `save` |
| `Color` (`_core`) | colour parsing (shared) | `parse`, `parse_rgb`, `NAMED` |
| `Transform` (`transform.py`) | matte extraction + pixel cleanup | `key_background`, `trim_alpha`, `crop`, `defringe`, `upscale`, `silhouette_mask`, `canny` |
| `Shape` (`shape.py`) | draw primitives + anchor/box model | `resolve_box`, `draw_shape`, `draw_line`, `NAMES`, `ANCHORS` |
| `Annotate` (`annotate.py`) | seed dots burned into pixels | `mark` |
| `Geometry` (`geometry.py`) | dots → outline → matte (seeded isolation) | `convex_hull`, `hull_snap`, `fill_polygon_alpha` |

Every method is a **stateless `@staticmethod`**, `RGBA (H,W,4) uint8 → RGBA` (Geometry
also takes/returns point lists). **cv2 does the drawing/geometry; NumPy holds the pixels.**

## Adding a tool

1. **Pick the ONE class its idea fits.** If it's a genuinely new idea, add a new class in
   its own file — don't bolt it onto an unrelated set. Tool classes may import `_core`
   only, never another tool class.
2. Write it as a `@staticmethod` taking `img: RGBA` first, returning a new array (copy —
   don't mutate the input).
3. Expose it in `server.py`: an `@mcp.tool()` wrapper **and** a CLI subparser, then add
   its name to the matching `TAXONOMY` category.

## The gate (taxonomy of *behaviour*, in `server.py`)

`TAXONOMY` groups the MCP tools: **session / transform / shape / annotate / arrange /
workspace**. **transform + shape + annotate MUTATE PIXELS and are GATED** — they refuse
unless an edit session is open. The flow:

```
edit("<intent>")  →  [gated tools]  →  cancel() (restore)  |  commit() (keep)
```

`_apply(op, fn, workspace, **params)` enforces the gate. A new pixel tool goes through it;
a read-only/arrange tool does not. See [coordinates](coordinates.md) for the (x,y) model.
