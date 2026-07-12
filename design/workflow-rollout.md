# DESIGN: Workflow rollout (build phases)

**Rolls out:** [`design/workflow.md`](workflow.md) (the concrete schema) under the contract in
[`specs/workflow.md`](../specs/workflow.md). This doc is the **build order** — how the design lands
in code as three dependency-strict, independently-testable phases. If this and the contract disagree,
the contract wins.

---

## Where the design already lives in code
The load-bearing engine is **built and tested** (≈168 tests, ~97% cov) — this rollout is a shell
around it, not a rewrite:
- **C9 reversible states + joint coherent undo** — `workspace.py` (append-only PNG chain + HEAD),
  `board.py`'s `History` stores a single joint memento (`pixel_head` + `overlay_head` + `mask`).
- **C7/C10 primitives** — `begin_edit`/`commit_edit`/`cancel_edit`, `collapse()`, `export()`.
- **Testability** — the web surface runs under a Starlette `TestClient` over a tmp `home`;
  `Workspace`/`Board` are plain filesystem objects.

The chain is strict: **1 → 2 → 3**, each green before the next.

---

## Phase 1 — Identity & addressing *(the foundation)* — ✅ DONE
**In:** C3 identity — `uuid5` project/asset ids in `identity.py`; a `projects.json` mount table in
`registry.py` (path-stored-for-verify, resume-on-reopen, `adopt_legacy`); storage rekeyed to
`home/<project_id>/<asset_id>/`; `board.py` + `web/app.py` resolve assets through the registry.
**C8 png-gate** at intake (signature bytes, not extension).

**Refinement vs. the original sketch:** the **window keeps addressing by its `name` label** (resolved
to the id-dir through the registry) rather than exposing `asset_id` to the frontend. The window is
scaffolding (C1) and becomes *session*-addressed in Phase 2 anyway, so the `state.ts` token change was
deferred there — this kept the live window working with zero frontend risk. `name` is now a **deduped,
registry-backed label**, not a raw directory name.

**Why first:** everything keys on identity; nothing can be addressed until this lands.

**Test gate — met:** `uuid5` idempotency + normalization; tamper-detection on `resolve`; png rejected
by signature; resume-on-reopen; `adopt_legacy`. Full suite green (`make check`: 200 py @ ~97.6%, 8 vitest).
New: `tests/test_identity.py`, `tests/test_registry.py`.

---

## Phase 2 — Sessions, mount & canvas-as-harness *(unify the two surfaces)* — ✅ DONE
**In:** C5/C6 session layer — opaque `session_id`, `sessions.json`/`working_session.json`, lazy-mount
+ resume, server owns the cursor; swapped all ~31 MCP tools from `workspace:str` → `session_id`; **routed
the canvas through the same mount/session layer.**

**Why second:** sessions sit on identity; the canvas can only share the path once the path exists.
Landing the canvas here is deliberate — from this point the existing `TestClient` `/api/*` tests
exercise the headless contract *for free*, and the live `--watch` window becomes a watchable
integration test for Phase 3.

**Decision (made 2026-07-11): fully session-addressed.** The window carries no ambient "current
asset" — every action names its `session_id` end-to-end, same as the MCP tools. This costs a bigger
`state.ts`/frontend rekey than ambient-sugar-over-sessions, but buys one resolution path with no
implicit-current corner cases (the Phase-1 rename→board-migration fix was a symptom of label-keyed
ambient state; sessions retire it rather than paper over it). The `name` label survives only as a
human-readable display field, never as the addressing key.

