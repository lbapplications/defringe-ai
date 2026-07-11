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
    a["mask"].setdefault("edge", False)      # an edge-map raster overlay (mask_edge.png) is present
    if not a.get("history") and all(k in a for k in ("x", "y", "scale")):
        a["history"] = History(_snapshot(a), "open").to_dict()
    return a


# --- per-image undo: the asset's board state <-> a History memento ---------

# The undoable slice of an asset's board state, PER IMAGE:
#   mask + lock      the invisible annotation layer
#   pixel_head       the workspace edit-chain HEAD → makes undo work at the IMAGE level:
#                    a committed transform (isolate, defringe, …) is captured here, so
#                    reverting a step moves the actual pixels back, not just the mask.
#   overlay_head     the workspace overlay-chain HEAD (-1 = none) → binds the LAYER chain
#                    the same way: reverting a derive step (edge/hull/simplify) restores
#                    that step's actual overlay pixels, not just the `edge` flag.
# Position/scale and z-order/selection are deliberately NOT tracked — moves aren't history
# we care to keep, so undo/goto never move an image, only revert its edits.
def _snapshot(a: dict) -> dict:
    return {
        "mask": copy.deepcopy(a["mask"]),
        "locked": a["locked"],
        "pixel_head": int(a.get("pixel_head", 0)),
        "overlay_head": int(a.get("overlay_head", -1)),
    }


def _restore(a: dict, snap: dict) -> None:
    a["mask"] = copy.deepcopy(snap["mask"])
    a["locked"] = snap["locked"]
    if "pixel_head" in snap:
        a["pixel_head"] = int(snap["pixel_head"])
    if "overlay_head" in snap:
        a["overlay_head"] = int(snap["overlay_head"])
    _ensure_layers(a)


def _current_pixel_head(home: str, name: str) -> int:
    """The live workspace HEAD for an asset (0 if it has no workspace yet)."""
    try:
        return Workspace(os.path.join(home, name)).head()
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
        return 0


def _current_overlay_head(home: str, name: str) -> int:
    """The live workspace overlay HEAD for an asset (-1 if it has none)."""
    try:
        return Workspace(os.path.join(home, name)).overlay_head()
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
        return -1


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
        for nm, a in b["assets"].items():               # backfill lock + mask + chain heads
            a["pixel_head"] = _current_pixel_head(self.home, nm)
            a["overlay_head"] = _current_overlay_head(self.home, nm)
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
        self._write(b)                                  # moves/resizes are NOT recorded
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

    def set_outline(self, name, outline, label="connect") -> dict:
        """Store a derived boundary polygon (list of [x, y], image space) on the mask.

        `label` names the timeline step: "connect" when the polygon is snapped through seed
        dots (`hull_snap`), "outline" when it's traced straight from the pixels
        (`simplify_contour`) — both land in the same `mask.outline` slot `isolate` fills."""
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            _ensure_layers(a)["mask"]["outline"] = [[int(x), int(y)] for x, y in outline]
            _commit(a, label)
            self._write(b)
        return b

    def push_overlay(self, name, img, label, record=True) -> dict:
        """Lay down a mask-overlay VERSION and (by default) record it as one timeline step.

        The raster is snapshotted into the asset's overlay chain (a real layer version), the
        mask is flagged ``edge``, and the memento captures the new ``overlay_head`` — so undo/
        goto restore this exact overlay's pixels, not merely the flag. Pass ``record=False``
        for live previews (e.g. the tune search) that shouldn't commit a timeline step until
        they finish; ``record_overlay_step`` then commits the settled version once."""
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            idx = Workspace(os.path.join(self.home, name)).push_overlay(img, label)
            a["overlay_head"] = idx
            _ensure_layers(a)["mask"]["edge"] = True
            if record:
                _commit(a, label)
            self._write(b)
        return b

    def record_overlay_step(self, name, label) -> dict:
        """Commit the asset's CURRENT overlay version as one timeline step — the overlay
        twin of ``record_pixel_edit``. No-op if the overlay HEAD hasn't moved since the last
        committed action (so an unchanged/idempotent preview adds no history)."""
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            h = _history(a)
            if h.state.get("overlay_head") != a.get("overlay_head"):
                _ensure_layers(a)["mask"]["edge"] = True
                _commit(a, label)
                self._write(b)
        return b

    # --- per-image undo / redo (focus-aware, image-level) ------------------

    def _apply_pixel_head(self, name, a) -> None:
        """Move the asset's workspace HEAD to the pixel_head just restored from a memento,
        so reverting a step moves the actual image — not only its mask."""
        ph = a.get("pixel_head")
        if ph is None:
            return
        try:
            Workspace(os.path.join(self.home, name)).set_head(int(ph))
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            pass

    def _apply_overlay_head(self, name, a) -> None:
        """Point the asset's workspace overlay HEAD at the overlay_head just restored from a
        memento, so reverting a derive step brings back that step's actual overlay pixels."""
        oh = a.get("overlay_head")
        if oh is None:
            return
        try:
            Workspace(os.path.join(self.home, name)).set_overlay_head(int(oh))
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            pass

    def record_pixel_edit(self, name, label) -> dict:
        """Record a committed *pixel* edit on the asset's per-image timeline. Called right
        after a transform commits (isolate, defringe, …): captures the new workspace HEAD
        as a memento so image-level undo can revert the whole image. No-op if the HEAD
        didn't actually move (an empty/idempotent commit adds no history)."""
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            h = _history(a)
            if h.state.get("pixel_head") != a.get("pixel_head"):
                _commit(a, label)
                self._write(b)
        return b

    def undo(self, name) -> dict:
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            h = _history(a)
            if h.undo():
                _restore(a, h.state)
                self._apply_pixel_head(name, a)
                self._apply_overlay_head(name, a)
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
                self._apply_pixel_head(name, a)
                self._apply_overlay_head(name, a)
            a["history"] = h.to_dict()
            self._write(b)
        return b

    def goto(self, name, index) -> dict:
        """Jump an asset to a specific point on its history timeline (dropdown select)."""
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            h = _history(a)
            if h.goto(index):
                _restore(a, h.state)
                self._apply_pixel_head(name, a)
                self._apply_overlay_head(name, a)
            a["history"] = h.to_dict()
            self._write(b)
        return b

    def reset_history(self, name) -> dict:
        """Reset an asset back to a clean slate: wipe its invisible mask layer (dots +
        outline) and erase its per-image history, re-seeding a single 'open' action from
        the now-clean state — so a reset leaves no stale mask *or* timeline steps."""
        b = self.sync()
        if name in b["assets"]:
            a = b["assets"][name]
            m = _ensure_layers(a)["mask"]
            m["dots"] = []
            m["outline"] = []
            m["edge"] = False
            try:                                        # detach the overlay layer chain
                Workspace(os.path.join(self.home, name)).set_overlay_head(-1)
            except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
                pass
            a["overlay_head"] = -1
            try:                                        # drop the legacy single-file overlay
                os.remove(os.path.join(self.home, name, "mask_edge.png"))
            except OSError:
                pass
            a["history"] = History(_snapshot(a), "open").to_dict()
            self._write(b)
        return b

    def undo_state(self, name) -> dict:
        a = self.sync().get("assets", {}).get(name)
        if not a:
            return {"can_undo": False, "can_redo": False, "timeline": []}
        h = _history(a)
        return {"can_undo": h.can_undo, "can_redo": h.can_redo, "timeline": h.timeline()}
