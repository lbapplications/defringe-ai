# DESIGN: Workflow (concrete schema + layout)

**Governed by:** [`specs/workflow.md`](../specs/workflow.md) (the contract — decisions + rationale).
This doc is the **concrete** shape: identifiers, on-disk layout, JSON schemas, and the
navigation/merge semantics. If this and the contract disagree, the contract wins.

---

## Identifiers
- `project_id = uuid5(root_path)` — full, no truncation. Doubles as the on-disk folder name.
- `asset_id   = uuid5(relative_asset_path)` — same.
- `session_id = uuid4` — opaque, random; the only token the agent carries.
- `state`  ids: `state_<n>` (folder). `mask` ids: `mask_<n>.png` (file).

The `uuid5(path)` is a deterministic name-based UUID (idempotent: same path → same id;
collision-free in practice). The path is stored inside every record so a lookup **verifies** it.

## Format constraint
**png only.** If a `.jpg` (or any non-png) asset is handed in, the tool **rejects it and says why**
— we do not silently transcode. png is required so (a) working states never recompress and (b)
masks/alpha are lossless. See "Projection".

---

## On-disk layout (single root: `workspace/`)
```
workspace/
  projects.json                     # lean registry (path ↔ ids ↔ assets)
  session/
    sessions.json                   # every session, ever (ledger)
    working_session.json            # the currently-active sessions
  <project_id>/
    <asset_id>/
      history.json                  # edit-management state (+ backup ledger)
      asset.png                     # the LOCKED base — untouched until merge
      state_0/ … state_n/           # each holds: state_<n>.png + mask_0.png, mask_1.png, …
      backup/                       # archived pre-merge bases: asset_0.png, asset_1.png, …
```

---

## `projects.json` — the registry (lean; a session-bridge, nothing high-churn)
```jsonc
projects.json = { "<project_id>": project, ... }

project = {
  "id":   "<project_id>",              // = uuid5(path); also the folder name
  "path": "path/to/project1/",         // absolute root; the ground-truth identity
  "assets": { "<asset_id>": asset, ... }
}

asset = { "path": "relative/path/asset1.png" }   // relative to the project root
```
No history, no backups, no session refs live here — those are per-asset (history.json) or in
`session/`. Keeps this file cheap to load whole.

---

## `history.json` — per-asset edit state (one per `<asset_id>/`)
```jsonc
history = {
  "locked_state": "asset.png",         // the locked base; untouched until merge
  "state_changes": [ state_0, state_1, ... ],   // linear; index = the undo cursor
  "assets_backup": [ { "id": "asset_0.png" }, { "id": "asset_1.png" }, ... ]  // commit-level, persists across merge
}

state = {
  "id": "state_<n>",                   // folder under the asset dir; holds state_<n>.png (never edited in place)
  "mask_history": mask_history          // the masks built while this state was current
}

mask_history = {                        // (renamed from the sketch's overloaded `mask_state`)
  "id": "state_<n>",                    // the state that owns these masks
  "masks": [ mask_0, mask_1, ... ]
}

mask = { "id": "mask_<n>.png" }         // png — a lossy mask fringes its own edges
```
- `state_changes` is **linear**. `assets_backup` is the coarse, cross-merge history (the bytes live
  in `backup/`; this list is the ledger).
- Masks nest **inside** the state that owns them — that's what makes undo coherent (below).

---

## `session/` — sessions (no DB yet; two JSON files)
```jsonc
working_session.json = { "<session_id>": session, ... }

session = {
  "id":         "<session_id>",
  "project_id": "<project_id>",        // REQUIRED
  "asset_id":   "<asset_id>",          // REQUIRED — a session is scoped to a single asset
  "state_id":   "state_<n>",           // the cursor (may not exist yet)
  "mask_id":    "mask_<n>.png"         // the cursor within the mask axis (may not exist yet)
}
```
- A **session is scoped to a single asset.** An agent editing several assets holds several sessions;
  the file path in the request makes which-asset unambiguous.
- **Bare minimum:** `project_id` + `asset_id`. `state_id` / `mask_id` are the live cursor and may be
  absent before the first edit.
- The **server/agent owns the session** and updates it on **every change** (advances the cursor).
- `sessions.json` is the full ledger; `working_session.json` is the active set.
- **Stale/orphaned sessions are possible** (an agent walks away). A cleanup pass over stale sessions
  is **deferred** — noted, not built.

---

## Navigation & undo (linear, coherent, collapsing)
The cursor (`state_id` + `mask_id` in the session) walks `state_changes`:
- **back** → step back one (pop masks within the current state first; a back on a mask-empty state
  steps to the previous state).
- **forward** → step forward one.
- **new edit after stepping back** → **collapse**: everything after the cursor is discarded, then the
  new state is appended. (Linear history with redo-truncation, not a tree.)

Undo is a **single joint cursor**, never per-axis: because pixel ops *consume* the mask, the mask
that cut a state's pixels is stored *with* that state, so you can never land on a (pixels, mask)
pair that never existed together.

---

## Edit model — projection (model A) + safety
- The **current state is projected onto the user's real file, in place, live** as each change is made.
  The filename **never changes** — only the bytes. (Stable path → whatever the user has the file open
  in just updates.)
- **png-only** makes this clean: alpha (a cutout) fits, and there's no format/extension juggling.
- Safety, not withholding: a **`.bk` sidecar** beside the user's file (written **only if absent**),
  plus `asset.png` staying **locked** in the workspace until merge, plus `assets_backup` across merges.

## Merge — approval, per asset
- `merge` **ships the chosen state** (the pixel state the cursor is parked on). The agent **asks the
  user "is this good?"** first — approval *is* the commit.
- On approval: the chosen state is written to the user's file (same name) and becomes the new
  `asset.png` base; the previous base is archived into `backup/` and appended to `assets_backup`;
  the fine `state_changes` collapse (session's asset work is done). The **mask never ships** — only
  the flattened state does.
- Cross-merge, the user can still move **backward/forward between approved commits** via `assets_backup`.
