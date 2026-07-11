# Rule: frontend — the edit screen is a Vite/React/Konva app, kept orthogonal

**Scope — read before** touching anything under `frontend/`, or the `app.py` routes that
serve/feed it. The frontend mirrors the backend's discipline: **one concern per module,
no sideways reach, the server is the single source of truth.** Related:
[architecture](architecture.md), [coordinates](coordinates.md), [server-ops](server-ops.md).

## Stack (and why)

Vite + React + **react-konva**. The board is a Konva `<Stage>`; drag, resize, and the
transform handles come from Konva's `<Transformer>` — **never hand-roll mouse math for
drag/resize** (that was the old `canvas.js` sin this rewrite deleted). Source lives in
`frontend/`; `pnpm build` emits into `src/defringe_ai/web/dist/`, which `app.py` serves.

## The taxonomy (orthogonal modules, `frontend/src/`)

| Module | Idea | Owns |
|---|---|---|
| `state.ts` | the **data plane** | the `Asset` type (mirrors `build_state`), `useBoard()` SSE hook, `post()`, coordinate helpers (`baseW`, `dispScale`). The ONLY place that does server I/O. |
| `Canvas.tsx` + `AssetNode.tsx` | the **view** | the Konva stage, z-ordered asset nodes, image + mask (dots/outline), drag/resize via `<Transformer>`, dot placement. |
| `Toolbox.tsx` | the **controls** | tool selection, view toggles, mask/history action buttons. Reads the asset list, POSTs intents. Holds no board state. |
| `App.tsx` + `styles.css` | the **shell** | composition + client-only UI state (active tool, view toggles) + global layout/the grid. |

## The invariants (mirror the backend's orthogonalization)

1. **One concern per module.** A genuinely new concern is a **taxonomy shift** — add a
   module *and* update this table, don't bolt it onto the nearest file. Surface it (see
   [orthogonalization](orthogonalization.md)).
2. **All server I/O goes through `state.ts`** (`post`, `useBoard`). No ad-hoc `fetch` in a
   component. `Canvas` and `Toolbox` never import each other; shared UI state lifts to `App`.
3. **The server is the source of truth.** Components render pushed SSE state and POST
   *intents*; they do **not** keep a parallel copy of board state. The `POST` result comes
   back over the stream and reconciles the view.
4. **The `Asset` type is the contract** with the Python `build_state` dict — they live in
   one place each and change **together** (a field added server-side is added to `Asset`).
5. **Coordinates match the backend:** the server speaks image-space `(x, y)`, top-left
   origin (see [coordinates](coordinates.md)); multiply by `dispScale` for on-board pixels.

## Build / run — see [server-ops](server-ops.md)

Dev: run the Python server, then `pnpm dev` in `frontend/` (proxies `/api`, `/img`, SSE →
:47824, instant HMR). Prod: `pnpm build` → `web/dist/`, served by `app.py`; an unbuilt
checkout still boots (index shows a "run pnpm build" hint). `node_modules/` and `dist/`
are git-ignored — the bundle is regenerated, not committed.
