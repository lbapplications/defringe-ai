"""Shared concepts every tool set leans on — the ``utils`` home.

The orthogonalization standard (see ``harness_driver/orthogonalization.md``): a tool class
depends on ``utils`` and nothing else — **never on another tool class**. The moment a
concept is needed in a second area, it moves *here*. Today that's RGBA I/O (``Io``) and
colour parsing (``Color``); numeric helpers stay local to their one class until a second
caller appears.

Everything is NumPy-first: pixels are ``(H, W, 4)`` uint8 arrays and math is vectorised
(no per-pixel Python loops). Native-Python loops over pixels/points are a smell — see the
NumPy standard in ``harness_driver/tools.md``.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

RGBA = np.ndarray  # (H, W, 4) uint8, alias for intent


class Io:
    """Read and write images as ``(H, W, 4)`` uint8 RGBA arrays."""

    @staticmethod
    def load(path: str) -> RGBA:
        """Read any image file as an RGBA array.

        Args:
            path: Filesystem path to the source image (any Pillow-readable format).

        Returns:
            The image as an ``(H, W, 4)`` uint8 RGBA array (alpha forced on).
        """
        return np.asarray(Image.open(path).convert("RGBA"))

    @staticmethod
    def save(img: RGBA, path: str) -> tuple[int, int]:
        """Write an RGBA array to disk as a PNG.

        Args:
            img: The ``(H, W, 4)`` uint8 array to write.
            path: Destination path (``.png``).

        Returns:
            The written image's ``(width, height)`` in pixels.
        """
        Image.fromarray(img, mode="RGBA").save(path)
        h, w = img.shape[:2]
        return w, h


class Color:
    """Colour parsing shared by every drawing tool. Names / ``#hex`` / ``r,g,b`` -> RGBA."""

    NAMED = {
        "red": (255, 0, 0, 255), "green": (0, 200, 0, 255), "blue": (0, 90, 255, 255),
        "white": (255, 255, 255, 255), "black": (0, 0, 0, 255), "yellow": (255, 210, 0, 255),
        "orange": (255, 140, 0, 255), "cyan": (0, 200, 220, 255), "magenta": (230, 0, 200, 255),
        "gray": (128, 128, 128, 255), "grey": (128, 128, 128, 255), "transparent": (0, 0, 0, 0),
    }

    @staticmethod
    def parse(s) -> tuple:
        """Resolve a colour spec to an RGBA 4-tuple.

        Args:
            s: A named colour (``"red"``), ``"#rrggbb"`` / ``"#rrggbbaa"``,
                ``"r,g,b"`` / ``"r,g,b,a"``, or an already-built ``(r,g,b[,a])`` sequence.

        Returns:
            An ``(R, G, B, A)`` uint8 tuple (alpha defaults to 255).

        Raises:
            ValueError: If ``s`` is a name that isn't in ``NAMED``.
        """
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
        """Resolve a colour spec to an RGB array, for keying against a background colour.

        Args:
            s: A ``"#rrggbb"`` hex string or ``"r,g,b"`` triple.

        Returns:
            A length-3 uint8 array ``[r, g, b]``.
        """
        s = s.strip()
        if s.startswith("#"):
            s = s[1:]
            return np.array([int(s[i: i + 2], 16) for i in (0, 2, 4)], np.uint8)
        return np.array([int(p) for p in s.split(",")[:3]], np.uint8)
