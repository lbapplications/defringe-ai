# Coordinate system — spec sheet

The one source of truth for how defringe-ai talks about pixel positions. Every tool
parameter named `x`, `y`, `w`, `h`, `cx`, `cy`, `radius`, etc. follows this.

## The convention (tool API + how most apps think)

**Origin `(0,0)` is the top-left. `x` increases to the → (right). `y` increases ↓ (down).**
Units are **pixels**, integers.

```
      x  →
   0 ───────────────► W-1
 y ┌───────────────┐
 │ │(0,0)          │   (0,0)   top-left
 ▼ │               │   (W-1,0) top-right
   │       •(cx,cy)│   (cx,cy) = (W/2, H/2) is the centre
   │               │   (0,H-1) bottom-left
   └───────────────┘   (W-1,H-1) bottom-right
```

| point (x, y) | means |
|---|---|
| `(0, 0)`   | top-left corner |
| `(5, 0)`   | 5 px **right**, 0 down |
| `(0, 5)`   | 0 right, 5 px **down** |
| `(W-1, H-1)` | bottom-right corner |
| `(W//2, H//2)` | centre of the image |

This is the convention used by **HTML canvas, CSS/SVG, Photoshop & most raster
editors, and OpenCV drawing points**. (The notable exception is OpenGL / math-style
axes, where `y` points **up** from a bottom-left origin — we do **not** use that.)

## ⚠️ The numpy transpose gotcha (read this)

Images are stored as numpy arrays, and **numpy is row-major: it indexes `arr[row, col]`,
which is `arr[y, x]` — the *transpose* of `arr[x][y]`.**

- axis 0 = **rows** = **y** (vertical, ↓)
- axis 1 = **cols** = **x** (horizontal, →)

So the intuitive-looking `arr[5][0]` is **row 5, col 0 = 5 px _down_, 0 right** — the
*opposite* of the point `(5, 0)` which is 5 right. They are transposed. Don't mix them up.

**Translation rules (memorise these two):**

| API / geometry (x, y) | numpy |
|---|---|
| pixel at point `(x, y)` | `arr[y, x]` |
| image size `(W, H)` (width, height) | `arr.shape == (H, W, C)` → `H, W = arr.shape[:2]` |

```python
H, W = img.shape[:2]          # H = height (rows, y-extent), W = width (cols, x-extent)
cx, cy = W // 2, H // 2        # centre as a POINT (x, y)
px = img[cy, cx]              # read that pixel: note it's [y, x], not [x, y]
```

## cv2 vs raw numpy

Handy fact: **OpenCV drawing functions take *points* as `(x, y)` tuples** — the same
convention as the tool API — even though the underlying array is `[y, x]`. So:

```python
cv2.circle(img, (x, y), r, color, thickness)   # (x, y) point — pass tool coords straight through
img[y, x] = color                              # raw indexing — flip to [y, x]
```

`draw_shape` relies on this: its `x, y` anchor resolves to a box, then cv2 draws with
`(x, y)` points; only hand-rolled numpy loops (e.g. the keyer/defringe) index `[y, x]`.

## Anchors (`draw_shape`)

`(x, y)` is where the **anchor** sits; the `anchor` name says which part of the shape's
bounding box lands there (same idea as CSS `transform-origin` / ImageMagick `-gravity`):

```
top_left    top     top_right
   ●─────────●─────────●
   │                   │
 left      center    right
   ●         ●         ●
   │                   │
   ●─────────●─────────●
bottom_left bottom  bottom_right
```

Default `center`: `(x, y)` is the middle of the shape (what "put a circle at (x,y)"
usually means). `top_left`: `(x, y)` is the box's top-left corner.

## Quick reference

- Params `(x, y)`: top-left origin, x→right, y→down, pixels.
- Size: `w` = width (x-extent), `h` = height (y-extent).
- Default "centre" = `(W//2, H//2)`.
- numpy: `arr[y, x]`, `shape == (H, W, C)`.
- cv2 points: `(x, y)` (same as API). numpy indexing: `[y, x]` (flipped).
