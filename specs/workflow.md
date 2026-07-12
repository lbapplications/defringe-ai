# SPEC: Workflow  *(contract)*

**Status:** derived. One item deferred (session-lifecycle cleanup, see Deferred). Concrete schema
+ on-disk layout live in [`design/workflow.md`](../design/workflow.md).

**Governs:** the loop a user or agent moves through to edit an image in this repo — and how that
loop *feels* across two surfaces:

1. **In the window** — the live edit screen (Konva board, click-through history, tool buttons).
2. **Headless** — a separate agent session driving the MCP with **no UI**: perceiving state, acting,
   and re-tuning purely through tool returns and looking at returned images.

The load-bearing question: *can the same MCP feel usable both ways* — is the tool surface a complete
instrument on its own, or does it lean on the window? This contract says it stands alone.

---

## Contract
<!-- Each clause: the rule + why. Collapsed from the D1–D19 derivation; traceability in brackets. -->

### C1 — Two workflows, one MCP; the headless loop is the product.
`open → look` on the Konva board is the *author's* local debug loop, not what the MCP is designed
around. The governing loop is **headless**: an external agent points the MCP at an asset and works
it. The window is scaffolding. [D1]

### C2 — State is addressed, not ambient.
There is no implicit "current image." Every tool resolves the asset it was pointed at and refuses if
it has no key for it. What the window gives you for free (peripheral vision) becomes explicit
headless: the agent names what it's editing, the server confirms it. [D2]

### C3 — Identity = `(project root path, relative asset path)`; the id is a full `uuid5`.
Project = a root directory; asset = a path relative to it. Uniqueness comes from the real filesystem
path. The on-disk/index id is `uuid5(path)` — **full, never truncated** — playing a dual role (folder
name *and* registry key); the path is stored inside every record so a lookup **verifies** it. A
truncated id was rejected: a key collision would silently route you into the *wrong workspace*.
[D3, D5, D6, Q4]

### C4 — File responsibilities are split and single-homed.
`projects.json` is a **lean registry / session-bridge** (path ↔ ids ↔ assets) — cheap to load whole,
nothing high-churn. Per-asset **`history.json`** owns all edit state **and the backup ledger**.
Sessions live under **`session/`**. No datum has two homes. [D4, D19, Q10]

### C5 — The agent carries only an opaque `session_id`; a session is scoped to one asset.
The server owns all id↔path resolution and hands back a `session_id`; the agent never juggles hashes
or paths. A **session is scoped to a single asset** (minimum: `project_id` + `asset_id`; `state_id`/
`mask_id` are the live cursor and may not exist yet). An agent editing several assets holds several
sessions. The server updates the session on **every change**. Session-id security is out of scope.
[D7, D8, D9, Q5]

### C6 — The MCP is a virtual mount table.
No OS mount: `projects.json` is a mount table, a session is a handle to a mounted `(project, asset)`,
and assets resolve **by relative path**. First call either **resumes** an existing asset (load its
history, continue from the cursor) or **lazily mounts** a new one (register it, create its workspace
dir, lock a copy of the original). [D10, D12]

### C7 — Edit model A: live in-place projection.
The current state is **projected onto the user's real file, in place, live** — the **filename never
changes, only the bytes**, so any viewer they have open just updates. Safety comes from backups, not
from withholding the write: a **`.bk` sidecar** (written only if absent), the base image **locked
until merge**, and the cross-merge `backup/`. [D11]

### C8 — png only.
A non-png asset (e.g. `.jpg`) is **rejected with a reason** — no silent transcoding. png keeps working
states lossless, keeps alpha/masks exact, and makes in-place projection format-clean. Masks are png
too — a lossy mask fringes the very edges it defines. [D14]

### C9 — Per-asset history: linear states, nested masks, one coherent cursor.
`history.json.state_changes` is a **linear** list of lossless-png pixel **states**; the masks built
during a state nest **inside** it. Undo is a **single joint cursor** (never per-axis): back pops
masks within a state, then steps states; forward steps one; **a new edit after stepping back collapses
everything after the cursor**. Joint-not-per-axis because pixel ops *consume* the mask — an
independent mask-undo would desync the selection from the pixels it already cut. [D13, D15, D16]

### C10 — `merge` is a per-asset approval.
`merge` **ships the chosen state** (where the cursor sits). The agent **asks "is this good?"** first;
approval *is* the commit. On approval: the chosen state is written to the user's file (same name) and
becomes the new locked base; **the approved state itself is archived into the `backup/` ledger as this
commit** (so every approved state is retained — the pristine pre-everything original stays in `.bk`,
not the commit ledger); the fine `state_changes` collapse. **The mask never ships — only the flattened
state does.** Across merges the user can still step **backward/forward between approved commits** via
the backup ledger — and because each commit is an *approved* state (not the base it replaced), stepping
back never destroys the state you're leaving. [D17, D18, Q9]

---

## Deferred
- **Session-lifecycle cleanup.** Orphaned/stale sessions are possible (an agent walks away). A cleanup
  pass, and whether "store the session" means resume across a **server restart**, are deferred — noted,
  not built. [was Q6]

## Closed during collapse
- Asset key = **relative path** (not bare filename — two dirs can share a name); `uuid5(relative_path)`.
  [was Q3]

---

*Derivation history (the D1–D19 / Q1–Q10 Socratic trail) is preserved in git; this contract is the
current normative statement.*
