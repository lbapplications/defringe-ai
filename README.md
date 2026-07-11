# defringe-ai

**An experiment in agent-driven image editing.**

Can a vision-capable agent edit images *effectively* when you hand it a set of
**deterministic raster transforms** — crop, key, mask, clean, composite — that it calls,
looks at, and re-tunes? This is a small [MCP](https://modelcontextprotocol.io) server
built to probe that question. Turning reference art, screenshots, and concept images into
game/UI-ready assets *without a human in an image editor* is one motivating use case — but
the goal is the general capability, not a product.

## Why this works

An AI can **see** an image but can't **generate** one. That asymmetry is a closed loop:

```
reference / screenshot ──▶ [deterministic transform tool] ──▶ result
        ▲                                                       │
        └──────────────  AI LOOKS, tunes params  ◀──────────────┘
```

The model doesn't paint. It **crops, keys, masks, cleans, and composites** with
parameters, then **looks at the output and adjusts** — exactly how a human uses
Photoshop's non-painting tools (magic wand, refine edge, levels).

## Stack

- **Python + NumPy** — images are `(H, W, 4)` uint8 RGBA arrays, so the pixel passes read
  as plain array math (the `MxNxRxGxB` model). Pillow for I/O, OpenCV for morphology.
- **[FastMCP](https://modelcontextprotocol.io)** — `stdio` for a local agent, streamable
  HTTP to run on a server.
- **Local, deterministic, no cloud.** Each tool edits the workspace and returns its
  status (HEAD, the edit chain, the current file) so the agent re-reads the result and
  self-corrects.

## The workspace (the "playground")

State lives on disk, not in the server's memory — so it survives an agent restart and
a **human and the agent can edit the same asset**. You point at an asset; it's copied
into a workspace; every edit is a full PNG snapshot in an append-only chain with a
`HEAD` pointer:

```
workspace/octopus/
  source/octopus.png       ← the original, copied in once, never mutated
  history/0000-open.png    ← every edit is a full, reversible snapshot
          0001-key_background.png
          0002-defringe.png   ← HEAD
  manifest.json            ← { steps:[…], head }
```

- **undo / redo** just move `HEAD` (snapshots are kept)
- editing after an undo **truncates the redo tail** and forks from `HEAD`
- **collapse** flattens the chain to the current image as the new base — *"verify, then
  collapse the edit chain to the verified asset"*
- **export** writes `HEAD` out as the finished deliverable

MCP tools (for the agent) and the CLI (for you) are thin front-ends over this — same
workspace on disk.

**Several assets at once.** Open multiple inputs and shape them in parallel — each is
its own named workspace with its own edit chain. Every tool takes an **optional
`workspace`**: name it to target a specific asset, or omit it to act on the one you
touched last. `list_workspaces` (CLI: `ls`) shows what's in flight.

## Run

```bash
uv sync

# --- human, from the shell ---
uv run defringe-ai open ./art/octopus.png   # copy an asset in, start editing
uv run defringe-ai status
uv run defringe-ai undo            # / redo
uv run defringe-ai collapse        # verify: flatten to the current image
uv run defringe-ai export out.png

# --- for an agent / MCP client ---
uv run defringe-ai serve                       # stdio
uv run defringe-ai serve --http --preview      # HTTP + browser edit screen
```

The **edit screen** (`--preview`) is a Vite + React + Konva app in `frontend/`. Build it
once so the server can serve it:

```bash
cd frontend && pnpm install && pnpm build      # → src/defringe_ai/web/dist (served at :47824)
pnpm dev                                        # or: live HMR on :47825, proxying to the server
```

## Dev — one command

`scripts/dev.sh` runs the whole stack with a **clean, graceful shutdown**: Ctrl-C stops
everything and frees the ports, so the next run always rebinds cleanly (no orphaned server
left behind). It streams the server log into the terminal.

```bash
./scripts/dev.sh           # build the frontend, run the server (serves web/dist) at :47824
./scripts/dev.sh --dev     # run the server + Vite dev server (HMR) on :47825 — iterate the UI
./scripts/dev.sh --server  # server only, skip the frontend build
```

| Want to… | Use |
|---|---|
| just look / demo | `./scripts/dev.sh` (built UI at :47824) |
| iterate on the React UI | `./scripts/dev.sh --dev`, open **:47825** (instant HMR) |
| work on the Python side only | `./scripts/dev.sh --server` |

Logs land in `logs/` (gitignored). Ports: **47823** MCP, **47824** edit screen, **47825**
Vite dev. Changing any of this (a port, a flag, the run flow) means updating this section —
see `harness_driver/dev.md`.

Ports default to the **uncommon** `47823` (MCP) / `47824` (preview) and **auto-bump to
the next free port** if taken — so it runs beside whatever an artist already has open.
`--preview` serves a live view of the edit chain with `HEAD` marked (auto-refresh,
dark+light checkerboard to judge alpha edges).

### Register with an MCP client (stdio)

```json
{
  "mcpServers": {
    "defringe-ai": { "command": "uv", "args": ["run", "defringe-ai", "serve"] }
  }
}
```

## Setup — onboarding an agent (any provider)

The working rules for this repo are **provider-agnostic**: they live in `harness_driver/`
(one concern per file) and are mapped by **[HARNESS.md](HARNESS.md)**, which is the
authoritative guidance any AI agent should follow. To point an agent at them:

- **Claude Code** — nothing to do. `CLAUDE.md` is auto-loaded and **chains** to HARNESS.md
  (`CLAUDE.md` → `HARNESS.md` → the `harness_driver/*.md` rule in scope). `CLAUDE.md` holds
  only personal prefs; the rules are in the harness.
- **Any other provider** — add **HARNESS.md** (and the `harness_driver/` rules it maps) to
  your agent's system/context/instructions, or create a thin entry file that says *"read
  HARNESS.md"*. Keep provider-specific prefs in that entry file; **never copy rules out of
  `harness_driver/`** — it's the single source.

**The chain (reading order):** personal/provider prefs → **HARNESS.md** → the
`harness_driver/*.md` rule for the task at hand. Changing this onboarding flow means
updating this section — see `harness_driver/onboarding.md`.

## What this is & how to use it — the tools

Each tool is an **MCP call** your agent makes (and a **CLI subcommand** you can run). It
edits the active workspace's `HEAD` and returns the new state, so the agent re-reads the
result and self-corrects. All pixel/point math is vectorised NumPy; OpenCV rasterises.
Pass an optional `workspace` to target a specific asset, or omit it to act on the one you
touched last.

**Transforms** — matte extraction + cleanup (gated: `edit(...)` → tools → `commit`/`cancel`):

| Tool | Does |
|---|---|
| `open_asset` | copy an external asset into a fresh workspace |
| `key_background` | luminance/value threshold → alpha, soft `lo..hi` ramp. `bg: white \| black \| #rrggbb \| r,g,b` |
| `crop` | carve a sub-rect (extract-region) |
| `trim_alpha` | crop to the content bounding box |
| **`defringe`** ⭐ | erode the alpha edge N px to drop the matte fringe, then **burn** the remaining edge pixels so a white/halo rim melts into a dark background |
| `upscale` | lanczos3 resample + gentle sharpen (holds linework; adds no real detail) |
| `silhouette_mask` | emit just the alpha shape for CSS `mask-image` tricks |
| `canny` | `cv2.Canny` edge map (white-on-black), `lo`/`hi` hysteresis — the edge *signal* |

**Annotate & shapes** — for flagging locations and drawing guides (burned into pixels):

| Tool | Does |
|---|---|
| `mark` | drop filled dots at a list of `[x,y]` points |
| `draw_shape` | one registered primitive — circle / ellipse / square / rectangle / triangle — placed by an `anchor` + bounding box; `fill`, `color`, `thickness` |
| `draw_line` | a straight line `(x1,y1)→(x2,y2)`, solid or dotted (a see-through guide) |

### Isolation — the cutout, via seed dots ⭐ (the `isolate` tools)

The headline workflow: turn a subject on a busy or fade-to-white background into a clean
matte, deterministically, by tracing a **rough** boundary. Value-based keying can't do
this (it punches holes in light interior areas); supplying the boundary fixes it. Every
image carries an **invisible mask layer** — dots in image-pixel space that ride *with* the
image, separate from the pixel edit chain.

| Tool | Does |
|---|---|
| `seed [[x,y],…]` | drop rough seed dots around the subject's edge (precision not needed) |
| `connect` | join the dots into a boundary — **convex hull, then snap inward** through every dot (deterministic; the same dots always give the same concave silhouette) |
| **`isolate`** ⭐ | fill that boundary into alpha = **the cutout** (transparent background, no interior holes) |
| `clear_seeds` | wipe the dots + outline and start over |

Then `defringe` melts any residual matte rim. Rough seeds in, tight matte out — the model
seeds, looks at the cut, and nudges. The edit screen exposes the same flow as toolbox
buttons (Dot → Connect → Cut out).

**Workspace / board controls:** `undo`, `redo` (per-image, two-level — see below),
`status`, `collapse`, `export`, `move` (place an asset on the canvas), `list_workspaces`.

### The edit screen

`serve --preview` opens a **Konva canvas** (React, built with Vite) at the preview URL:
every asset's current image, placed at its `(x,y)` on a grey/black transparency grid,
pushed live over **SSE** (no polling; the tab auto-reloads when the server restarts). Drag
and resize use Konva's native transform handles. A **left toolbox** drives the isolation flow:

- **Move** / **Dot** tools — drag/resize images (corner handles), or click to drop surface dots
- **View: Image / Mask** — toggle either layer off (hiding the image reveals the grid, the
  same read as a cut-out alpha)
- **Lock** — pin an image so clicks land as dots instead of dragging it
- **Connect dots (hull → snap)** → **Cut out (fill mask → alpha)** — the isolation path
- **Undo / Redo** (Ctrl-Z / Ctrl-Shift-Z) — **per-image, two-level**: placing dots bundles
  into one timeline action, but each dot is individually undoable while you're still
  placing them; any other action collapses the bundle. A live timeline shows the history.

The UI is orthogonal to the backend — it talks to the server only over `/api` + `/img` +
SSE. Its structure and conventions live in `harness_driver/frontend.md`.

Assets are movable by the agent (the `move` tool) and by you (drag — the drop persists).
`/chains` shows the per-asset reversible pixel edit history.

## Roadmap

- [x] MCP skeleton + NumPy core (`key_background`, `trim_alpha`, `defringe`, `upscale`, `silhouette_mask`, `canny`)
- [x] on-disk workspace with reversible undo/redo + `collapse` (verify), shared by CLI and MCP
- [x] annotate + shapes (`mark`, `draw_shape`, `draw_line`) and the live edit screen (Vite/React/Konva, SSE, left toolbox)
- [x] **isolation** — seed dots → `hull_snap` (convex hull → snap inward) → `fill_polygon_alpha`
- [x] per-image two-level undo (dots bundle into one action, each individually undoable mid-focus)
- [ ] **fully-automatic isolation** — `canny → close gaps → findContours → fill largest contour` (no seed dots)
- [ ] **edge-snap** — pull the `hull_snap` outline onto the nearest strong image edge for a pixel-tight matte
- [ ] tests + a sample asset sheet
- [ ] `tint`/`recolor`, `feather`, `drop-shadow`, `flip`/`rotate`
- [ ] `remove_bg` (ML via `rembg`, `pip install defringe-ai[ml]`) for photographic inputs
- [ ] publish to the MCP registry

## License

MIT
