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

## Phase 2 — Sessions, mount & canvas-as-harness *(unify the two surfaces)*
**In:** C5/C6 session layer — opaque `session_id`, `sessions.json`/`working_session.json`, lazy-mount
+ resume, server owns the cursor; swap the ~15 MCP tools from `workspace:str` → `session_id`; **route
the canvas through the same mount/session layer.**

**Why second:** sessions sit on identity; the canvas can only share the path once the path exists.
Landing the canvas here is deliberate — from this point the existing `TestClient` `/api/*` tests
exercise the headless contract *for free*, and the live `--watch` window becomes a watchable
integration test for Phase 3.

**Decision this phase forces:** window keeps ambient-selection *sugar over sessions* (leaning) vs.
fully addressed state (no implicit current). Pick before building; capture the call into
[`specs/workflow.md`](../specs/workflow.md).

**Test gate:** session create/resume; resume-after-server-restart; the `/api/*` suite now proving
*both* surfaces run one resolution path.

---

## Phase 3 — Projection, merge & backup *(the commit side, isolated)*
**In:** C7 live in-place projection onto the user's real file + `.bk` sidecar (write-if-absent) +
locked base; C10 merge = "is this good?" approval + `backup/` ledger (`assets_backup`).

**Parked (non-gating):** C9 on-disk mask-*nesting* (`state_<n>/mask_<n>.png`). The *behavior* it
guarantees (joint undo) already ships from the existing engine; this is a storage reshape, safe to do
as a follow-up.

**Why last:** the only irreversible side effects in the whole system (writing the user's actual file)
— quarantine them behind a fully-addressed, fully-tested state model, with the Phase-2 window letting
you *watch* each projection land.

**Test gate:** fake client-file in tmp; `.bk` write-if-absent; projection-after-every-op; merge
archives old base + restores from the ledger. Tests never touch a real path.
