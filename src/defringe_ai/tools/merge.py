"""[merge] Ship approved work to the user's real file, and step between approved commits.

This is the commit side of the workflow (specs/workflow.md, C10) — the only tools that write
the user's actual file as a deliberate, approved act (the *live* projection during editing is
automatic, in ``core.advance``). Everything these tools touch outside the workspace ``home`` goes
through :class:`~defringe_ai.projection.Projection`, which owns the real file + ``.bk`` + the
``backup/`` ledger.
"""

from __future__ import annotations

from ..projection import Projection
from ..schemas import MergeResult
from ..sessions import Sessions
from . import core

merge_cat = core.category("merge")


@merge_cat
def merge(session: str = "") -> MergeResult:
    """[merge] Ship the current state to the user's real file as an approved commit. **Ask the
    user "is this good?" first** — calling this *is* the approval. It writes the current image onto
    their actual file (same name, in place), archives the previous base into the backup ledger so
    they can still step back to it, and collapses the fine edit chain to this state. The mask never
    ships — only the flattened image does. Pass the `session` from open_asset."""
    pid, aid = Sessions(core.HOME).resolve(session)
    nm, ws = core.workspace(session)
    res = Projection(core.HOME, pid, aid).merge(ws)
    core.advance(session, ws)                       # cursor now sits on the collapsed base
    st = ws.status()
    return MergeResult(workspace=nm, merged=res["merged"], commit=res["commit"],
                       commits=res["commits"], head=st["head"], steps=st["steps"])


@merge_cat
def revert_merge(commit: int, session: str = "") -> MergeResult:
    """[merge] Step back to a previously approved commit — restore its image onto the user's real
    file and make it the working base. `commit` is an index from a prior merge's `commits` ledger.
    Cross-merge navigation (C10): approved commits persist in the backup ledger even after later
    merges, so the user can move between them. Pass the `session` from open_asset."""
    pid, aid = Sessions(core.HOME).resolve(session)
    nm, ws = core.workspace(session)
    proj = Projection(core.HOME, pid, aid)
    res = proj.restore(ws, int(commit))
    core.advance(session, ws)
    st = ws.status()
    return MergeResult(workspace=nm, merged=proj.real, commit=res["restored"],
                       commits=res["commits"], head=st["head"], steps=st["steps"])
