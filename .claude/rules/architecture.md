# Rule: architecture — layers, kept orthogonal

**Scope — read before** navigating the code or adding a feature, to place it in the right
layer. Each layer owns one concern and doesn't reach across.

```
server.py     MCP tools + CLI + transport — THIN over the domain layers
   │
web/app.py    the edit screen's SERVER: routes, SSE state stream, serves the built UI
   │          from web/dist; state = board + workspace heads. THIN (see frontend below).
   │
frontend/     the edit screen's UI: a Vite + React + Konva app (see frontend.md).
   │          Built by `pnpm build` into web/dist; talks to app.py over /api + SSE only.
   │
   ├── board.py      the ARRANGEMENT: per-asset x/y/scale, z-order (ordered list,
   │                 Konva-style — not a growing counter), selection, the invisible
   │                 MASK layer (dots/outline/lock), and per-image undo (via history.py)
   ├── workspace.py  ONE asset's PIXEL edit history (open/apply/undo/collapse/export) +
   │                 the edit SESSION gate (begin_edit/cancel_edit/commit_edit + backup)
   ├── history.py    the per-image undo ENGINE — generic, knows nothing about pixels/dots
   └── imageops/     the TOOLS as orthogonal class sets (see tools.md)
```

**Orthogonality rules that must hold:**

- **Tool classes depend only on `imageops/_core`**, never on each other.
- **The frontend is orthogonal to the backend** — `frontend/` talks to `app.py` only
  through `/api` + `/img` + the SSE stream; the server holds no view logic and the UI holds
  no board state. It has its own taxonomy + rule ([frontend.md](frontend.md)).
- **`history.py` is idea-agnostic** — it stores opaque state snapshots; the board decides
  *what* a snapshot is. Don't leak dot/pixel specifics into it.
- **`server.py` stays thin** — it wires MCP/CLI to domain calls; logic lives below it.
- **State is on disk** (`workspace/` PNGs + `manifest.json`, `board.json`) so a human
  (CLI) and the agent (MCP) drive the same asset. Don't add in-memory-only state.
- Deep-dives live in their own rules: [tools](tools.md), [undo](undo.md),
  [coordinates](coordinates.md), [server-ops](server-ops.md), [frontend](frontend.md).
