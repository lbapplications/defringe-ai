# Rule: tools — what a tool is, and the standards it must meet

**Scope — read before** adding or editing an image tool. Related: [docstrings](docstrings.md),
[orthogonalization](orthogonalization.md), [coordinates](coordinates.md).

## A tool is not real until it's registered to the MCP layer

A bare function in `imageops/` is an *implementation*, not a tool. It only becomes a
**tool** when it's registered under a **taxonomy category** — defined in the matching
`tools/<category>.py` module and decorated with that module's category decorator (e.g.
`@transform`, from `core.category("transform", gated=True)`), ideally with a CLI subparser in
`server.py` too. The decorator registers the tool on the shared MCP server **and** records its
taxonomy membership, so the taxonomy is **derived from the modules** — there is no hand-kept
`TAXONOMY` dict. "Add a tool" always means: implement it **and** register it (in its category
module) **and** document it. An unregistered helper is not a tool — don't call it one, and
don't leave a headline capability reachable only from a web route.

## Tools are orthogonal class sets, one idea per class (`imageops/`)

| Class (`imageops/…`) | Idea | Methods | MCP tools |
|---|---|---|---|
| `Io` (`utils`) | RGBA read/write | `load`, `save` | — (substrate) |
| `Color` (`utils`) | colour parsing (shared) | `parse`, `parse_rgb`, `NAMED` | — (substrate) |
| `Transform` (`transform.py`) | matte extraction + pixel cleanup | `key_background`, `trim_alpha`, `crop`, `defringe`, `upscale`, `silhouette_mask`, `edge_detect` | same names (gated) |
| `Shape` (`shape.py`) | draw primitives + anchor/box model | `resolve_box`, `draw_shape`, `draw_line` | `draw_shape`, `draw_line` (gated) |
| `Annotate` (`annotate.py`) | seed dots burned into pixels | `mark` | `mark` (gated) |
| `Geometry` (`geometry.py`) | dots → outline → matte (seeded isolation) | `convex_hull`, `hull_snap`, `simplify_contour`, `fill_polygon_alpha` | `seed`, `connect`, `isolate`, `clear_seeds` |

Each method is a **stateless `@staticmethod`** on RGBA `(H,W,4)` uint8 (Geometry also
takes/returns point lists). Tool classes import `utils` **only**, never each other.

## The four standards every tool meets

1. **NumPy is the substrate.** Pixel/point math is **vectorised NumPy** — no native-Python
   per-pixel or per-point loops (Python is slow). cv2 rasterising calls are fine; the math
   around them is arrays. A `for` loop over pixels/points is a smell — vectorise it.
2. **Google-style docstrings** with `Args`/`Returns`/`Raises` on the forward-facing method,
   updated whenever the function changes — see [docstrings](docstrings.md).
3. **Pydantic returns.** A state-mutating MCP tool returns a Pydantic model from
   `schemas.py` (e.g. `MaskState`, `IsolateResult`), not a bare dict — declared, validated,
   self-documenting. New tools follow this; old dict returns migrate opportunistically.
4. **Keep README in sync.** Every tool add/rename/removal updates the tool section of
   **README.md** in the *same change*. CLAUDE.md requires it; a tool the README doesn't
   list is undocumented to users.

## Adding a tool — the checklist

1. Pick the ONE class its idea fits; a genuinely new idea is a **taxonomy shift** (new
   class + new `tools/<category>.py` module) — surface it, see [orthogonalization](orthogonalization.md).
2. Implement it as a vectorised `@staticmethod` (input first, returns a fresh array/value).
3. Add the tool to its **category module** (`tools/<category>.py`), decorated with that
   module's category decorator (+ a CLI subparser in `server.py`, and re-export it from the
   `server.py` facade). The taxonomy updates itself — no dict to edit.
4. Return a Pydantic model if it mutates state.
5. Write the Google-style docstring.
6. Update the README tool section.

## The gate (taxonomy of *behaviour*)

The taxonomy — one module per category under `tools/` — groups the MCP tools: **session /
transform / shape / annotate / isolate / arrange / workspace / merge** (the `workspace` category is
`tools/manage.py`, named to avoid clashing with the engine's `workspace.py`). **transform +
shape + annotate MUTATE PIXELS and are GATED** (`gated=True` on the category) — they refuse
unless an edit session is open (`core.apply` enforces it):

```
edit("<intent>")  →  [gated tools]  →  cancel() (restore)  |  commit() (keep)
```

`isolate` is compound and **self-contained** (opens/commits its own edit), so it's a
separate category, not part of the gate. `arrange`/`workspace`/`merge` run freely. `merge`
is the commit side (C10) — the only tools that write the user's *real* file as a deliberate
act (the live projection during editing is automatic, in `core.advance`); its irreversible
writes are quarantined in `projection.py`.
