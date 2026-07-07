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
- **Local, deterministic, no cloud.** Each tool: `image` ref → writes a PNG → returns
  `{session, path, width, height}` so the agent chains tools and re-reads the result.

## Run

```bash
uv sync                       # install
uv run defringe-ai            # stdio (for a local MCP client / agent)
uv run defringe-ai --http --preview   # HTTP server + browser gallery on :8787
```

`--preview` serves a live gallery of the `out/` dir (auto-refresh, dark+light
checkerboard so you can judge alpha edges) — this is the "see changes on a server" loop.

### Register with an MCP client (stdio)

```json
{
  "mcpServers": {
    "defringe-ai": { "command": "uv", "args": ["run", "defringe-ai"] }
  }
}
```

## Tools (v0)

| Tool | Does |
|---|---|
| `open_image` | load a file into a session |
| `key_background` | luminance/value threshold → alpha, soft `lo..hi` ramp. `bg: white \| black \| #rrggbb \| r,g,b` |
| `crop` | carve a sub-rect (extract-region) |
| `trim_alpha` | crop to the content bounding box |
| **`defringe`** ⭐ | erode the alpha edge N px to drop the matte fringe, then **burn** the remaining edge pixels so a white/halo rim melts into a dark background |
| `upscale` | lanczos3 resample + gentle sharpen (holds linework; adds no real detail) |
| `silhouette_mask` | emit just the alpha shape for CSS `mask-image` tricks |

Every tool accepts an `image` that is **either a filesystem path or a session id**
returned by a prior tool, so the agent chains ops without re-reading files.

## Roadmap

- [x] MCP skeleton + NumPy core (`key_background`, `trim_alpha`, `defringe`, `upscale`, `silhouette_mask`)
- [ ] tests + a sample asset sheet
- [ ] `tint`/`recolor`, `feather`, `drop-shadow`, `flip`/`rotate`
- [ ] `remove_bg` (ML via `rembg`, `pip install defringe-ai[ml]`) for photographic inputs
- [ ] publish to the MCP registry

## License

MIT
