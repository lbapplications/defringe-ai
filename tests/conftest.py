"""Shared fixtures for the suite. Everything is tiny + on tmp_path, so the whole run
stays fast (small synthetic RGBA arrays, no real assets, no live server)."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def rgba() -> np.ndarray:
    """A 20x20 RGBA test image: opaque white ground with a dark 8x8 square in the middle.

    Small but rich enough for every transform — keying (white ground), trim/crop (a content
    box), defringe (alpha edges), edge_detect (a hard edge)."""
    a = np.zeros((20, 20, 4), np.uint8)
    a[..., :3] = 255          # white
    a[..., 3] = 255           # opaque
    a[6:14, 6:14, :3] = 30    # dark square (the "subject")
    return a


@pytest.fixture
def asset_png(tmp_path, rgba) -> str:
    """`rgba` written to a PNG on disk — a source asset to `open_asset` into a workspace."""
    p = tmp_path / "square.png"
    Image.fromarray(rgba, mode="RGBA").save(p)
    return str(p)


@pytest.fixture
def asset_png2(tmp_path, rgba) -> str:
    """A *second, distinct* source PNG. Identity keys on the path (C3), so opening two names
    from one file now resolves to one asset — tests that want two assets use two files."""
    p = tmp_path / "square2.png"
    Image.fromarray(rgba, mode="RGBA").save(p)
    return str(p)


@pytest.fixture
def home(tmp_path) -> str:
    """An empty DEFRINGE_HOME (workspace root) on tmp_path."""
    h = tmp_path / "home"
    h.mkdir()
    return str(h)


@pytest.fixture
def opened(home, asset_png):
    """A workspace opened from the sample asset. Returns (home, name)."""
    from defringe_ai.workspace import Workspace

    ws = Workspace.open_asset(asset_png, home)
    return home, ws._read()["name"]


@pytest.fixture
def srv(monkeypatch, home):
    """The server module with the tool surface's HOME pointed at a tmp workspace root, so the
    MCP tools and CLI act on an isolated home. `HOME` lives in ``tools.core`` (tools read it
    live; ``server.HOME`` proxies to it), so that's the one place to repoint. Returns the module."""
    from defringe_ai import server
    from defringe_ai.tools import core

    monkeypatch.setattr(core, "HOME", home)
    return server
