"""board.py — arrangement + the invisible mask layer + image-level undo (pixel_head)."""

from __future__ import annotations

import json
import os

import numpy as np
import pytest

from defringe_ai import imageops as ops
from defringe_ai.board import Board, _current_pixel_head, _seed_from_manifest
from defringe_ai.workspace import Workspace


@pytest.fixture
def board(home, asset_png):
    Workspace.open_asset(asset_png, home, name="a")
    return Board(home), "a"


def test_sync_adds_and_selects(board):
    b, name = board
    state = b.sync()
    assert name in state["assets"]
    assert name in state["order"]
    assert state["selected"] == name


def test_sync_drops_stale(home, asset_png):
    Workspace.open_asset(asset_png, home, name="a")
    b = Board(home)
    b.sync()
    # remove the workspace on disk, re-sync → asset drops out
    import shutil

    shutil.rmtree(os.path.join(home, "a"))
    state = b.sync()
    assert "a" not in state["assets"]
    assert state["selected"] is None


def test_place_and_bring_to_front(board, asset_png, home):
    b, name = board
    Workspace.open_asset(asset_png, home, name="b")
    b.place(name, x=100, y=50, scale=2.0)
    a = b.sync()["assets"][name]
    assert a["x"] == 100 and a["y"] == 50 and a["scale"] == 2.0
    b.bring_to_front(name)
    assert b.sync()["order"][-1] == name


def test_place_scale_clamped(board):
    b, name = board
    b.place(name, scale=99.0)
    assert b.sync()["assets"][name]["scale"] == 6.0


def test_select(board, asset_png, home):
    b, name = board
    Workspace.open_asset(asset_png, home, name="b")
    b.select(name)
    assert b.sync()["selected"] == name


def test_lock_unlock_records_history(board):
    b, name = board
    b.lock(name, True)
    assert b.sync()["assets"][name]["locked"] is True
    b.lock(name, False)
    assert b.sync()["assets"][name]["locked"] is False


def test_dots_bundle_and_undo(board):
    b, name = board
    b.add_dot(name, 5, 5)
    b.add_dot(name, 15, 5)
    assert len(b.sync()["assets"][name]["mask"]["dots"]) == 2
    # each dot is individually undoable while the focus is open
    b.undo(name)
    assert len(b.sync()["assets"][name]["mask"]["dots"]) == 1


def test_connect_then_clear(board):
    b, name = board
    for p in ([2, 2], [18, 2], [18, 18], [2, 18]):
        b.add_dot(name, *p)
    b.set_outline(name, ops.Geometry.hull_snap(
        b.sync()["assets"][name]["mask"]["dots"]))
    assert len(b.sync()["assets"][name]["mask"]["outline"]) >= 3
    b.clear_dots(name)
    m = b.sync()["assets"][name]["mask"]
    assert m["dots"] == [] and m["outline"] == []


def test_record_pixel_edit_and_image_level_undo(board, home):
    b, name = board
    b.sync()                              # seed the per-image timeline at HEAD 0 (as the live UI does)
    ws = Workspace.resolve(name, home)
    # commit a real pixel edit, then record it on the per-image timeline
    ws.begin_edit("x")
    ws.apply("edge_detect", ops.Transform.edge_detect, {"lo": 50, "hi": 150})
    ws.commit_edit()
    b.record_pixel_edit(name, "edge_detect")
    assert ws.head() == 1
    # image-level undo moves the actual pixel HEAD back
    b.undo(name)
    assert Workspace.resolve(name, home).head() == 0
    b.redo(name)
    assert Workspace.resolve(name, home).head() == 1


def test_record_pixel_edit_noop_when_head_unmoved(board):
    b, name = board
    before = json.dumps(b.sync()["assets"][name].get("history"))
    b.record_pixel_edit(name, "noop")     # HEAD never moved → no new action
    after = json.dumps(b.sync()["assets"][name].get("history"))
    assert before == after


def test_goto_and_reset_history(board):
    b, name = board
    b.add_dot(name, 5, 5)
    b.clear_dots(name)                    # a committed action after the dots bundle
    b.goto(name, 0)
    # reset wipes the mask AND the timeline
    b.add_dot(name, 9, 9)
    b.reset_history(name)
    a = b.sync()["assets"][name]
    assert a["mask"]["dots"] == []
    st = b.undo_state(name)
    assert st["can_undo"] is False


