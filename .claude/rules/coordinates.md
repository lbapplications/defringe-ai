# Rule: coordinates — (x, y) top-left, and the numpy transpose

**Scope — read before** any geometry, pixel-indexing, drawing, or dot/mask work.
Canonical spec: `docs/coordinates.md`.

- **Tool API is `(x, y)`, origin top-left, x→right, y→down** — matches CSS / canvas /
  cv2 points. Dots, boxes, line endpoints, polygons all use this.
- **Gotcha: numpy indexes `arr[y, x]`** (row-major) — the transpose of `arr[x][y]`.
  Image **size `(W, H)`** corresponds to array **shape `(H, W, C)`**. Mixing these up is
  the #1 source of "why is it rotated/offset" bugs.
- **`draw_shape` `anchor`** (center default + 8 edges/corners, like CSS
  `transform-origin` / ImageMagick gravity) names which part of the bounding box sits at
  `(x, y)`. `Shape.resolve_box` turns anchor+size into a concrete pixel box.
- **Mask dots are stored in image-pixel space** and rendered at `x/w`, `y/h` percentages
  so they ride with the image as it moves/scales on the board.
