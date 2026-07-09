# defringe-ai

**AI-native image tooling. "Free Photoshop for UI."**

A small MCP server that gives a vision-capable AI a set of **deterministic raster
transforms** it can call natively — so it can turn reference art, screenshots, and
concept images into game/UI-ready assets *without a human in an image editor*.

> Seed repo — idea dump to fiddle with when bored. Not started yet. The reference
> implementations below were all written (and proven) live while theming a UI, so the
> tool list is grounded in what the work *actually* reached for, not speculation.

## The thesis (why this is a real niche)

An AI like Claude can **see** an image but can't **generate** one. That asymmetry is
usually treated as a dead end. It isn't — it's a **closed loop**:

```
reference/screenshot ──▶ [deterministic transform tool] ──▶ result
        ▲                                                     │
        └──────────────  AI LOOKS, tunes params  ◀────────────┘
```

The AI doesn't need to *paint*. It needs to **crop, key, mask, clean, and composite**
with parameters — and then *look at the output and adjust*. That's exactly how a human
uses Photoshop's non-painting tools (magic wand, refine edge, levels, transform). Give
those to the model as tools and it can do real asset prep on its own.

The value is the pairing: **vision model + parameterized transforms + it can see the
result to self-correct.** Nobody's packaged the boring-but-essential matting/cleanup
ops as first-class AI tools.

## The tools (v0 — every one of these earned its place on a real job)

| Tool | Does | Real use it came from |
|---|---|---|
| `key-background` | luminance/value threshold → alpha, with a soft LO..HI ramp for AA edges. `bg: white \| black \| color` | cut a black octopus off a logo; a wreck off black; rocks off a white sheet |
| `crop` / `extract-region` | carve a sub-rect out of a sheet | slicing 4 separate rocks out of one asset sheet |
| `trim-alpha` | crop to the content bounding box | every extracted asset |
| **`defringe`** ⭐ | erode the alpha edge in N px to drop the matte fringe, then **burn** (darken) the remaining edge pixels so a white/halo rim melts into a dark background instead of glowing | the white-trim killer — the tool that named this repo |
| `upscale` | lanczos3 resample + gentle sharpen (holds linework; adds no real detail — honest about that) | enlarging low-res carved assets without pixelation |
| `silhouette-mask` | emit just the alpha shape (for CSS `mask-image` atmospheric-veil tricks) | tinting a sprite toward its background by masking a colored gradient to its shape |

Obvious v1 adds: `tint`/`recolor`, `feather`, `drop-shadow`, `flip`/`rotate`,
`remove-bg` (ML, via `rembg`) for photographic inputs where luminance keying fails.

## Stack

- **Node + [`sharp`](https://sharp.pixelplumbing.com)**, wrapped with the **TypeScript MCP
  SDK**. `sharp` covers resize/extract/trim/composite natively; the pixel-level passes
  (`key-background`, `defringe`'s erode+burn) are ~30-line raw-RGBA loops.
- **Local, deterministic, no cloud.** Each tool: `input` path + params → writes `output`
  → returns `{ path, width, height }` so the agent chains tools and re-reads the result.
- Python + Pillow/OpenCV (+ `rembg`) is the alt if you'd rather lean on ML background
  removal from day one.

## Reference: the `defringe` core (proven — port this first)

The star tool. Kills the white matte fringe left when you key art off a white
background: erode the alpha edge inward ~1px, then darken the edge pixels so they read
as a dark line (invisible on dark backgrounds) instead of a glowing white halo.

```js
// input: raw RGBA (data, W, H, C=4). BURN=0.45, RIM_LUM=135.
// 1) eroded alpha E = 3x3 neighbourhood MIN of alpha  (shrinks the matte ~1px)
// 2) for each pixel with E>0:
//      edge = (E < 250) || (touches a near-transparent neighbour && luminance > RIM_LUM)
//      if edge: rgb *= BURN            // "burn it in" — melts the rim into the dark bg
//      alpha = E
```

`key-background` (the extractor it complements):

```js
// value V = max(r,g,b) for a black bg;  luminance for a white bg.
// alpha = 0 below LO, 255 above HI, linear ramp between (soft AA edge).
// then trim-alpha to the content box.
```

## Repo intent (read before adding ceremony)

This is **just a public repo to test an MCP** — a scratchpad, not a product. It lives on
**one branch (`master`)**; no feature branches, no PRs, no worktrees to babysit. **Don't
force structure on it yet** — no CI, packaging polish, elaborate configs, or big
refactors unless asked. Keep changes small and direct; commit straight to `master`.

Two folders are kept (empty, via `.gitkeep`) and their contents git-ignored:
`inputs/` (drop source art here) and `workspace/` (runtime edit state the server writes).

## Status / next

Built (Python + FastMCP + NumPy + OpenCV + Pillow + Starlette): the workspace engine
(reversible edit chain + edit-session gate), the transforms (`key_background`,
`trim_alpha`, `crop`, `defringe`, `upscale`, `silhouette_mask`, `canny`), `draw_shape` +
`mark`, the board (arrange/z-order), and the live edit screen (SSE push, auto-reload).

- [ ] **isolation (tool #1)**: Canny → close gaps → `findContours` → fill largest contour
      into alpha (the deterministic cutout). `canny` lands the edge signal; this closes it.
- [ ] publish to the MCP registry (mcpmarket etc.)

Fiddle when bored. The hard part (knowing *which* tools matter) is already done.
