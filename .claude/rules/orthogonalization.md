# Rule: orthogonalization — one idea per unit, shared concepts go to utils

**Scope — read before** adding a class/module, moving code between areas, or when a
function in one area starts needing a concept from another.

## The standard

1. **One idea per class / module.** A tool class is a set of methods that share a single
   idea (matte cleanup, drawing, geometry). If a new function doesn't fit an existing
   idea, it's a **taxonomy shift** (below), not a bolt-on to the nearest class.
2. **No sideways dependencies.** A tool class imports **`imageops/utils`** and standard
   libs — **never another tool class**. If `Shape` needs something `Transform` has, that
   something doesn't belong to `Transform`; it belongs to `utils`.
3. **Shared concept → `utils`.** The moment a helper is needed in a *second* area, move it
   to `imageops/utils.py` (the shared home) and import it in both. Don't copy-paste it, and
   don't let one area reach into another to borrow it. Single-area helpers stay local
   (module-private) until that second caller appears — don't pre-hoist.
4. **NumPy is the substrate.** Pixel/point math is vectorised NumPy, not native-Python
   loops (see the NumPy standard in [tools](tools.md)). Shared numeric helpers live in
   `utils` once shared.

## Taxonomy shifts — surface them, don't smuggle them

A **taxonomy shift** is any change to the *set of ideas*: a new tool class, a new
`TAXONOMY` category in `server.py`, a new Pydantic result model, or promoting a helper to
`utils`. When you make one:

- **Call it out** in your summary and the commit message ("taxonomy shift: added the
  `isolate` category / `Geometry` class / `utils` promotion").
- Keep the reflections in sync in the **same change**: the code class, the `server.py`
  `TAXONOMY` dict, the README tool section, and the relevant rule file. A shift that
  updates one but not the others is half-done.

Orthogonality is the invariant; a taxonomy shift is the *only* sanctioned way to widen it,
and it must be explicit.
