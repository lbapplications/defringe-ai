"""The workspace engine — the 'playground' the MCP server and CLI both drive.

A workspace is a directory on disk holding one asset and its full edit history as
an append-only chain of PNG snapshots with a HEAD pointer. This is the stateful
core; MCP tools and the CLI are thin front-ends over it, so state survives an
agent restart and a human and the agent can edit the same asset.

Model
-----
  source/<name>.png     the original, copied in once, never mutated
  history/NNNN-op.png   one full snapshot per edit (truly reversible)
  manifest.json         {name, source, steps:[{op,params,file,ts}], head}

  apply    -> snapshot, drop any redo tail, HEAD -> new step
  undo/redo-> move HEAD (snapshots are kept)
  collapse -> flatten history to HEAD as the lone base (the 'verified asset')
"""

from __future__ import annotations

import json
import os
import shutil
import time
from typing import Callable

import numpy as np

from . import imageops as ops

HOME = os.environ.get("DEFRINGE_HOME", "workspace")


class Workspace:
    def __init__(self, root: str):
        self.root = root
        self.manifest_path = os.path.join(root, "manifest.json")

    # --- lifecycle ---------------------------------------------------------

    @classmethod
    def open_asset(cls, src_path: str, home: str = HOME, name: str | None = None) -> "Workspace":
        """Copy an external asset into a fresh workspace and seed step 0."""
        if not os.path.exists(src_path):
            raise ValueError(f"no such asset: {src_path!r}")
        name = name or os.path.splitext(os.path.basename(src_path))[0]
        root = os.path.join(home, name)
        if os.path.exists(root):
            shutil.rmtree(root)
        os.makedirs(os.path.join(root, "source"))
        os.makedirs(os.path.join(root, "history"))

        ws = cls(root)
        local_src = os.path.join(root, "source", os.path.basename(src_path))
        shutil.copy2(src_path, local_src)

        img = ops.load(local_src)
        step_file = os.path.join("history", "0000-open.png")
        ops.save(img, os.path.join(root, step_file))
        ws._write(
            {
                "name": name,
                "source": os.path.relpath(local_src, root),
                "steps": [{"op": "open", "params": {}, "file": step_file, "ts": _now()}],
                "head": 0,
            }
        )
        _set_active(home, name)
        return ws

    @classmethod
    def active(cls, home: str = HOME) -> "Workspace":
        """The workspace last opened or touched (or a raised error if none)."""
        name = _get_active(home)
        if not name:
            raise ValueError("no active workspace — call open_asset first")
        return cls(os.path.join(home, name))

    @classmethod
    def resolve(cls, name: str = "", home: str = HOME) -> "Workspace":
        """A workspace by name (which then becomes active), or the active one if blank.

        This is the versatility hook: the agent can open several assets and address
        each by name, or omit the name and keep shaping whatever it touched last.
        """
        if not name:
            return cls.active(home)
        root = os.path.join(home, name)
        if not os.path.exists(os.path.join(root, "manifest.json")):
            raise ValueError(f"no workspace named {name!r} — open one first ({cls.list_all(home)})")
        _set_active(home, name)
        return cls(root)

    @classmethod
    def list_all(cls, home: str = HOME) -> list[str]:
        """Every open workspace, so the agent (or a human) can see what it's juggling."""
        if not os.path.isdir(home):
            return []
        return sorted(
            d for d in os.listdir(home)
            if os.path.exists(os.path.join(home, d, "manifest.json"))
        )

    # --- edits -------------------------------------------------------------

    def apply(self, op: str, fn: Callable[..., np.ndarray], params: dict) -> dict:
        """Run a transform on HEAD, snapshot it, and advance HEAD (dropping any redo tail)."""
        m = self._read()
        result = fn(self.current_array(), **params)

        # truncate the redo tail: anything after HEAD is now orphaned
        for st in m["steps"][m["head"] + 1:]:
            _rm(os.path.join(self.root, st["file"]))
        m["steps"] = m["steps"][: m["head"] + 1]

        idx = len(m["steps"])
        step_file = os.path.join("history", f"{idx:04d}-{op}.png")
        ops.save(result, os.path.join(self.root, step_file))
        m["steps"].append({"op": op, "params": params, "file": step_file, "ts": _now()})
        m["head"] = idx
        self._write(m)
        return self.status()

    def undo(self) -> dict:
        m = self._read()
        m["head"] = max(0, m["head"] - 1)
        self._write(m)
        return self.status()

    def redo(self) -> dict:
        m = self._read()
        m["head"] = min(len(m["steps"]) - 1, m["head"] + 1)
        self._write(m)
        return self.status()

    def collapse(self) -> dict:
        """Verify: flatten the chain to HEAD as the lone base, discard the rest."""
        m = self._read()
        keep = self.current_array()
        for st in m["steps"]:
            _rm(os.path.join(self.root, st["file"]))
        base = os.path.join("history", "0000-base.png")
        ops.save(keep, os.path.join(self.root, base))
        m["steps"] = [{"op": "collapsed", "params": {}, "file": base, "ts": _now()}]
        m["head"] = 0
        self._write(m)
        return self.status()

    def export(self, dest: str) -> dict:
        """Write the current (HEAD) image out to an arbitrary path — the deliverable."""
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        shutil.copy2(self.current_path(), dest)
        return {"exported": dest, **self.status()}

    # --- reads -------------------------------------------------------------

    def current_path(self) -> str:
        m = self._read()
        return os.path.join(self.root, m["steps"][m["head"]]["file"])

    def current_array(self) -> np.ndarray:
        return ops.load(self.current_path())

    def status(self) -> dict:
        m = self._read()
        img = self.current_array()
        h, w = img.shape[:2]
        return {
            "workspace": m["name"],
            "root": self.root,
            "head": m["head"],
            "steps": len(m["steps"]),
            "can_undo": m["head"] > 0,
            "can_redo": m["head"] < len(m["steps"]) - 1,
            "current": self.current_path(),
            "width": w,
            "height": h,
            "chain": [s["op"] for s in m["steps"]],
        }

    # --- io ----------------------------------------------------------------

    def _read(self) -> dict:
        with open(self.manifest_path) as f:
            return json.load(f)

    def _write(self, m: dict) -> None:
        with open(self.manifest_path, "w") as f:
            json.dump(m, f, indent=2)


def _now() -> float:
    return round(time.time(), 3)


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _active_file(home: str) -> str:
    return os.path.join(home, ".active")


def _set_active(home: str, name: str) -> None:
    os.makedirs(home, exist_ok=True)
    with open(_active_file(home), "w") as f:
        f.write(name)


def _get_active(home: str) -> str | None:
    try:
        with open(_active_file(home)) as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None
