"""Shared runtime for the MCP tool modules — the one place the tools reach for.

Every tool lives in a category module under this package (``transform.py``, ``isolate.py``,
…) and registers itself through :func:`category`, which does two things at once: bind the
tool onto the shared :data:`mcp` server *and* record its ``(category, name, gated)`` so the
**taxonomy is derived from the modules themselves** — not hand-maintained as a separate dict.
Ask a module "what tools do you own?" and the answer is the functions it decorates.

`gated` tools (they MUTATE PIXELS) refuse unless an edit session is open — enforced by
:func:`apply` / an inline ``in_session`` check, reported by the taxonomy.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .. import imageops as ops
from ..board import Board
from ..workspace import HOME as _DEFAULT_HOME
from ..workspace import Workspace, _get_active

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


# --- resolution + the edit gate (shared by the tool modules) ---------------

def name(workspace: str) -> str:
    """Resolve a board asset label: the given one, or the active workspace."""
    return workspace or _get_active(HOME) or ""


def apply(op: str, fn, workspace: str, **params) -> dict:
    """Apply a pixel-mutating op — but only inside an edit session (the gate)."""
    ws = Workspace.resolve(workspace, HOME)
    if not ws.in_session():
        raise ValueError(
            f"'{op}' is gated: this asset has no active edit session. "
            f'Call edit("<what you want to change>") first, then apply {op}; '
            f"cancel() to revert or commit() to keep."
        )
    return ws.apply(op, fn, params)


__all__ = ["mcp", "HOME", "category", "taxonomy_map", "gated_set", "name", "apply",
           "ops", "Board", "Workspace", "_get_active"]
