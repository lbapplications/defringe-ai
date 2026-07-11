"""The pydantic result models — construct + serialize."""

from __future__ import annotations

from defringe_ai.schemas import EdgeDetectTuneResult, IsolateResult, MaskState


def test_mask_state():
    m = MaskState(workspace="a", dots=3, outline=0, locked=False)
    assert m.model_dump()["dots"] == 3


def test_isolate_result():
    r = IsolateResult(workspace="a", head=1, steps=2, current="/x.png",
                      width=10, height=10, chain=["open", "isolate"])
    assert r.chain[-1] == "isolate"


def test_edge_detect_tune_result():
    r = EdgeDetectTuneResult(
        workspace="a", done=False, probe=1, lo=87, hi=175, bracket=[50, 300], nos=0,
        question="look", current="/x.png", head=1, steps=2, width=10, height=10)
    d = r.model_dump()
    assert d["done"] is False and d["bracket"] == [50, 300]
