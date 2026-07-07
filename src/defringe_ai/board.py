"""The board — how assets are *arranged*, distinct from how each is *edited*.

`workspace.py` owns a single asset's edit history. `board.py` owns the layout of all
assets on the shared canvas: each asset's position + scale, the **z-order**, and the
**selection**. Kept on disk (`<home>/board.json`) so it survives reloads and both the
human and the agent drive the same arrangement.

Z-order is modelled the way real canvas libraries (Konva/Fabric) do it: an **explicit
back-to-front list of names**, not an ever-growing z-index number. `z-index` is just an
asset's index in that list. "Bring to front" = move the name to the end of the list.
Selection is separate state (which asset is the current target/highlight).
"""

from __future__ import annotations

import json
import os

from .workspace import Workspace


def _staggered(i: int) -> dict:
    return {"x": 40 + (i % 4) * 250, "y": 40 + (i // 4) * 250, "scale": 1.0}


def _seed_from_manifest(home: str, name: str) -> dict | None:
    """Migrate an asset's placement from an older workspace manifest, if it has one."""
    try:
        with open(os.path.join(home, name, "manifest.json")) as f:
            c = json.load(f).get("canvas")
        if c:
            return {"x": c.get("x", 40), "y": c.get("y", 40), "scale": c.get("scale", 1.0)}
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None


class Board:
    def __init__(self, home: str):
        self.home = home
        self.path = os.path.join(home, "board.json")

    # --- persistence -------------------------------------------------------

    def _read(self) -> dict:
        try:
            with open(self.path) as f:
                b = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            b = {}
        b.setdefault("order", [])
        b.setdefault("selected", None)
        b.setdefault("assets", {})
        return b

    def _write(self, b: dict) -> None:
        os.makedirs(self.home, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(b, f, indent=2)

    # --- reconciliation ----------------------------------------------------

    def sync(self) -> dict:
        """Reconcile the board with the workspaces that actually exist: add new assets
        (seeding placement from an old manifest or a staggered slot), drop stale ones."""
        names = Workspace.list_all(self.home)
        b = self._read()
        for name in names:
            if name not in b["assets"]:
                b["assets"][name] = _seed_from_manifest(self.home, name) or _staggered(len(b["order"]))
                if name not in b["order"]:
                    b["order"].append(name)
        b["order"] = [n for n in b["order"] if n in names]
        b["assets"] = {n: v for n, v in b["assets"].items() if n in names}
        if b["selected"] not in names:
            b["selected"] = b["order"][-1] if b["order"] else None
        self._write(b)
        return b

    # --- mutations ---------------------------------------------------------

    def place(self, name, x=None, y=None, scale=None) -> dict:
        b = self.sync()
        if name not in b["assets"]:
            return b
        a = b["assets"][name]
        if x is not None:
            a["x"] = int(x)
        if y is not None:
            a["y"] = int(y)
        if scale is not None:
            a["scale"] = round(max(0.1, min(6.0, float(scale))), 3)
        self._write(b)
        return b

    def bring_to_front(self, name) -> dict:
        b = self.sync()
        if name in b["order"]:
            b["order"].remove(name)
            b["order"].append(name)
            self._write(b)
        return b

    def select(self, name) -> dict:
        """Select an asset (the highlight/target) and raise it to the front."""
        b = self.bring_to_front(name)
        if name in b["assets"]:
            b["selected"] = name
            self._write(b)
        return b
