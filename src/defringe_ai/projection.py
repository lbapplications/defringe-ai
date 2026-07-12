"""Projection — the asset's relationship to the user's *real* file (the only irreversible writes).

Every other layer keeps its state inside the workspace ``home`` (PNG chains, manifests, the
registry table, sessions). This module is the one place that reaches **outside** it: it writes
the current edit onto the user's actual file, in place, live (specs/workflow.md, C7), and — on
approval — ships a chosen state as a permanent commit (C10). Quarantining every external,
irreversible write here is deliberate: it keeps :mod:`workspace` a self-contained dir, keeps
:mod:`registry` lean, and keeps :mod:`sessions` a thin resolve+cursor layer.

Three files make up the safety net around the live in-place write:

  * the **real file** (``project_root/relative_path``) — always mirrors the current HEAD, so any
    viewer the user has open just updates; the filename never changes, only the bytes.
  * the **``.bk`` sidecar** beside it — the pristine pre-everything original, written **only if
    absent** (so it captures the file's state before defringe-ai first touched it, and never again).
  * the **``backup/`` dir** inside the asset's workspace — archived *approved* bases, one per
    merge (``asset_0.png``, ``asset_1.png``, …). The directory listing **is** the commit ledger
    (no side JSON to desync from the bytes); the user can step back to any of them (:meth:`restore`).

``ws`` is duck-typed (``current_path`` / ``base_path`` / ``reseed_base``) so this module takes no
hard dependency on the engine below it.
"""

from __future__ import annotations

import filecmp
import os
import shutil

from .registry import Registry


def _log(msg: str) -> None:
    """One greppable ``[project]`` line to the server console — so a live ``--watch`` run *shows*
    the only irreversible writes landing (mirrors the ``[session]`` lines the session layer emits)."""
    print(f"[project] {msg}", flush=True)


