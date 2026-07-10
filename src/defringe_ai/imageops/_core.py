"""Shared primitives every tool set leans on: RGBA I/O and colour parsing.

Not a tool set itself — `Io` and `Color` are the substrate the `Transform` / `Shape` /
`Annotate` / `Geometry` classes build on. Kept separate so no tool class depends on
another tool class, only on this core.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

RGBA = np.ndarray  # (H, W, 4) uint8, alias for intent


class Io:
    """Read/write images as (H, W, 4) uint8 RGBA arrays."""

    @staticmethod
    def load(path: str) -> RGBA:
        """Read any image as (H, W, 4) uint8 RGBA."""
        return np.asarray(Image.open(path).convert("RGBA"))

    @staticmethod
    def save(img: RGBA, path: str) -> tuple[int, int]:
        """Write an RGBA array as PNG. Returns (width, height)."""
        Image.fromarray(img, mode="RGBA").save(path)
        h, w = img.shape[:2]
        return w, h


class Color:
    """Colour parsing shared by the drawing tools. Names / #hex / r,g,b -> RGBA."""

    NAMED = {
        "red": (255, 0, 0, 255), "green": (0, 200, 0, 255), "blue": (0, 90, 255, 255),
        "white": (255, 255, 255, 255), "black": (0, 0, 0, 255), "yellow": (255, 210, 0, 255),
        "orange": (255, 140, 0, 255), "cyan": (0, 200, 220, 255), "magenta": (230, 0, 200, 255),
        "gray": (128, 128, 128, 255), "grey": (128, 128, 128, 255), "transparent": (0, 0, 0, 0),
    }

    @staticmethod
    def parse(s) -> tuple:
        """'red' | '#rrggbb[aa]' | 'r,g,b[,a]' | already-a-tuple  ->  (R,G,B,A) uint8."""
        if isinstance(s, (tuple, list)):
            c = list(int(v) for v in s)
        elif s.strip().startswith("#"):
            h = s.strip()[1:]
            c = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
        elif "," in s:
            c = [int(v) for v in s.split(",")]
        else:
            key = s.strip().lower()
            if key not in Color.NAMED:
                raise ValueError(f"unknown colour {s!r}; use a name, #hex, or r,g,b[,a]")
            return Color.NAMED[key]
        if len(c) == 3:
            c.append(255)
        return tuple(c[:4])

    @staticmethod
    def parse_rgb(s: str) -> np.ndarray:
        """'#rrggbb' or 'r,g,b' -> uint8 array [r,g,b] (for keying against a bg colour)."""
        s = s.strip()
        if s.startswith("#"):
            s = s[1:]
            return np.array([int(s[i: i + 2], 16) for i in (0, 2, 4)], np.uint8)
        return np.array([int(p) for p in s.split(",")[:3]], np.uint8)
