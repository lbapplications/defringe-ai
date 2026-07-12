"""Shared runtime for the MCP tool modules — the one place the tools reach for.

Every tool lives in a category module under this package (``transform.py``, ``isolate.py``,
…) and registers itself through :func:`category`, which does two things at once: bind the
tool onto the shared :data:`mcp` server *and* record its ``(category, name, gated)`` so the
**taxonomy is derived from the modules themselves** — not hand-maintained as a separate dict.
Ask a module "what tools do you own?" and the answer is the functions it decorates.

`gated` tools (they MUTATE PIXELS) refuse unless an edit session is open — enforced by
:func:`apply` / an inline ``in_session`` check, reported by the taxonomy.

**Addressing is session-scoped (Phase 2, C2/C5).** There is no ambient "current asset": every
tool names its target with an opaque ``session`` id (minted by ``open_asset``), and the server
resolves it — ``session → (project_id, asset_id) → name`` — then drives the still-name-keyed
board/workspace under it. The old "omit it and act on the last one touched" sugar is gone; a
blank/unknown session is a loud, guided error. The server also **owns the cursor**: every applied
edit advances the session (:func:`advance`), so the live server log shows the session layer working.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .. import imageops as ops
from ..board import Board
from ..projection import Projection
from ..registry import Registry
from ..sessions import Sessions
from ..workspace import HOME as _DEFAULT_HOME
from ..workspace import Workspace

# The workspace root every tool acts on. Mutable at runtime (tests point it at a tmp home);
# tools read it live as ``core.HOME``, so there's a single source of truth to repoint.
HOME = _DEFAULT_HOME

mcp = FastMCP("defringe-ai")

# The derived taxonomy, filled as category modules import and decorate their tools.
_TAXONOMY: dict[str, list[str]] = {}
_GATED: set[str] = set()


def category(cat: str, *, gated: bool = False):
    """A decorator factory: register a tool under taxonomy category ``cat``.

    Bind it onto :data:`mcp` and record its membership (and whether the whole category is
    gated). Use it per module — ``tool = core.category("transform", gated=True)`` — so each
    file reads as "these are my tools" and the taxonomy falls out of the code."""
    def register(fn):
        _TAXONOMY.setdefault(cat, []).append(fn.__name__)
        if gated:
            _GATED.add(fn.__name__)
        return mcp.tool()(fn)
    return register


def taxonomy_map() -> dict[str, list[str]]:
    """The category → tool-names map, derived from what the modules registered."""
    return {c: list(names) for c, names in _TAXONOMY.items()}


def gated_set() -> set[str]:
    """The set of gated (pixel-mutating) tool names, derived from the modules."""
    return set(_GATED)


# --- session resolution + the edit gate (shared by the tool modules) -------

def open_session(name: str) -> str:
    """Open (or resume) a session on the asset labelled ``name`` → its ``session`` id. Called by
    ``open_asset`` and the window's per-asset mount. Resolves the label to identity through the
    registry, so the session is bound to ``(project_id, asset_id)`` — not the mutable label."""
    loc = Registry(HOME).locate(name)
    if not loc:
        raise ValueError(f"no asset labelled {name!r} to open a session on")
    pid, aid = loc
    return Sessions(HOME).open(pid, aid, name).id


def name(session: str) -> str:
    """A ``session`` id → the asset's current display label. Raises (with guidance) on a
    blank or unknown session — there is no ambient fallback (C2)."""
    return Sessions(HOME).name_of(session)


def workspace(session: str) -> tuple[str, Workspace]:
    """A ``session`` id → ``(name, Workspace)``. The read path a tool takes to reach the engine
    below the session layer, without touching the (retired) active pointer."""
    nm = name(session)
    return nm, Workspace.locate(nm, HOME)


def advance(session: str, ws: Workspace) -> None:
    """The post-change hook the tools fire after every mutation — two orthogonal reactions to
    one state change:

    1. **cursor** (C5): advance the session to ``ws``'s live HEADs via :meth:`Sessions.advance_to`,
       the one place that derivation lives, so the MCP tools and the window can't drift apart.
    2. **projection** (C7): mirror the new HEAD onto the user's real file, in place, live.

    Both are no-ops when nothing actually moved. Projection is best-effort — a stale session or a
    missing real file must not fail an edit; the backups (``.bk`` / ``backup/``) are the safety net,
    not withholding the write."""
    Sessions(HOME).advance_to(session, ws)
    try:
        pid, aid = Sessions(HOME).resolve(session)
        Projection(HOME, pid, aid).project(ws)
    except (FileNotFoundError, ValueError, KeyError, OSError):
        pass


def apply(op: str, fn, session: str, **params) -> dict:
    """Apply a pixel-mutating op on a session's asset — but only inside an edit session (the
    gate) — then advance the session cursor."""
    nm, ws = workspace(session)
    if not ws.in_session():
        raise ValueError(
            f"'{op}' is gated: this asset has no active edit session. "
            f'Call edit("<what you want to change>") first, then apply {op}; '
            f"cancel() to revert or commit() to keep."
        )
    st = ws.apply(op, fn, params)
    advance(session, ws)
    return st


__all__ = ["mcp", "HOME", "category", "taxonomy_map", "gated_set",
           "open_session", "name", "workspace", "advance", "apply",
           "ops", "Board", "Workspace", "Sessions", "Registry"]