class Projection:
    """The projection surface for one asset, identified by ``(project_id, asset_id)``.

    Resolves the asset's real path + workspace dir through the registry once, then all writes
    (live projection, merge, restore) go through this instance."""

    def __init__(self, home: str, project_id: str, asset_id: str):
        reg = Registry(home)
        self.real = reg.real_path(project_id, asset_id)   # the user's actual file (verified id↔path)
        self.dir = reg.dir_of(project_id, asset_id)       # the asset's workspace dir (holds backup/)

    # --- paths -------------------------------------------------------------

    @property
    def bk(self) -> str:
        """The ``.bk`` sidecar beside the user's real file (the pristine original)."""
        return self.real + ".bk"

    @property
    def backup_dir(self) -> str:
        """The archived-approved-bases directory (the cross-merge commit ledger)."""
        return os.path.join(self.dir, "backup")

    # --- live projection (C7) ---------------------------------------------

    def _ensure_bk(self) -> None:
        """Capture the pristine original into ``.bk`` — **write-if-absent**, so it snapshots the
        file exactly as it was before the first projection and is never overwritten again."""
        if os.path.exists(self.real) and not os.path.exists(self.bk):
            shutil.copy2(self.real, self.bk)

    def project(self, ws) -> bool:
        """Mirror the asset's current HEAD onto the user's real file, in place (C7).

        Byte-faithful (a PNG copy, no re-encode). A no-op when the real file is gone (nothing to
        project onto) or already holds these exact bytes — so a mask-only change, which leaves the
        pixel HEAD untouched, writes nothing and the mask never leaks onto the user's file.

        Args:
            ws: The asset's workspace (duck-typed: ``.current_path()`` gives the HEAD PNG).

        Returns:
            True if the real file was (re)written, False if the projection was skipped.
        """
        head = ws.current_path()
        if not os.path.isfile(self.real):                   # gone, or a legacy dir-keyed asset → skip
            return False
        if filecmp.cmp(head, self.real, shallow=False):     # HEAD already on disk → nothing to do
            return False
        self._ensure_bk()
        shutil.copy2(head, self.real)
        _log(f"{os.path.basename(self.real)} ← HEAD  →  {self.real}")
        return True

    # --- merge / restore (C10) --------------------------------------------

    def commits(self) -> list[int]:
        """The approved-commit indices in the ledger, ascending — derived from ``backup/`` itself
        (the archived-base PNGs), so the ledger can never desync from the bytes."""
        out = []
        if os.path.isdir(self.backup_dir):
            for f in os.listdir(self.backup_dir):
                if f.startswith("asset_") and f.endswith(".png"):
                    try:
                        out.append(int(f[len("asset_"):-len(".png")]))
                    except ValueError:
                        pass
        return sorted(out)

    def merge(self, ws) -> dict:
        """Ship the current HEAD as a permanent, approved commit (C10 — approval *is* the commit).

        Archives the **approved state** (HEAD) into the ``backup/`` ledger as this commit, ships it
        onto the real file, then flattens the edit chain so HEAD becomes the new base. Archiving the
        *approved* state (not the outgoing base) is what makes cross-merge navigation lossless: every
        approved commit stays in the ledger, so :meth:`restore` can return to any of them without
        destroying the one you're leaving. The pristine pre-everything original lives in ``.bk``; the
        **mask never ships** — only the flattened pixel state does. Refuses a mid-edit-session or a
        non-file real path rather than corrupting state.

        Args:
            ws: The asset's workspace (duck-typed: ``.current_path()``, ``.collapse()``, ``.in_session()``).

        Returns:
            ``{"merged": <real path>, "commit": <new index>, "commits": [...]}``.

        Raises:
            ValueError: If there's no real file to ship onto, or an edit session is still open.
        """
        if not os.path.isfile(self.real):
            raise ValueError(f"cannot merge {os.path.basename(self.dir)}: it has no real file to ship "
                             f"onto ({self.real}). Adopted/legacy assets aren't backed by an external file.")
        if ws.in_session():
            raise ValueError("commit or cancel the open edit session before merging — "
                             "merge ships an approved state, not a half-finished edit.")
        os.makedirs(self.backup_dir, exist_ok=True)
        self._ensure_bk()                                   # pristine original safe before any write
        idx = (self.commits()[-1] + 1) if self.commits() else 0
        head = ws.current_path()
        shutil.copy2(head, os.path.join(self.backup_dir, f"asset_{idx}.png"))   # archive the approved state
        if not filecmp.cmp(head, self.real, shallow=False):
            shutil.copy2(head, self.real)                   # ship it (skip if projection already synced)
        ws.collapse()                                       # HEAD is now the lone base (fine chain collapses)
        _log(f"merged {os.path.basename(self.real)} → commit {idx}  ({self.real})")
        return {"merged": self.real, "commit": idx, "commits": self.commits()}

    def restore(self, ws, index: int) -> dict:
        """Return the user's file (and the engine) to a previously approved commit (C10 cross-merge
        navigation). Byte-faithful: the archived base is written back onto the real file and reseeded
        as the workspace's lone base.

        Args:
            ws: The asset's workspace (duck-typed: ``.reseed_base(src)``).
            index: Which approved commit to restore (an index from :meth:`commits`).

        Returns:
            ``{"restored": <index>, "commits": [...]}`` plus the workspace status.

        Raises:
            ValueError: If ``index`` is not an archived commit.
        """
        src = os.path.join(self.backup_dir, f"asset_{index}.png")
        if not os.path.exists(src):
            raise ValueError(f"no approved commit {index} to restore (have {self.commits()})")
        if not os.path.isfile(self.real):
            raise ValueError(f"cannot restore onto {os.path.basename(self.dir)}: it has no real file.")
        self._ensure_bk()                                   # never overwrite the real file without a sidecar
        shutil.copy2(src, self.real)                        # the user sees the restored commit
        st = ws.reseed_base(src)                            # the engine agrees: HEAD = the restored base
        _log(f"restored {os.path.basename(self.real)} ← commit {index}")
        return {"restored": index, "commits": self.commits(), **st}
