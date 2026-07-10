# Rule: architecture — layers, kept orthogonal

**Scope — read before** navigating the code or adding a feature, to place it in the right
layer. Each layer owns one concern and doesn't reach across.

```
server.py     MCP tools + CLI + transport — THIN over the domain layers
   │
web/          the edit screen: app.py (routes, SSE, state) + canvas.{html,css,js}
   │          static files served from the main checkout; state = board + workspace heads
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
- **`history.py` is idea-agnostic** — it stores opaque state snapshots; the board decides
  *what* a snapshot is. Don't leak dot/pixel specifics into it.
- **`server.py` stays thin** — it wires MCP/CLI to domain calls; logic lives below it.
- **State is on disk** (`workspace/` PNGs + `manifest.json`, `board.json`) so a human
  (CLI) and the agent (MCP) drive the same asset. Don't add in-memory-only state.
- Deep-dives live in their own rules: [tools](tools.md), [undo](undo.md),
  [coordinates](coordinates.md), [server-ops](server-ops.md).
