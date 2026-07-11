"""[derive] Extract a SIGNAL (edges) as a mask overlay — the image is untouched, undoable."""

from __future__ import annotations

from .. import imageops as ops
from ..board import Board
from ..schemas import EdgeDetectTuneResult
from ..workspace import Workspace
from . import core

derive = core.category("derive")


@derive
def edge_detect(lo: int = 100, hi: int = 200, workspace: str = "") -> dict:
    """[derive] Edge map (Canny) laid down as a **mask overlay**, not a pixel edit — the
    original image is untouched and stays HEAD. `lo`/`hi` are the hysteresis thresholds
    (100/200 classic; lower them to catch fainter edges, raise to keep only strong ones).
    The edges are swept into a vivid, transparency-keyed overlay (matrix_sweep) that rides
    on top of the image under the mask view. The edge *signal*, not an isolation; undo
    clears the overlay."""
    name = core.name(workspace)
    if not name:
        raise ValueError("no active workspace — open an asset first")
    return _edge_detect_apply(name, lo, hi)


def _edge_overlay(img, lo: int, hi: int):
    """The edge mask overlay we render: thin **negative-of-the-image** lines (each edge
    pixel inverts what's beneath it, so it stays visible over any colour), keyed onto
    transparency. One place defines the look — both edge_detect and the tune search use it."""
    return ops.Transform.matrix_sweep(
        ops.Transform.edge_detect(img, lo, hi), mode="negative", base=img, bold=0, glow=0)


def _edge_detect_apply(name: str, lo: int, hi: int) -> dict:
    """Compute the edge map from the asset's current image and lay it down as a MASK
    OVERLAY VERSION (thin negative lines, transparency-keyed via matrix_sweep). The image is
    untouched — the original stays HEAD; the overlay is snapshotted into the asset's overlay
    chain and recorded as one timeline step, so the edit screen shows it under the mask view
    and undo restores the exact prior overlay (or none)."""
    ws = Workspace.resolve(name, core.HOME)
    Board(core.HOME).push_overlay(name, _edge_overlay(ws.current_array(), lo, hi), "edge → mask")
    return ws.status()


# --- adaptive edge detection: an agent-in-the-loop binary search over the threshold -----
# The tool bakes in the SEARCH (log(n): middle first, halve each step); YOU bake in the
# JUDGEMENT (look at the candidate, say which way). Converges in <=3 probes or after 2
# 'more' verdicts, then commits the winning edge map in place (undo restores the original).
_TUNE_KEY = "edge_detect_tune"
_TUNE_LEVEL = (50, 300)     # search range for the hysteresis level (hi); lo is level//2
_TUNE_MAX_PROBES = 3
_TUNE_MAX_NOS = 2


def _tune_render(name: str, ws: Workspace, cand: int) -> dict:
    """Render the candidate edge map as a mask-overlay preview — the original image is
    untouched and stays HEAD. Pushes an overlay version WITHOUT recording a timeline step,
    since a search's probes shouldn't spam the undo timeline until it converges."""
    Board(core.HOME).push_overlay(
        name, _edge_overlay(ws.current_array(), cand // 2, cand), "edge → mask", record=False)
    return ws.status()


def _tune_question(cand: int, probe: int) -> str:
    return (f"Probe {probe}/{_TUNE_MAX_PROBES} — edges at lo={cand // 2}, hi={cand}. LOOK at the "
            f"edge map: is your subject cleanly outlined? Call edge_detect_tune(verdict=…): "
            f"'reduce' (too many / noisy edges), 'more' (subject not fully outlined), or "
            f"'good' (stop here).")


def _tune_result(name: str, st: dict, state: dict, done: bool) -> EdgeDetectTuneResult:
    cand = state["cand"]
    return EdgeDetectTuneResult(
        workspace=name, done=done, probe=state["probe"], lo=cand // 2, hi=cand,
        bracket=[state["lo_b"], state["hi_b"]], nos=state["nos"],
        question="" if done else _tune_question(cand, state["probe"]),
        current=st["current"], head=st["head"], steps=st["steps"],
        width=st["width"], height=st["height"],
    )


def _tune_commit(ws: Workspace, name: str, state: dict) -> EdgeDetectTuneResult:
    """Finalise the converged candidate as the mask overlay, record the single image-level
    undo step (so the whole search collapses to one 'edge → mask' action), and clear the
    search state."""
    st = _tune_render(name, ws, state["cand"])
    Board(core.HOME).record_overlay_step(name, "edge → mask")
    ws.scratch_clear(_TUNE_KEY)
    return _tune_result(name, st, state, done=True)


@derive
def edge_detect_tune(verdict: str = "", workspace: str = "") -> EdgeDetectTuneResult:
    """[derive] Adaptive edge detection — find the threshold by LOOKING, not guessing. Call with no
    verdict to start: it renders the mid-range edge map and asks a question. You look at the
    result and call again with `verdict`: 'reduce' (too many / noisy edges → the search
    raises the threshold), 'more' (subject not fully outlined → it lowers the threshold), or
    'good' (stop now). It's a binary search — middle first, then halve the range each step —
    so it converges in at most 3 probes (or after 2 'more' verdicts). The winning edge map is
    committed in place; `undo` restores the original. This is the repo's loop in one tool:
    the tool owns the search, you own the judgement."""
    name = core.name(workspace)
    if not name:
        raise ValueError("no active workspace — open an asset first")
    ws = Workspace.resolve(name, core.HOME)
    state = ws.scratch_get(_TUNE_KEY)

    # start (or restart) — verdict ignored when there's no live search
    if not verdict or state is None:
        lo_b, hi_b = _TUNE_LEVEL
        cand = (lo_b + hi_b) // 2
        st = _tune_render(name, ws, cand)
        state = {"lo_b": lo_b, "hi_b": hi_b, "cand": cand, "probe": 1, "nos": 0}
        ws.scratch_set(_TUNE_KEY, state)
        return _tune_result(name, st, state, done=False)

    # continue — steer the bracket around the candidate the agent just judged
    v = verdict.strip().lower()
    if v in ("good", "stop", "done", "keep"):
        return _tune_commit(ws, name, state)
    if v in ("reduce", "fewer", "too_many", "noisy", "yes"):
        state["lo_b"] = state["cand"]            # fewer edges → raise level → upper half
    elif v in ("more", "increase", "too_few", "sparse", "no"):
        state["hi_b"] = state["cand"]            # more edges → lower level → lower half
        state["nos"] += 1
    else:
        raise ValueError("verdict must be 'reduce', 'more', or 'good'")

    state["probe"] += 1
    state["cand"] = (state["lo_b"] + state["hi_b"]) // 2
    if state["probe"] > _TUNE_MAX_PROBES or state["nos"] >= _TUNE_MAX_NOS:
        return _tune_commit(ws, name, state)

    st = _tune_render(name, ws, state["cand"])
    ws.scratch_set(_TUNE_KEY, state)
    return _tune_result(name, st, state, done=False)
