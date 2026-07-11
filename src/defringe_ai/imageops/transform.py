"""``Transform`` — pixel transforms: matte extraction + cleanup.

The core "non-painting Photoshop" ops: pull a subject off a background, tidy the matte,
resample, read edges. Every method is ``RGBA -> RGBA``, deterministic, and vectorised —
the passes are whole-array NumPy math plus the odd ``cv2`` call, never per-pixel loops.
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from .utils import RGBA, Color


def _luminance(rgb: np.ndarray) -> np.ndarray:
    """Rec.601 luminance of an RGB array, float32 ``(H, W)``."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return 0.299 * r + 0.587 * g + 0.114 * b


def _min3x3(a: np.ndarray) -> np.ndarray:
    """3x3 neighbourhood minimum == a single-step erosion of a uint8 plane."""
    return cv2.erode(a, np.ones((3, 3), np.uint8))


class Transform:
    """Matte extraction + pixel cleanup. All methods take and return RGBA ``(H, W, 4)``."""

    @staticmethod
    def key_background(img: RGBA, bg: str = "white", lo: int = 40, hi: int = 90) -> RGBA:
        """Threshold a flat background into alpha, with a soft ramp for anti-aliased edges.

        Builds a per-pixel "foreground-ness" score, then maps it: alpha 0 below ``lo``,
        255 above ``hi``, linear between. Score depends on the background:
        ``black`` -> ``max(r,g,b)``; ``white`` -> ``255 - luminance``; a colour ->
        distance from that colour.

        Args:
            img: Source RGBA image on a roughly flat background.
            bg: ``"white"``, ``"black"``, or a colour (``"#rrggbb"`` / ``"r,g,b"``).
            lo: Score at/below which a pixel is fully transparent.
            hi: Score at/above which a pixel is fully opaque.

        Returns:
            A new RGBA array with the background keyed into the alpha channel.
        """
        rgb = img[..., :3].astype(np.float32)
        if bg == "black":
            score = rgb.max(axis=-1)
        elif bg == "white":
            score = 255.0 - _luminance(rgb)
        else:
            key = Color.parse_rgb(bg).astype(np.float32)
            dist = np.linalg.norm(rgb - key, axis=-1)      # 0..~441
            score = np.clip(dist / (441.673 / 255.0), 0, 255)
        ramp = np.clip((score - lo) * (255.0 / max(hi - lo, 1)), 0, 255)
        out = img.copy()
        out[..., 3] = ramp.astype(np.uint8)
        return out

    @staticmethod
    def trim_alpha(img: RGBA) -> RGBA:
        """Crop the image to the bounding box of its non-transparent pixels.

        Args:
            img: Source RGBA image.

        Returns:
            The image cropped to ``alpha > 0``, or the input unchanged if fully transparent.
        """
        ys, xs = np.nonzero(img[..., 3])
        if len(xs) == 0:
            return img
        return img[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]

    @staticmethod
    def crop(img: RGBA, x: int, y: int, w: int, h: int) -> RGBA:
        """Carve out a sub-rectangle (clamped to the image bounds).

        Args:
            img: Source RGBA image.
            x: Left edge of the rect (top-left origin, x->right).
            y: Top edge of the rect (y->down).
            w: Rect width in pixels.
            h: Rect height in pixels.

        Returns:
            A view of the sub-rect (empty if the rect lies fully outside the image).
        """
        H, W = img.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(H, y + h)
        return img[y0:y1, x0:x1]

    @staticmethod
    def defringe(img: RGBA, erode_px: int = 1, burn: float = 0.45,
                 rim_lum: float = 135.0, transparent_below: int = 16) -> RGBA:
        """Kill the white matte fringe left by keying art off a light background.

        Erodes the alpha inward, then darkens ("burns") the remaining edge pixels so a
        white/halo rim reads as a dark line that melts into a dark background instead of
        glowing.

        Args:
            img: Source RGBA image (typically straight out of ``key_background``).
            erode_px: How many 1px 3x3-minimum steps to shrink the alpha by.
            burn: Multiplier applied to edge RGB (``<1`` darkens; 0.45 = burn to ~45%).
            rim_lum: Only burn edge pixels brighter than this luminance (targets white rims).
            transparent_below: Alpha under which a neighbour counts as "transparent".

        Returns:
            A new RGBA array with the eroded alpha and burned rim.
        """
        alpha = img[..., 3]
        e = alpha
        for _ in range(max(erode_px, 1)):
            e = _min3x3(e)
        neighbour_min = _min3x3(alpha)
        touches_transparent = neighbour_min < transparent_below
        lum = _luminance(img[..., :3].astype(np.float32))
        keep = e > 0
        edge = keep & ((e < 250) | (touches_transparent & (lum > rim_lum)))
        out = img.copy().astype(np.float32)
        out[edge, :3] *= burn
        out = out.astype(np.uint8)
        out[..., 3] = e
        return out

    @staticmethod
    def upscale(img: RGBA, factor: float = 2.0, sharpen: float = 0.6) -> RGBA:
        """Enlarge with Lanczos3 resampling and a gentle unsharp pass.

        Holds linework crisp but adds no real detail (honest resampling, not synthesis).

        Args:
            img: Source RGBA image.
            factor: Scale multiplier (2.0 doubles each dimension).
            sharpen: Unsharp strength, 0..1 (0 disables the pass).

        Returns:
            The enlarged RGBA array.
        """
        h, w = img.shape[:2]
        pil = Image.fromarray(img, mode="RGBA").resize(
            (round(w * factor), round(h * factor)), Image.LANCZOS)
        if sharpen > 0:
            from PIL import ImageFilter
            pil = pil.filter(
                ImageFilter.UnsharpMask(radius=1.0, percent=int(sharpen * 100), threshold=1))
        return np.asarray(pil)

    @staticmethod
    def silhouette_mask(img: RGBA) -> RGBA:
        """Emit just the alpha shape as white-on-transparent, for CSS ``mask-image`` tricks.

        Args:
            img: Source RGBA image.

        Returns:
            A new RGBA array: RGB forced white, original alpha preserved.
        """
        out = np.zeros_like(img)
        out[..., :3] = 255
        out[..., 3] = img[..., 3]
        return out

    @staticmethod
    def matrix_sweep(img: RGBA, color: str = "#35ff7d", threshold: int = 8,
                     bold: int = 1, glow: float = 3.0,
                     mode: str = "color", base: RGBA | None = None) -> RGBA:
        """Sweep an image into a transparency-keyed line overlay: black drops out, edges show.

        Copies the image into a fresh matrix (``* 1``), reads per-pixel brightness, sends
        the black part to fully transparent alpha, and paints everything that survives —
        optionally thickened into a **bold core** with a **soft glow** halo. The surviving
        pixels are coloured by ``mode``:

        * ``"color"``    — one fixed ``color`` (the vivid default).
        * ``"white"``    — plain white lines.
        * ``"negative"`` — each kept pixel becomes the photographic negative (``255 - rgb``)
          of ``base`` at that spot, so the line always contrasts whatever sits under it.

        Built to turn an edge map (white lines on black) into a mask overlay you lay over
        the original image: the background vanishes, the edges stay.

        Args:
            img: Source RGBA — an edge map, or any light-on-dark signal.
            color: Colour for ``mode="color"``.
            threshold: Brightness (0..255) at/below which a pixel is black -> transparent.
            bold: 3x3 dilations of the kept pixels (0 = crisp 1px lines).
            glow: Gaussian sigma of the halo bled around the core (0 disables the glow).
            mode: ``"color"`` | ``"white"`` | ``"negative"`` — how kept pixels are coloured.
            base: The image the negative is taken from (defaults to ``img``); used only by
                ``mode="negative"`` — pass the ORIGINAL so lines invert what's beneath them.

        Returns:
            A new RGBA: coloured per ``mode`` over the kept lines (opaque core fading through
            the glow), fully transparent where the source was black.
        """
        work = img[..., :3].astype(np.float32) * 1.0        # the whole image into a separate matrix
        lum = _luminance(work)                               # (H, W) brightness 0..255
        core = ((lum > threshold).astype(np.uint8) * 255)    # black -> transparent; the rest kept
        if bold > 0:
            core = cv2.dilate(core, np.ones((3, 3), np.uint8), iterations=bold)   # thicken to a bold core
        halo = cv2.GaussianBlur(core, (0, 0), sigmaX=glow) if glow > 0 else np.zeros_like(core)
        alpha = np.maximum(core.astype(np.float32), halo.astype(np.float32) * 0.7)  # opaque core + soft halo
        out = np.zeros_like(img)
        if mode == "negative":
            src = (img if base is None else base)[..., :3].astype(np.int16)
            out[..., :3] = (255 - src).astype(np.uint8)      # invert whatever the line sits over
        elif mode == "white":
            out[..., :3] = 255
        else:
            out[..., :3] = Color.parse_rgb(color)[:3].astype(np.float32)
        out[..., 3] = np.clip(alpha, 0, 255).astype(np.uint8)
        return out

    @staticmethod
    def edge_detect(img: RGBA, lo: int = 100, hi: int = 200) -> RGBA:
        """Compute an edge map via the Canny algorithm (white edges on opaque black).

        The *edge signal*, not an isolation — closing the gaps + ``findContours`` + fill
        would turn it into a cutout (see :mod:`.geometry` for the seeded path).

        Args:
            img: Source RGBA image.
            lo: Weak (lower) hysteresis threshold.
            hi: Strong (upper) hysteresis threshold. 100/200 is the classic pairing.

        Returns:
            A full RGBA snapshot: white where an edge fired, opaque black elsewhere.
        """
        edges = cv2.Canny(img[..., :3], lo, hi)      # (H, W) uint8, 0 or 255
        out = np.zeros_like(img)
        out[..., :3] = edges[..., None]              # white where an edge fired
        out[..., 3] = 255                            # opaque so the black bg reads on the canvas
        return out
