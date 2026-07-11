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
- **Selectable.** The timeline is a dropdown; `History.goto(index)` jumps the head to any
  committed action (ends any open focus first). Undo/redo are just goto by ±1.
- **Image-level.** Undo reverts the actual **image**, not just the mask: the memento
  carries the workspace edit-chain `pixel_head`, so reverting a step that changed pixels
  (isolate, defringe, …) moves the pixels back too. Mask edits and pixel edits share ONE
  per-image timeline.
- **Moves are NOT tracked.** Position/scale (drag/resize) are *not* history — `place()`
  records nothing, and the memento excludes x/y/scale, so undo/goto never move an image.
- **Reset erases history.** `/api/reset` reverts the pixels to the original open
  (`Workspace.reset`) *and* wipes the mask + per-image timeline (`Board.reset_history`,
  re-seeding a single `open` from the clean state) — a reset leaves no stale mask or steps.

## The engine (`history.py`) is orthogonal

`Memento` (opaque state dict) → `Action{label,state}` on a timeline + optional `Focus`
(base + sub-step mementos). It **knows nothing about dots/pixels/placement** — it stores
and restores snapshots. New undoable state needs zero engine changes.

## Wiring (`board.py`)

- The per-image memento = `_snapshot(a)` = `{mask, locked, pixel_head}`. Position/scale,
  z-order and selection are **not** in per-image undo — moves aren't history we keep (above).
- **`pixel_head` binds the two chains.** `sync()` refreshes each asset's `pixel_head` from
  its `Workspace` HEAD; `_restore` writes the memento's `pixel_head` back into the asset and
  `_apply_pixel_head` moves the `Workspace` HEAD to match. So undo/redo/goto revert pixels
  *and* mask in one move, per image.
- **Pixel commits record a step.** After a transform's `commit_edit()`, the caller calls
  `Board.record_pixel_edit(name, label)` (MCP `commit`, MCP `isolate`, web `/api/isolate`) —
  it commits a memento at the new HEAD, or no-ops if HEAD didn't move. The board layer owns
  this; `workspace.py` stays orthogonal (never imports the board).
- **Seed history in `_ensure_layers`** (from the clean opening state) so the *first*
  action is reversible — do NOT lazily seed on first mutation (that captures the
  post-mutation state as the baseline and makes the first action un-undoable).
- Dots → `_step(a, "place dots")`; every other *mask* mutation → `_commit(a, label)` (which
  ends any open focus first). `place()` (move/resize) commits nothing.