**As built (2026-07-11):**
- `src/defringe_ai/sessions.py` — the `Sessions` store: `session/working_session.json` (active set) +
  `sessions.json` (ledger); `open` mints/**resumes** one handle per asset (keyed on identity, not the
  mutable label, so it survives a rename); `name_of` resolves live through the registry; `advance` is
  the server-owned cursor (`state_<head>` + `mask_<overlay_head>.png`). Every open/resume/advance
  **logs** `[session] …` so a live `--watch` run *shows* the layer working.
- `tools/core.py` — session-addressed resolution (`open_session`, `name`, `workspace`, `advance`,
  gated `apply`); no ambient fallback — a blank/unknown session is a guided error.
- All tool modules swapped `workspace:str` → `session:str`; `open_asset` returns `session`;
  `list_workspaces` returns the label→session map (no more `active`).
- `web/app.py` — the canvas mounts through `_session_for`/`_name_for`; `/api/*` + `/img/{session}/{i}`
  + `/mask/{session}` all address by session; `build_state` emits `session` per asset.
- Frontend — `state.ts` `Asset` gains `session`; every component POSTs `session` and fetches images by
  it; `name` is display-only.
- **The CLI stays name-addressed** — deliberately: it's the local human debug loop (C1 scaffolding),
  not one of the two addressed surfaces this decision names. It drives the engine directly (which keeps
  its `.active` convenience pointer); the MCP tools + window simply never consult it.

**Test gate — met:** `make check` green (219 py @ 97.3%, hard_lint 5/5, 8 vitest, frontend build clean).
New `tests/test_sessions.py` (open/resume, rename-follows, resolve, cursor advance); `test_server.py`
+ `test_app.py` thread sessions and prove *both* surfaces run one resolution path.

**Follow-up landed (2026-07-11): window cursor-advance coherence (C5).** The window's edit routes
(derive/isolate/undo/redo/goto/reset in `web/app.py`) resolved the session but never advanced its
cursor — only the MCP tools did — so an agent sharing a session saw a stale `state_id`/`mask_id`
after a human undo/derive. Fixed by lifting the `(session, workspace) → cursor` derivation out of
`tools.core.advance` into `Sessions.advance_to(session, ws)` — the **one** place both addressed
surfaces derive the cursor — and calling it after each window mutation. `web` reaches the session
layer directly (never the FastMCP `tools.core`). Regression: `test_window_edit_advances_session_cursor`.

**Parked to Phase 3 / deferred:** resume-*after-server-restart* (the ledger persists, but re-attaching a
walked-away agent's session is part of C6 lifecycle cleanup — noted, not built); the cursor's
`state_id`/`mask_id` currently mirror the live workspace HEADs rather than the on-disk nested
`state_<n>/mask_<n>.png` storage, which Phase 3 reshapes.

---

## Phase 3 — Projection, merge & backup *(the commit side, isolated)* — ✅ DONE (2026-07-11)
**In:** C7 live in-place projection onto the user's real file + `.bk` sidecar (write-if-absent) +
locked base; C10 merge = "is this good?" approval + `backup/` ledger.

**Why last:** the only irreversible side effects in the whole system (writing the user's actual file)
— quarantine them behind a fully-addressed, fully-tested state model, with the Phase-2 window letting
you *watch* each projection land.

**As built (2026-07-11):**
- **New `src/defringe_ai/projection.py`** (taxonomy shift — a new top-level module) — the ONE place
  that writes *outside* the workspace `home`. `Projection(home, project_id, asset_id)` resolves the
  real path via `Registry.real_path` and owns three files: the **real file** (byte-faithful mirror of
  HEAD), the **`.bk` sidecar** (pristine original, write-if-absent), and the **`backup/` dir** (archived
  approved bases — the directory listing *is* the commit ledger, no side JSON to desync). `project(ws)`
  is a no-op when the real file is gone/legacy-dir-keyed or already holds HEAD (so a **mask-only change
  writes nothing** — the mask never leaks onto the real file, C10). `merge(ws)` archives the current
  base → ships HEAD → `collapse()`. `restore(ws, index)` returns a prior approved commit.
- **Projection rides the existing choke points**, no new call sites: `tools.core.advance` (MCP) and the
  `web/app.py` `advance()` closure (window) each already fire once per state change (C5 cursor) — both
  now also project (C7). Best-effort: a stale session / missing file can't fail an edit (backups are the
  safety net, not withholding the write). Every projection/merge logs a `[project]` line for `--watch`.
- **New `merge` taxonomy category** (`tools/merge.py`): `merge(session)` (approval commit) +
  `revert_merge(commit, session)` (cross-merge navigation), Pydantic `MergeResult`. CLI `merge` /
  `revert_merge` (name-addressed, like the rest of the CLI). README + nomenclature ledger (`projection`
  / `merge` / `commit`) + architecture layer + `tools.md` updated in the same change.
- **Engine seams added** (small, single-homed): `Registry.real_path` (the one path pointing outside
  `home`), `Workspace.base_path()` (what merge archives), `Workspace.reseed_base(src)` (restore a commit).

**Parked (non-gating):** C9 on-disk mask-*nesting* (`state_<n>/mask_<n>.png`) — a storage reshape; the
joint-undo *behavior* it guarantees already ships from the existing engine. Resume-after-server-restart
(C6 lifecycle). And a **module-layout refactor** the growing cross-imports now warrant — see the status memo.

**Test gate — met:** `make check-deterministic` green (234 py @ 97.4%, hard_lint 5/5, 8 vitest).
New `tests/test_projection.py` (project/`.bk`/skip/merge/ledger/restore); `test_registry.py` (`real_path`),
`test_workspace.py` (`base_path`/`reseed_base`), `test_server.py` (merge/revert tools + CLI), `test_app.py`
(a window edit projects onto the real file). Every test mounts a tmp asset — no real path is touched.
