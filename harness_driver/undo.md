# Rule: undo — per-image, two-level, focus-aware

**Scope — read before** touching `history.py`, board mutations, or anything that changes
an asset's mask/placement.

## The model (what the user asked for)

- **Per-image timeline.** Each asset owns its own `History`; undo targets the selected
  image, not a global stack.
- **Two levels.** A committed `Action` is one step on the timeline. A `Focus` is an open
  **bundle** of sub-steps: placing dots opens a `place dots` focus, each dot is a
  sub-step. `History.undo()` is **focus-aware** — it pops a sub-step if a focus is open,
  else walks the committed timeline. Any *other* action collapses the bundle into ONE
  timeline action, so a later undo jumps past all the dots in one step.

## The engine (`history.py`) is orthogonal

`Memento` (opaque state dict) → `Action{label,state}` on a timeline + optional `Focus`
(base + sub-step mementos). It **knows nothing about dots/pixels/placement** — it stores
and restores snapshots. New undoable state needs zero engine changes.

## Wiring (`board.py`)

- The per-image memento = `_snapshot(a)` = `{mask, locked, x, y, scale}`. z-order and
  selection are **global**, deliberately **not** in per-image undo.
- **Seed history in `_ensure_layers`** (from the clean opening state) so the *first*
  action is reversible — do NOT lazily seed on first mutation (that captures the
  post-mutation state as the baseline and makes the first action un-undoable).
- Dots → `_step(a, "place dots")`; every other mutation → `_commit(a, label)` (which ends
  any open focus first).

**Not yet merged:** pixel-edit history still lives in `workspace.py` (its own chain).
Folding pixel ops into the same per-image `History` is the open next step.
