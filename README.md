# defringe-ai

**AI-native image tooling — "free Photoshop for UI."**

A small [MCP](https://modelcontextprotocol.io) server that hands a vision-capable AI a
set of **deterministic raster transforms** — crop, key, mask, clean, composite — so it
can turn reference art, screenshots, and concept images into game/UI-ready assets
*without a human in an image editor*.

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
uv run defringe-ai serve --http --preview      # HTTP + browser gallery
```

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

## Tools (v0)

**Transforms** — each applies to the active workspace's `HEAD`:

| Tool | Does |
|---|---|
| `open_asset` | copy an external asset into a fresh workspace |
| `key_background` | luminance/value threshold → alpha, soft `lo..hi` ramp. `bg: white \| black \| #rrggbb \| r,g,b` |
| `crop` | carve a sub-rect (extract-region) |
| `trim_alpha` | crop to the content bounding box |
| **`defringe`** ⭐ | erode the alpha edge N px to drop the matte fringe, then **burn** the remaining edge pixels so a white/halo rim melts into a dark background |
| `upscale` | lanczos3 resample + gentle sharpen (holds linework; adds no real detail) |
| `silhouette_mask` | emit just the alpha shape for CSS `mask-image` tricks |

**Workspace controls:** `undo`, `redo`, `status`, `collapse`, `export`.

## Roadmap

- [x] MCP skeleton + NumPy core (`key_background`, `trim_alpha`, `defringe`, `upscale`, `silhouette_mask`)
- [x] on-disk workspace with reversible undo/redo + `collapse` (verify), shared by CLI and MCP
- [ ] tests + a sample asset sheet
- [ ] `tint`/`recolor`, `feather`, `drop-shadow`, `flip`/`rotate`
- [ ] `remove_bg` (ML via `rembg`, `pip install defringe-ai[ml]`) for photographic inputs
- [ ] publish to the MCP registry

## License

MIT
