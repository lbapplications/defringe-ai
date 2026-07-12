# nomenclature — the one word for each thing (a top-down corpus)

This is the **canonical vocabulary** of the repo. Every tool name, taxonomy label, concept,
and doc uses these words for these ideas — one word per thing, decided here first, then
spent everywhere. When a name is in question, this file settles it; code and prose conform
to the file, not the other way round. Part of it is **machine-enforced** (see the bottom):
the [deterministic linter](../hard_lint/) parses the ledger below, so drift fails `make check`.

## The one rule: name for the outcome, not the implementation

A public name says **what the tool does for the user**, never **how it does it** or **which
library it borrows from**. The agent picks a tool by the effect it wants — it shouldn't need
to know the algorithm.

- `edge_detect`, **not** `canny`. Canny is *how* the edge map is computed (`cv2.Canny`); the
  outcome is "detect edges". The algorithm name stays where it belongs — in the docstring and
  the implementation — never on the public surface.
- The same logic pre-empts `grabcut`, `lanczos`, `otsu`, `cv2_*`, `np_*`: name the result
  (`isolate`, `upscale`, `threshold`, …), not the routine.

**Why:** the repo's thesis is a vision agent that *looks and re-tunes*. It reasons in
outcomes ("the subject isn't fully outlined"), so the tool surface must, too — an
implementation-named tool leaks a detail the agent shouldn't have to carry, and locks the
name to a library we might swap.

## Form

- **Tools & CLI subcommands:** `snake_case`, lowercase, `[a-z][a-z0-9_]*`. No camelCase, no
  hyphens, no library prefixes. A companion/adaptive variant appends a suffix on the same
  stem: `edge_detect` → `edge_detect_tune`.
- **Verbs for actions, nouns for state.** A tool that *does* a thing is a verb
  (`isolate`, `defringe`, `connect`); a tool that *reports* is a noun (`status`, `taxonomy`).
- **Result models:** `PascalCase` + `Result` (`EdgeDetectTuneResult`) — the tool's stem in
  PascalCase, so the model name tracks the tool name.
- **Internal algorithm methods** (`imageops`) may keep the algorithm's proper name in the
  docstring ("via the Canny algorithm") — but the *method* is still named for the outcome
  (`Transform.edge_detect`), so the public and internal vocabularies agree.

## The concept ledger (shared nouns — use these exact words)

| Word | Means (and don't call it…) |
|---|---|
| **workspace** | one asset's on-disk home + its edit chain. Not "project", "doc", "buffer". |
| **board** | the multi-asset canvas + the invisible mask layer. Not "scene", "stage". |
| **HEAD** | the current step pointer in the pixel edit chain. Not "cursor", "tip". |
| **edit chain** | the append-only list of PNG snapshots. Not "history stack" (that's the mask's). |
| **edit session** / **the gate** | the `edit → … → commit/cancel` transaction that gates pixel mutations. Not "transaction mode". |
| **mask** | the invisible per-image dots+outline layer that rides with the asset. Not "selection", "layer". |
| **seed** (v.) | drop rough boundary dots. **connect** = join them into an outline. Not "trace". |
| **outline** (v.) | trace the boundary straight from the pixels (simplify a matte's contour) — the *unseeded* `connect`. Fills the same `mask.outline` slot; then `isolate`. |
| **isolate** / **cutout** | fill the outline into alpha = the matte. Not "extract", "clip". |
| **signal** / **derive** | a read-only extraction (e.g. an edge map) applied in place. Not "filter". |
| **defringe** | erode + burn the matte rim. **fringe/matte rim** = the halo it removes. |
| **memento** | one entry in the mask's undo timeline; carries `pixel_head` **and** `overlay_head` to bind the pixel + overlay chains. |
| **overlay** / **layer chain** | a versioned mask-overlay raster (edge/hull/simplify) snapshotted per step; `overlay_head` points at the current version. Not "the mask" (that's the dots+outline), not a single file. |
| **projection** | mirroring the current HEAD onto the user's **real file**, in place, live (C7). Not "save", "sync", "write-back". |
| **merge** | shipping a chosen state as an **approved commit** to the real file (C10) — approval *is* the commit. Not "publish", "apply", "finalize". |
| **commit** (n.) | one approved merged state in the backup ledger (`backup/asset_<n>.png`), navigable across merges. Not "version", "revision" (those are edit-chain steps). |

Add a term here the moment a new concept earns a name — before it picks up three synonyms
across the code.

## Enforced ledger — banned public names

The linter reads the block below and **fails if any banned name is used as a tool or CLI
subcommand**, or if a tool name isn't `snake_case`. Each line is `` `banned` `` → the word to
use instead. Edit this list when a naming decision is made; the gate updates with it.

<!-- nomenclature:banned -->
- `canny` → `edge_detect` (name the outcome, not the algorithm)
- `grabcut` → name the outcome (`isolate` / `segment`), not the OpenCV routine
- `lanczos` → `upscale` (the resample kernel is an implementation detail)
- `otsu` → `threshold` (the method name is not the outcome)
- `cv2` → never a tool name (library leak)
- `opencv` → never a tool name (library leak)
- `numpy` → never a tool name (library leak)
<!-- /nomenclature:banned -->

## How it's enforced

`hard_lint/check.py` has a `nomenclature` check that parses the banned block above (the
`<!-- nomenclature:banned -->` markers) and the live `TAXONOMY` + CLI, then asserts:

1. every tool / subcommand name matches `[a-z][a-z0-9_]*` (snake_case), and
2. no banned name appears as a tool / subcommand name.

So this doc is the **source of truth**: decide a name here, and the deterministic lane of
`make check` holds the whole repo to it. See [tools](tools.md) for the rest of the
tool-authoring standard and [hard_lint](../hard_lint/) for the check lane.
