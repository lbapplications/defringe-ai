"""Registry — the ``projects.json`` mount table that turns paths into identity.

This is the lean bridge the contract calls for (specs/workflow.md, C4/C6): a single JSON
file under the workspace home mapping **projects → assets**, keyed by the deterministic ids
from :mod:`identity`. It is cheap to load whole and carries no edit state (that lives per-asset
in ``history.json``/the manifest) — only the path↔id↔dir bindings needed to *find* an asset.

    projects.json = { "<project_id>": {
        "id":   "<project_id>",
        "path": "/abs/project/root",              # ground-truth identity; stored to verify
        "assets": { "<asset_id>": {
            "id":   "<asset_id>",
            "path": "relative/asset.png",         # identity within the project (verifies the id)
            "name": "asset",                       # a human label — how the window addresses it
            "dir":  "<home>/<project_id>/<asset_id>"   # where the bytes + history live
        } } }

Opening the *same path* twice resolves to the *same* asset (a resume, C6) — identity is the
path, not the call.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from . import identity


@dataclass
class Mount:
    """The result of mounting an asset — everything a caller needs to open its workspace."""

    project_id: str
    asset_id: str
    name: str
    dir: str
    root: str
    rel: str
    created: bool                    # True if this mount registered a new asset (vs. resumed one)
    renamed_from: str | None = None  # on a resume that changed the label: the old label, else None


class Registry:
    """The ``projects.json`` mount table for one workspace ``home``."""

    def __init__(self, home: str):
        self.home = home
        self.path = os.path.join(home, "projects.json")

    # --- io ----------------------------------------------------------------

    def _read(self) -> dict:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict) -> None:
        os.makedirs(self.home, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)                     # atomic swap — never a half-written table

    # --- mounting ----------------------------------------------------------

    def mount(self, asset_path: str, *, project_root: str | None = None,
              name: str | None = None) -> Mount:
        """Resolve ``asset_path`` to identity, registering its project + asset if new.

        png-gated (C8). The project root defaults to the asset's directory (so assets sharing a
        folder share a project); pass ``project_root`` to group a whole tree under one project.
        A second mount of the same path **resumes** the existing asset instead of duplicating it.
        """
        identity.ensure_png(asset_path)
        root = identity.norm_root(project_root) if project_root else os.path.dirname(
            os.path.realpath(asset_path))
        pid = identity.project_id(root)
        rel = identity.relativize(asset_path, root)
        aid = identity.asset_id(rel)

        data = self._read()
        proj = data.setdefault(pid, {"id": pid, "path": identity.norm_root(root), "assets": {}})
        assets = proj["assets"]

        created = aid not in assets
        renamed_from: str | None = None
        if created:
            label = self._unique_label(data, name or _default_label(rel))
            assets[aid] = {
                "id": aid,
                "path": rel,
                "name": label,
                "dir": os.path.join(self.home, pid, aid),
            }
        else:
            label = assets[aid]["name"]
            if name and name != label:               # an explicit rename on resume
                renamed_from = label                 # surfaced so the caller can migrate board state
                label = assets[aid]["name"] = self._unique_label(data, name, keep=aid)
        self._write(data)
        return Mount(pid, aid, label, assets[aid]["dir"], proj["path"], rel, created, renamed_from)

    def _unique_label(self, data: dict, want: str, keep: str | None = None) -> str:
        """``want`` if free across the whole table, else ``want-2``, ``want-3``, … — labels stay
        unique so the window can address an asset by its label unambiguously. ``keep`` excludes
        one asset_id from the clash check (so renaming an asset to its own label is a no-op)."""
        existing = {rec["name"]
                    for proj in data.values()
                    for aid, rec in proj["assets"].items()
                    if aid != keep}
        if want not in existing:
            return want
        i = 2
        while f"{want}-{i}" in existing:
            i += 1
        return f"{want}-{i}"

    # --- lookups -----------------------------------------------------------

    def resolve(self, project_id: str, asset_id: str) -> dict:
        """Return an asset record, **verifying** its stored paths still derive its ids.

        The verification (C3) is the whole point of storing the path beside the id: a corrupted
        or hand-edited table that would route into the wrong workspace is caught here, loudly."""
        data = self._read()
        proj = data.get(project_id)
        if not proj or asset_id not in proj["assets"]:
            raise ValueError(f"no such asset {asset_id!r} in project {project_id!r}")
        if identity.project_id(proj["path"]) != project_id:
            raise ValueError(f"project id/path mismatch for {project_id!r} (table corrupted?)")
        rec = proj["assets"][asset_id]
        if identity.asset_id(rec["path"]) != asset_id:
            raise ValueError(f"asset id/path mismatch for {asset_id!r} (table corrupted?)")
        return rec

    def locate(self, name: str) -> tuple[str, str] | None:
        """The (project_id, asset_id) of the asset with label ``name`` (or None)."""
        for pid, proj in self._read().items():
            for aid, rec in proj["assets"].items():
                if rec["name"] == name:
                    return pid, aid
        return None

    def dir_of(self, project_id: str, asset_id: str) -> str:
        """The storage directory of a (verified) asset."""
        return self.resolve(project_id, asset_id)["dir"]

    def dir_by_name(self, name: str) -> str | None:
        """The storage directory of the asset labelled ``name`` (or None if unknown).

        A single **unverified** read — the cheap lookup the board/web hot paths use. Call
        ``resolve``/``dir_of`` instead when you need the id↔path verification (a single
        deliberate lookup), not on the listing path where one bad record shouldn't cascade."""
        for proj in self._read().values():
            for rec in proj["assets"].values():
                if rec["name"] == name:
                    return rec["dir"]
        return None

    def dir_map(self) -> dict[str, str]:
        """``{label: dir}`` for every asset, from **one** read — the listing path (unverified).
        Used by ``Workspace.list_all`` so a sync doesn't re-parse the table once per asset."""
        return {rec["name"]: rec["dir"]
                for proj in self._read().values()
                for rec in proj["assets"].values()}

    def names(self) -> list[str]:
        """Every asset label, sorted — what the window/CLI lists."""
        return sorted(rec["name"]
                      for proj in self._read().values()
                      for rec in proj["assets"].values())

    def assets(self) -> list[tuple[str, str, dict]]:
        """Every (project_id, asset_id, record) triple in the table."""
        return [(pid, aid, rec)
                for pid, proj in self._read().items()
                for aid, rec in proj["assets"].items()]

    # --- migration ---------------------------------------------------------

    def adopt_legacy(self, source_root: str | None = None) -> list[str]:
        """Register any pre-identity flat workspaces (``home/<name>/manifest.json``) so an
        existing home keeps working after the rekey. Each is adopted **in place** (its ``dir``
        stays the old flat path — no bytes move) under a ``local`` project rooted at ``home``.
        Idempotent: already-registered names are skipped. Returns the names newly adopted."""
        root = identity.norm_root(source_root or self.home)
        pid = identity.project_id(root)
        data = self._read()
        # Idempotency is keyed on *identity* (asset_id), not the label — a re-adopt is a no-op
        # even if some other asset now carries the same basename as its label.
        known_ids = {aid for proj in data.values() for aid in proj["assets"]}
        adopted: list[str] = []
        for entry in sorted(os.listdir(self.home)) if os.path.isdir(self.home) else []:
            flat = os.path.join(self.home, entry)
            if not os.path.exists(os.path.join(flat, "manifest.json")):
                continue
            aid = identity.asset_id(entry)
            if aid in known_ids:
                continue
            proj = data.setdefault(pid, {"id": pid, "path": root, "assets": {}})
            label = self._unique_label(data, entry)      # keep labels globally unique on adopt too
            proj["assets"][aid] = {"id": aid, "path": entry, "name": label, "dir": flat}
            known_ids.add(aid)
            adopted.append(label)
        if adopted:
            self._write(data)
        return adopted


def _default_label(rel: str) -> str:
    """An asset's default label: its basename without extension (e.g. ``a/shark.png`` → ``shark``)."""
    return os.path.splitext(os.path.basename(rel))[0]