def _overlay(shape=(20, 20)):
    """A tiny transparency-keyed overlay to push as a layer version."""
    ov = np.zeros((*shape, 4), np.uint8)
    ov[5:15, 5:15] = (255, 0, 0, 255)
    return ov


def test_push_overlay_versions_record_and_undo(board):
    b, name = board
    b.sync()
    ws = Workspace(os.path.join(b.home, name))

    b.push_overlay(name, _overlay(), "edge → mask")        # version 0, one timeline action
    a = b.sync()["assets"][name]
    assert a["mask"]["edge"] is True and a["overlay_head"] == 0
    assert ws.overlay_head() == 0

    b.push_overlay(name, _overlay(), "simplify_contour")   # version 1, a second action
    assert b.sync()["assets"][name]["overlay_head"] == 1
    assert ws.overlay_head() == 1

    b.undo(name)                                           # back to version 0's overlay
    assert b.sync()["assets"][name]["overlay_head"] == 0
    assert ws.overlay_head() == 0

    b.undo(name)                                           # back to open: no overlay
    a = b.sync()["assets"][name]
    assert a["mask"]["edge"] is False and a["overlay_head"] == -1
    assert ws.overlay_head() == -1


def test_push_overlay_preview_then_record(board):
    b, name = board
    b.sync()
    before = json.dumps(b.sync()["assets"][name].get("history"))
    b.push_overlay(name, _overlay(), "edge → mask", record=False)   # preview → no history
    after = json.dumps(b.sync()["assets"][name].get("history"))
    assert before == after
    assert b.sync()["assets"][name]["mask"]["edge"] is True
    b.record_overlay_step(name, "edge → mask")             # settle → one action
    assert json.dumps(b.sync()["assets"][name].get("history")) != after
    # recording again with an unchanged overlay HEAD is a no-op
    stable = json.dumps(b.sync()["assets"][name].get("history"))
    b.record_overlay_step(name, "edge → mask")
    assert json.dumps(b.sync()["assets"][name].get("history")) == stable


def test_mutations_on_unknown_asset_are_safe_noops(board):
    b, _ = board
    # every mutation must ignore a name it doesn't know, without raising
    for call in (
        lambda: b.place("ghost", x=1),
        lambda: b.bring_to_front("ghost"),
        lambda: b.select("ghost"),
        lambda: b.lock("ghost", True),
        lambda: b.add_dot("ghost", 1, 1),
        lambda: b.clear_dots("ghost"),
        lambda: b.set_outline("ghost", [[0, 0], [1, 1], [2, 2]]),
        lambda: b.push_overlay("ghost", _overlay(), "edge → mask"),
        lambda: b.record_overlay_step("ghost", "edge → mask"),
        lambda: b.undo("ghost"),
        lambda: b.redo("ghost"),
        lambda: b.goto("ghost", 0),
        lambda: b.reset_history("ghost"),
        lambda: b.record_pixel_edit("ghost", "x"),
    ):
        call()   # no exception = pass


def test_undo_redo_at_the_ends_are_noops(board):
    b, name = board
    b.sync()
    assert b.undo(name) is not None      # nothing to undo → state unchanged, no raise
    assert b.redo(name) is not None      # nothing to redo → likewise


def test_add_dot_ignores_missing_coords(board):
    b, name = board
    b.add_dot(name, None, None)          # x/y None → skipped
    assert b.sync()["assets"][name]["mask"]["dots"] == []


def test_undo_state_missing_asset(home):
    st = Board(home).undo_state("ghost")
    assert st == {"can_undo": False, "can_redo": False, "timeline": []}


def test_current_pixel_head_missing(home):
    assert _current_pixel_head(home, "ghost") == 0


def test_seed_from_manifest_reads_canvas(home, asset_png):
    Workspace.open_asset(asset_png, home, name="a")
    mpath = os.path.join(home, "a", "manifest.json")
    m = json.load(open(mpath))
    m["canvas"] = {"x": 7, "y": 8, "scale": 1.5}
    json.dump(m, open(mpath, "w"))
    seeded = _seed_from_manifest(home, "a")
    assert seeded == {"x": 7, "y": 8, "scale": 1.5}


def test_seed_from_manifest_absent(home):
    assert _seed_from_manifest(home, "ghost") is None
