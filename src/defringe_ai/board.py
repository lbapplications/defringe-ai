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

import copy
import json
import os

from .history import History
from .workspace import Workspace


def _staggered(i: int) -> dict:
    return {"x": 40 + (i % 4) * 250, "y": 40 + (i // 4) * 250, "scale": 1.0}


def _ensure_layers(a: dict) -> dict:
    """Every asset carries a lock flag + an invisible mask layer (dots in image space,
    plus a derived `outline` polygon once the dots are connected), and a per-image undo
    History seeded from its clean opening state (so the FIRST action is reversible)."""
    a.setdefault("locked", False)
    a.setdefault("mask", {})
    a["mask"].setdefault("dots", [])
    a["mask"].setdefault("outline", [])
    if not a.get("history") and all(k in a for k in ("x", "y", "scale")):
        a["history"] = History(_snapshot(a), "open").to_dict()
    return a


# --- per-image undo: the asset's board state <-> a History memento ---------

# The undoable slice of an asset's board state (z-order/selection are global, not here).
def _snapshot(a: dict) -> dict:
    return {"mask": copy.deepcopy(a["mask"]), "locked": a["locked"],
            "x": a["x"], "y": a["y"], "scale": a["scale"]}


def _restore(a: dict, snap: dict) -> None:
    a["mask"] = copy.deepcopy(snap["mask"])
    a["locked"], a["x"], a["y"], a["scale"] = snap["locked"], snap["x"], snap["y"], snap["scale"]
    _ensure_layers(a)


def _history(a: dict) -> History:
    """Load the asset's History, seeding it from current state on first touch."""
    _ensure_layers(a)
    return History.from_dict(a["history"]) if a.get("history") else History(_snapshot(a), "open")


def _commit(a: dict, label: str) -> None:
    """Record the asset's CURRENT state as one atomic action on its timeline."""
    h = _history(a)
    h.commit(label, _snapshot(a))
    a["history"] = h.to_dict()


def _step(a: dict, label: str) -> None:
    """Record the asset's current state as a sub-step of a `label` focus (bundle)."""
    h = _history(a)
    h.step(label, _snapshot(a))
    a["history"] = h.to_dict()


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
        for a in b["assets"].values():                 # backfill lock + mask on every asset
            _ensure_layers(a)
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
        _commit(a, "resize" if scale is not None else "move")
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

    # --- mask layer (invisible per-image annotation) -----------------------

    def lock(self, name, locked=True) -> dict:
        """Pin an asset so clicks drop mask dots instead of dragging it."""
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            a["locked"] = bool(locked)
            _commit(a, "lock" if a["locked"] else "unlock")
            self._write(b)
        return b

    def add_dot(self, name, x, y) -> dict:
        """Drop a surface dot on the asset's invisible mask, in image-pixel space.
        Each dot is a sub-step of a 'place dots' focus (bundle) so it can be undone one
        at a time; the bundle collapses to a single timeline action on the next action."""
        b = self.sync()
        if name in b["assets"] and x is not None and y is not None:
            a = b["assets"][name]
            m = _ensure_layers(a)["mask"]
            m["dots"].append([int(x), int(y)])
            m["outline"] = []                          # dots changed -> stale outline
            _step(a, "place dots")
            self._write(b)
        return b

    def clear_dots(self, name) -> dict:
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            m = _ensure_layers(a)["mask"]
            m["dots"], m["outline"] = [], []
            _commit(a, "clear dots")
            self._write(b)
        return b

    def set_outline(self, name, outline) -> dict:
        """Store a derived boundary polygon (list of [x, y], image space) on the mask."""
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            _ensure_layers(a)["mask"]["outline"] = [[int(x), int(y)] for x, y in outline]
            _commit(a, "connect")
            self._write(b)
        return b

    # --- per-image undo / redo (focus-aware) -------------------------------

    def undo(self, name) -> dict:
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            h = _history(a)
            if h.undo():
                _restore(a, h.state)
            a["history"] = h.to_dict()
            self._write(b)
        return b

    def redo(self, name) -> dict:
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            h = _history(a)
            if h.redo():
                _restore(a, h.state)
            a["history"] = h.to_dict()
            self._write(b)
        return b

    def undo_state(self, name) -> dict:
        a = self.sync().get("assets", {}).get(name)
        if not a:
            return {"can_undo": False, "can_redo": False, "timeline": []}
        h = _history(a)
        return {"can_undo": h.can_undo, "can_redo": h.can_redo, "timeline": h.timeline()}
