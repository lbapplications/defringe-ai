"""Projection — the only irreversible external writes (C7 live projection, C10 merge/restore).

Every test mounts a real (tmp) asset so the 'user's real file' is a genuine path we can read
back, and drives the engine directly — no server, no sockets (harness_driver/testing.md)."""

from __future__ import annotations

import filecmp
import os

import numpy as np
import pytest

from defringe_ai.projection import Projection
from defringe_ai.registry import Registry
from defringe_ai.workspace import Workspace


def _mount(home, asset_png):
    """Mount an asset → (name, pid, aid, ws) — the pieces a Projection needs."""
    ws = Workspace.open_asset(asset_png, home)
    name = ws._read()["name"]
    pid, aid = Registry(home).locate(name)
    return name, pid, aid, ws


def _edit(ws, tag="zero"):
    """Apply a pixel-changing op so HEAD differs from the base (a fresh all-zero image)."""
    ws.apply(tag, lambda a: np.zeros_like(a), {})


# --- live projection (C7) --------------------------------------------------

def test_project_mirrors_head_onto_real_file(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    _edit(ws)
    assert Projection(home, pid, aid).project(ws) is True
    assert filecmp.cmp(ws.current_path(), asset_png, shallow=False)   # real file == HEAD


def test_bk_sidecar_is_write_once(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    proj = Projection(home, pid, aid)
    original = open(asset_png, "rb").read()
    _edit(ws, "one")
    proj.project(ws)
    assert os.path.exists(proj.bk)
    assert open(proj.bk, "rb").read() == original          # .bk captured the pristine original
    # a second edit + projection must NOT overwrite the sidecar (write-if-absent)
    _edit(ws, "two")
    proj.project(ws)
    assert open(proj.bk, "rb").read() == original


def test_project_skips_when_head_already_on_disk(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    proj = Projection(home, pid, aid)
    _edit(ws)
    assert proj.project(ws) is True
    assert proj.project(ws) is False                       # nothing changed → no rewrite (mask-only case)


def test_project_noop_when_real_file_gone(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    _edit(ws)
    os.remove(asset_png)
    assert Projection(home, pid, aid).project(ws) is False  # can't project onto a vanished file


# --- merge / restore (C10) -------------------------------------------------

def test_merge_archives_the_approved_state_and_collapses(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    proj = Projection(home, pid, aid)
    _edit(ws)
    approved = open(ws.current_path(), "rb").read()        # the state being approved (HEAD)
    res = proj.merge(ws)
    assert res["commit"] == 0 and res["commits"] == [0]
    assert filecmp.cmp(ws.current_path(), asset_png, shallow=False)  # approved state on the real file
    assert ws.head() == 0 and ws.status()["steps"] == 1             # fine chain collapsed
    archived = os.path.join(proj.backup_dir, "asset_0.png")
    assert open(archived, "rb").read() == approved                  # the APPROVED state IS the commit


def test_merge_ledger_grows_per_commit(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    proj = Projection(home, pid, aid)
    _edit(ws, "a"); proj.merge(ws)
    _edit(ws, "b"); res = proj.merge(ws)
    assert res["commit"] == 1 and res["commits"] == [0, 1]


def test_restore_returns_an_approved_commit_without_losing_the_later_one(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    proj = Projection(home, pid, aid)
    _edit(ws, "a"); proj.merge(ws)                          # commit 0 = approved state A
    approved_a = open(os.path.join(proj.backup_dir, "asset_0.png"), "rb").read()
    _edit(ws, "b"); proj.merge(ws)                          # commit 1 = approved state B (real file = B)
    res = proj.restore(ws, 0)
    assert res["restored"] == 0
    assert open(asset_png, "rb").read() == approved_a       # real file back to approved state A
    assert ws.head() == 0 and ws.status()["chain"] == ["restored"]
    assert proj.commits() == [0, 1]                         # B not lost — still restorable


def test_merge_refuses_mid_edit_session(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    ws.begin_edit("wip"); ws.apply("z", lambda a: np.zeros_like(a), {})
    with pytest.raises(ValueError, match="edit session"):
        Projection(home, pid, aid).merge(ws)


def test_merge_and_restore_refuse_without_a_real_file(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    _edit(ws)
    os.remove(asset_png)                                    # user's file gone (or a legacy dir-keyed asset)
    with pytest.raises(ValueError, match="no real file"):
        Projection(home, pid, aid).merge(ws)


def test_cancel_after_merge_does_not_crash(home, asset_png):
    """Merge collapses the chain; a later edit-session cancel must clamp HEAD, not IndexError."""
    _, pid, aid, ws = _mount(home, asset_png)
    _edit(ws); Projection(home, pid, aid).merge(ws)         # chain collapsed to a lone base
    ws.begin_edit("x"); ws.apply("z", lambda a: np.zeros_like(a), {})
    ws.cancel_edit()
    assert ws.head() == 0 and ws.status()["steps"] == 1     # landed safely on the base


def test_restore_unknown_commit_raises(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    with pytest.raises(ValueError, match="no approved commit"):
        Projection(home, pid, aid).restore(ws, 9)


def test_restore_refuses_without_a_real_file(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    proj = Projection(home, pid, aid)
    _edit(ws); proj.merge(ws)                              # commit 0 exists
    os.remove(asset_png)
    with pytest.raises(ValueError, match="no real file"):
        proj.restore(ws, 0)


def test_commits_ignores_stray_files(home, asset_png):
    _, pid, aid, ws = _mount(home, asset_png)
    proj = Projection(home, pid, aid)
    _edit(ws); proj.merge(ws)
    os.makedirs(proj.backup_dir, exist_ok=True)
    open(os.path.join(proj.backup_dir, "asset_x.png"), "w").close()   # non-numeric → ignored
    open(os.path.join(proj.backup_dir, "notes.txt"), "w").close()
    assert proj.commits() == [0]
