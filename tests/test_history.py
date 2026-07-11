"""history.py — the focus-aware per-image undo engine (no image knowledge at all)."""

from __future__ import annotations

from defringe_ai.history import History


def _s(n):
    return {"v": n}


def test_commit_and_undo_redo():
    h = History(_s(0))
    h.commit("a", _s(1))
    h.commit("b", _s(2))
    assert h.state == _s(2)
    assert h.can_undo and not h.can_redo
    assert h.undo() and h.state == _s(1)
    assert h.can_redo
    assert h.redo() and h.state == _s(2)
    assert not h.redo()          # nothing ahead


def test_commit_drops_redo_tail():
    h = History(_s(0))
    h.commit("a", _s(1))
    h.undo()
    h.commit("c", _s(9))         # forks from head, drops the old redo
    assert h.state == _s(9)
    assert not h.can_redo


def test_focus_bundles_substeps():
    h = History(_s(0))
    h.begin_focus("dots")
    h.step("dots", _s(1))
    h.step("dots", _s(2))
    assert h.in_focus and h.focus_label == "dots"
    assert h.state == _s(2)
    # focus-undo pops one sub-step at a time
    assert h.undo() and h.state == _s(1)
    # commit collapses the whole focus into ONE timeline action
    h.end_focus()
    assert not h.in_focus
    h.commit("next", _s(5))
    assert h.undo() and h.state == _s(1)   # jumps past the whole bundle


def test_step_with_new_label_collapses_prior_focus():
    h = History(_s(0))
    h.step("dots", _s(1))
    h.step("lines", _s(2))       # different label → prior focus collapses first
    assert h.focus_label == "lines"
    committed = [m for m in h.timeline() if not m.startswith("~")]
    assert any("dots" in m for m in committed)   # 'dots' became a committed action


def test_undo_empty_focus_falls_through_to_timeline():
    h = History(_s(0))
    h.commit("a", _s(1))
    h.begin_focus("empty")       # opened but no steps
    assert h.undo()              # drops the empty focus, then steps the timeline back
    assert h.state == _s(0)


def test_cancel_focus():
    h = History(_s(0))
    h.commit("a", _s(1))
    h.begin_focus("x")
    h.step("x", _s(2))
    h.cancel_focus()
    assert not h.in_focus and h.state == _s(1)


def test_redo_blocked_during_focus():
    h = History(_s(0))
    h.commit("a", _s(1))
    h.undo()
    h.begin_focus("x")
    assert h.redo() is False


def test_goto():
    h = History(_s(0))
    h.commit("a", _s(1))
    h.commit("b", _s(2))
    assert h.goto(0) and h.state == _s(0)
    assert h.goto(99) and h.state == _s(2)   # clamped to last
    assert h.goto(2) is False                # already there → no-op


def test_timeline_marks_head_and_focus():
    h = History(_s(0))
    h.commit("a", _s(1))
    h.begin_focus("dots")
    h.step("dots", _s(2))
    tl = h.timeline()
    assert any(m.startswith("* ") for m in tl)
    assert any(m.startswith("~ dots") for m in tl)


def test_to_from_dict_roundtrip():
    h = History(_s(0))
    h.commit("a", _s(1))
    h.begin_focus("dots")
    h.step("dots", _s(2))
    d = h.to_dict()
    h2 = History.from_dict(d)
    assert h2.state == _s(2)
    assert h2.in_focus


def test_from_dict_empty_defaults():
    h = History.from_dict({})
    assert h.state == {}
    assert not h.can_undo
