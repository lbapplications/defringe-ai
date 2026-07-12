"""Sessions — the opaque handle an agent carries, resolved to an asset by the server.

The contract (specs/workflow.md, C5/C6) says the agent juggles no paths or hashes: it holds
an **opaque ``session_id``** scoped to one asset, and the server owns every id↔path resolution
and the edit **cursor**. This module is that layer — it sits *above* the registry (which turns
paths into identity) and *above* the board/workspace (which are still keyed by the human
``name`` label). A session is the bridge: ``session_id → (project_id, asset_id) → name``.

    session/
      working_session.json   { "<session_id>": session, ... }   # the active set
      sessions.json          { "<session_id>": session, ... }   # the ledger (every session, ever)

    session = {
      "id":         "<session_id>",        # uuid4 — opaque, the only token the agent carries
      "project_id": "<project_id>",        # REQUIRED
      "asset_id":   "<asset_id>",          # REQUIRED — a session is scoped to a single asset
      "name":       "shark",               # the current display label (refreshed on resume)
      "state_id":   "state_<n>",           # the pixel cursor  (may be None before the first edit)
      "mask_id":    "mask_<n>.png"         # the mask/overlay cursor (may be None)
    }

**Why a name-keyed board underneath.** The board is *persistent arrangement* state; a session is
an *ephemeral handle* (uuid4, many-per-asset in principle). Keying the board on ``session_id``
would be wrong — sessions come and go. So the stable ``asset_id`` (via its ``name`` label) stays
the board/workspace key, and the session resolves *to* it. That keeps this a thin resolution +
cursor layer, not a rewrite of the engine below it.

Opening the same asset twice **resumes** its working session (C6) rather than minting a second —
one live handle per asset. The server logs every open/resume/advance so a live ``--watch`` run
shows the session layer working.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass

from .registry import Registry


@dataclass
class Session:
    """A resolved session — what a caller gets back from :meth:`Sessions.open`."""

    id: str
    project_id: str
    asset_id: str
    name: str
    created: bool                 # True if this call minted a new session (vs. resumed one)


def _log(msg: str) -> None:
    """One greppable line to the server console — so a live ``--watch`` run *shows* the
    session layer working (open/resume/advance), which is otherwise invisible headless."""
    print(f"[session] {msg}", flush=True)


class Sessions:
    """The ``session/`` store for one workspace ``home`` (working set + ledger)."""

    def __init__(self, home: str):
        self.home = home
        self.dir = os.path.join(home, "session")
        self.working_path = os.path.join(self.dir, "working_session.json")
        self.ledger_path = os.path.join(self.dir, "sessions.json")

    # --- io ----------------------------------------------------------------

    def _read(self, path: str) -> dict:
        try:
            with open(path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, path: str, data: dict) -> None:
        os.makedirs(self.dir, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)                          # atomic swap — never a half-written file

    def _persist(self, session: dict) -> None:
        """Write a session into both the active set and the append-only ledger."""
        working = self._read(self.working_path)
        working[session["id"]] = session
        self._write(self.working_path, working)
        ledger = self._read(self.ledger_path)
        ledger[session["id"]] = session
        self._write(self.ledger_path, ledger)

    # --- open / resume -----------------------------------------------------

    def open(self, project_id: str, asset_id: str, name: str) -> Session:
        """Open a session on ``(project_id, asset_id)`` — or **resume** the live one for that
        asset if it already exists (C6: one handle per asset). Idempotent and cheap: a resume
        with an unchanged label neither rewrites the store nor logs, so the web loop can call
        this every SSE tick without churn."""
        working = self._read(self.working_path)
        for sid, s in working.items():
            if s.get("project_id") == project_id and s.get("asset_id") == asset_id:
                if s.get("name") != name:              # label was renamed → refresh the display field
                    s["name"] = name
                    self._persist(s)
                    _log(f"resumed {sid[:8]}… → {name} (relabelled)")
                return Session(sid, project_id, asset_id, name, created=False)

        sid = str(uuid.uuid4())
        s = {"id": sid, "project_id": project_id, "asset_id": asset_id,
             "name": name, "state_id": None, "mask_id": None}
        self._persist(s)
        _log(f"opened {sid[:8]}… → {name}  (project {project_id[:8]}…, asset {asset_id[:8]}…)")
        return Session(sid, project_id, asset_id, name, created=True)

    # --- resolve -----------------------------------------------------------

    def get(self, session_id: str) -> dict | None:
        """The raw working-session record (or None if unknown)."""
        return self._read(self.working_path).get(session_id)

    def _require(self, session_id: str) -> dict:
        if not session_id:
            raise ValueError(
                "this tool needs a session — open_asset(path) returns one as `session`; "
                "pass it here so the server knows which asset you mean.")
        s = self.get(session_id)
        if s is None:
            raise ValueError(f"unknown session {session_id!r} — call open_asset(path) to get one")
        return s

    def resolve(self, session_id: str) -> tuple[str, str]:
        """A session → its ``(project_id, asset_id)``. Raises with guidance on a bad/blank id."""
        s = self._require(session_id)
        return s["project_id"], s["asset_id"]

    def name_of(self, session_id: str) -> str:
        """A session → the asset's **current** display label, resolved live through the registry
        (so a rename since the session opened is reflected, and the id↔path binding is verified)."""
        pid, aid = self.resolve(session_id)
        return Registry(self.home).resolve(pid, aid)["name"]

    # --- cursor (server-owned) --------------------------------------------

    def advance(self, session_id: str, *, state_id: str | None, mask_id: str | None) -> None:
        """Advance the session's cursor after a change (C5: the server updates on every change).
        A no-op — no write, no log — when the cursor didn't actually move, so an idempotent op
        adds no churn."""
        s = self.get(session_id)
        if s is None or (s.get("state_id") == state_id and s.get("mask_id") == mask_id):
            return
        s["state_id"], s["mask_id"] = state_id, mask_id
        self._persist(s)
        _log(f"{s['name']} advanced → {state_id}" + (f" / {mask_id}" if mask_id else ""))

    def advance_to(self, session_id: str, ws) -> None:
        """Advance the cursor to a live :class:`~.workspace.Workspace`'s HEADs. This is the one
        place the ``(session, workspace) → cursor`` derivation lives — the pixel state maps to
        ``state_<head>``, the overlay to ``mask_<overlay_head>.png`` (None when the asset carries
        no overlay). **Both** addressed surfaces advance through here: the MCP tools (via
        ``tools.core.advance``) and the window (via ``web/app.py``), so neither can drift from the
        other's notion of the cursor. ``ws`` is duck-typed (``.head()`` / ``.overlay_head()``) so
        this layer takes no hard dependency on the engine below it."""
        oh = ws.overlay_head()
        self.advance(session_id, state_id=f"state_{ws.head()}",
                     mask_id=f"mask_{oh}.png" if oh >= 0 else None)

    # --- listing -----------------------------------------------------------

    def working(self) -> dict:
        """The active session set: ``{session_id: session}``."""
        return self._read(self.working_path)

    def by_name(self) -> dict[str, str]:
        """``{name: session_id}`` over the active set — the reverse lookup the window uses to
        find the session for an asset it's showing (last one wins if an asset somehow has two)."""
        return {s["name"]: sid for sid, s in self.working().items()}
