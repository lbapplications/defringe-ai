"""server.py — the MCP tools + the CLI, both over an isolated tmp HOME (the `srv` fixture
points server.HOME at tmp). Tools are plain functions under the official-SDK @mcp.tool(),
so we call them directly.

The tools are **session-addressed** (Phase 2, C2): open_asset returns a `session` id and every
other tool names its target with it — there is no ambient "current asset". The `app` fixture
opens one asset and hands back ``(srv, session)``. The CLI half stays name-addressed (it drives
the engine directly — the local human debug loop, not one of the addressed surfaces)."""

from __future__ import annotations

import os

import pytest

from defringe_ai.workspace import Workspace


@pytest.fixture
def app(srv, asset_png):
    """server module + the session of one opened asset → (srv, session)."""
    st = srv.open_asset(asset_png, name="shark")
    return srv, st["session"]


# --- discovery / workspace listing -----------------------------------------

def test_open_asset_returns_a_session(app):
    srv, s = app
    assert isinstance(s, str) and s                          # open_asset hands back a session id
    assert srv.status(session=s)["workspace"] == "shark"


def test_taxonomy_and_list(app):
    srv, s = app
    tax = srv.taxonomy()
    assert "edge_detect" in tax["categories"]["derive"]
    assert set(srv.GATED) == set(tax["gated"])
    ls = srv.list_workspaces()
    assert "shark" in ls["workspaces"]
    assert ls["sessions"]["shark"] == s                      # the label → session reverse map


def test_list_shapes(app):
    srv, _ = app
    s = srv.list_shapes()
    assert "circle" in s["shapes"] and "center" in s["anchors"]


def test_tool_without_a_session_raises(srv):
    """No ambient current asset: a tool called with a blank session is a guided error."""
    with pytest.raises(ValueError, match="needs a session"):
        srv.status()


# --- session gate ----------------------------------------------------------

def test_gate_refuses_then_allows(app):
    srv, s = app
    with pytest.raises(ValueError, match="gated"):
        srv.mark([[5, 5]], session=s)                        # session known, but no edit session
    srv.edit("draw a dot", session=s)
    st = srv.mark([[5, 5]], radius=2, session=s)
    assert st["marked"] == 1
    srv.commit(session=s)
    assert Workspace.active(srv.HOME).status()["head"] == 1


def test_cancel_restores(app):
    srv, s = app
    srv.edit("scratch", session=s)
    srv.mark([[5, 5]], session=s)
    srv.cancel(session=s)
    assert Workspace.active(srv.HOME).status()["head"] == 0


def test_transform_tools_through_the_gate(app):
    """Each gated transform MCP wrapper, once, inside a session."""
    srv, s = app
    srv.edit("run the transforms", session=s)
    assert srv.key_background(bg="white", session=s)["chain"][-1] == "key_background"
    assert srv.defringe(erode_px=1, session=s)["chain"][-1] == "defringe"
    assert srv.trim_alpha(session=s)["chain"][-1] == "trim_alpha"
    assert srv.crop(0, 0, 10, 10, session=s)["chain"][-1] == "crop"
    assert srv.upscale(factor=1.5, session=s)["chain"][-1] == "upscale"
    assert srv.silhouette_mask(session=s)["chain"][-1] == "silhouette_mask"
    ln = srv.draw_line(0, 0, 9, 9, color="red", session=s)
    assert ln["line"]["to"] == [9, 9]
    srv.commit(session=s)


def test_draw_shape_gate_and_geometry(app):
    srv, s = app
    with pytest.raises(ValueError):
        srv.draw_shape(session=s)                            # gated
    srv.edit("shape it", session=s)
    st = srv.draw_shape(shape="circle", x=10, y=10, width=6, height=6, color="red", session=s)
    assert st["drew"]["shape"] == "circle"
    assert "clipped" in st


def test_session_cursor_advances_on_edits(app):
    """The server owns the cursor (C5): committing a pixel edit advances the session's state_id."""
    from defringe_ai.sessions import Sessions

    srv, s = app
    assert Sessions(srv.HOME).get(s)["state_id"] == "state_0"
    srv.edit("mark it", session=s)
    srv.mark([[5, 5]], session=s)
    srv.commit(session=s)
    assert Sessions(srv.HOME).get(s)["state_id"] == "state_1"   # cursor followed the new HEAD


# --- derive: edge_detect + adaptive edge_detect_tune -----------------------

def test_edge_detect_makes_a_mask_overlay(app):
    from defringe_ai.board import Board

    srv, s = app
    st = srv.edge_detect(lo=50, hi=150, session=s)
    assert st["head"] == 0 and st["chain"] == ["open"]        # image untouched — original stays HEAD
    from defringe_ai.registry import Registry

    assert os.path.exists(os.path.join(
        Registry(srv.HOME).dir_by_name("shark"), "overlay", "0000-edge → mask.png"))
    a = Board(srv.HOME).sync()["assets"]["shark"]
    assert a["mask"]["edge"] is True and a["overlay_head"] == 0
    Board(srv.HOME).undo("shark")                            # image-level undo clears the overlay
    a = Board(srv.HOME).sync()["assets"]["shark"]
    assert a["mask"]["edge"] is False and a["overlay_head"] == -1


def test_edge_detect_no_session_raises(srv):
    with pytest.raises(ValueError):
        srv.edge_detect()                       # nothing open, no session


def test_edge_detect_tune_good_immediately(app):
    from defringe_ai.board import Board

    srv, s = app
    start = srv.edge_detect_tune(session=s)
    assert start.done is False and start.probe == 1
    done = srv.edge_detect_tune(verdict="good", session=s)
    assert done.done is True
    assert Workspace.active(srv.HOME).status()["head"] == 0          # image untouched
    assert Board(srv.HOME).sync()["assets"]["shark"]["mask"]["edge"] is True


def test_edge_detect_tune_two_more_converges(app):
    srv, s = app
    srv.edge_detect_tune(session=s)                      # start (probe 1)
    srv.edge_detect_tune(verdict="more", session=s)      # nos 1, probe 2
    res = srv.edge_detect_tune(verdict="more", session=s)  # nos 2 → commit
    assert res.done is True and res.nos == 2


def test_edge_detect_tune_reduce_caps_at_three_probes(app):
    srv, s = app
    srv.edge_detect_tune(session=s)                      # probe 1
    srv.edge_detect_tune(verdict="reduce", session=s)    # probe 2
    srv.edge_detect_tune(verdict="reduce", session=s)    # probe 3
    res = srv.edge_detect_tune(verdict="reduce", session=s)  # probe 4 > max → commit
    assert res.done is True


def test_edge_detect_tune_bad_verdict_raises(app):
    srv, s = app
    srv.edge_detect_tune(session=s)
    with pytest.raises(ValueError):
        srv.edge_detect_tune(verdict="banana", session=s)


def test_edge_detect_tune_no_session_raises(srv):
    with pytest.raises(ValueError):
        srv.edge_detect_tune()


# --- isolate flow ----------------------------------------------------------

def test_seed_connect_isolate(app):
    srv, s = app
    ms = srv.seed([[2, 2], [18, 2], [18, 18], [2, 18]], session=s)
    assert ms.dots == 4
    cm = srv.connect(session=s)
    assert cm.outline >= 3
    res = srv.isolate(session=s)
    assert res.chain[-1] == "isolate"
    img = Workspace.active(srv.HOME).current_array()
    assert img[0, 0, 3] == 0


def test_outline_traces_matte_then_isolate(app):
    from defringe_ai import imageops as ops

    srv, s = app
    # key the white ground → alpha now marks the dark square (the matte `outline` traces)
    Workspace.active(srv.HOME).apply("key_background", ops.Transform.key_background, {"bg": "white"})
    ms = srv.outline(epsilon=1.0, session=s)
    assert ms.dots == 0 and ms.outline >= 3        # boundary from pixels, no seeds placed
    b = srv.Board(srv.HOME).sync()
    assert b["assets"]["shark"]["mask"]["outline"]  # landed in the same slot connect fills
    res = srv.isolate(session=s)                     # cuts the traced polygon
    assert res.chain[-1] == "isolate"


def _wipe_alpha(img):
    img = img.copy()
    img[..., 3] = 0        # no opaque pixel → no contour to trace
    return img


def test_outline_without_matte_raises(app):
    srv, s = app
    Workspace.active(srv.HOME).apply("wipe_alpha", _wipe_alpha, {})
    with pytest.raises(ValueError):
        srv.outline(session=s)


def test_cutout_segments_subject(srv, tmp_path):
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(2)
    a = np.zeros((80, 80, 4), np.uint8)
    a[..., 3] = 255
    a[..., 2] = rng.integers(180, 220, (80, 80))
    a[26:54, 26:54, 0] = rng.integers(180, 220, (28, 28))
    a[26:54, 26:54, 2] = rng.integers(0, 40, (28, 28))
    p = tmp_path / "box.png"
    Image.fromarray(a, "RGBA").save(p)
    s = srv.open_asset(str(p), name="box")["session"]

    res = srv.cutout(rect=[22, 22, 36, 36], iterations=3, session=s)
    assert res.chain[-1] == "cutout"
    out = Workspace.active(srv.HOME).current_array()
    assert out[0, 0, 3] == 0            # outside the seed rect → transparent
    assert out[40, 40, 3] == 255        # subject centre kept
    srv.undo(session=s)
    assert Workspace.active(srv.HOME).current_array()[0, 0, 3] == 255


def test_cutout_auto_rect_from_frame(srv, tmp_path):
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(3)
    a = np.zeros((80, 80, 4), np.uint8)
    a[..., 3] = 255
    a[..., 2] = rng.integers(180, 220, (80, 80))
    a[20:60, 20:60, 0] = rng.integers(180, 220, (40, 40))
    a[20:60, 20:60, 2] = rng.integers(0, 40, (40, 40))
    p = tmp_path / "box2.png"
    Image.fromarray(a, "RGBA").save(p)
    s = srv.open_asset(str(p), name="box2")["session"]
    res = srv.cutout(session=s)         # no rect + no seeds → inset-frame seed box
    assert res.chain[-1] == "cutout"
    assert (Workspace.active(srv.HOME).current_array()[..., 3] > 0).any()


def test_isolate_without_outline_raises(app):
    srv, s = app
    with pytest.raises(ValueError):
        srv.isolate(session=s)


def test_clear_seeds(app):
    srv, s = app
    srv.seed([[2, 2], [18, 18]], session=s)
    ms = srv.clear_seeds(session=s)
    assert ms.dots == 0


# --- workspace controls ----------------------------------------------------

def test_status_collapse_move_select_export(app, tmp_path):
    srv, s = app
    assert srv.status(session=s)["workspace"] == "shark"
    srv.edge_detect(lo=50, hi=150, session=s)
    srv.collapse(session=s)
    assert srv.status(session=s)["chain"] == ["collapsed"]
    mv = srv.move(30, 40, scale=1.5, session=s)
    assert mv["placement"]["x"] == 30
    sel = srv.select(session=s)
    assert sel["selected"] == "shark"
    dest = str(tmp_path / "out.png")
    assert srv.export(dest, session=s)["exported"] == dest


def test_redo_after_undo(app):
    srv, s = app
    srv.edit("mark it", session=s); srv.mark([[5, 5]], session=s); srv.commit(session=s)
    srv.undo(session=s)
    srv.redo(session=s)
    assert srv.status(session=s)["head"] == 1


def test_reopen_under_new_name_keeps_board_state(srv, asset_png):
    """Resume-under-a-new-name renames the registry label; the board arrangement + mask must
    follow the rename, and the SAME session resumes (identity, not label, keys it)."""
    s1 = srv.open_asset(asset_png, name="a")["session"]
    srv.move(500, 300, session=s1)                          # place it
    srv.seed([[5, 5], [15, 15]], session=s1)               # and annotate it
    s2 = srv.open_asset(asset_png, name="hero")["session"]  # same path → resume, rename a→hero
    assert s2 == s1                                         # one handle per asset (C6), across a rename
    assert srv.status(session=s1)["workspace"] == "hero"
    ls = srv.list_workspaces()["workspaces"]
    assert ls == ["hero"] and "a" not in ls                # exactly one asset, under the new label
    from defringe_ai.board import Board
    a = Board(srv.HOME).sync()["assets"]["hero"]
    assert a["x"] == 500 and a["y"] == 300                  # placement carried over
    assert a["mask"]["dots"] == [[5, 5], [15, 15]]          # mask carried over, not wiped


# --- helpers ---------------------------------------------------------------

def test_free_port_and_print(srv, capsys):
    p = srv._free_port(0)          # 0 asks the OS for any free port; bindable
    assert isinstance(p, int)
    srv._print({"workspace": "w", "head": 0, "steps": 1,
                "chain": ["open"], "current": "/x.png", "width": 10, "height": 10})
    assert "[w]" in capsys.readouterr().out


def test_free_port_exhausted(srv, monkeypatch):
    import socket as _socket

    class Bound:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def setsockopt(self, *a): pass
        def bind(self, *a): raise OSError("taken")
    monkeypatch.setattr(_socket, "socket", lambda *a, **k: Bound())
    with pytest.raises(RuntimeError):
        srv._free_port(5000)


# --- CLI (main) — name-addressed (the local human debug loop, C1) -----------

def _run(srv, monkeypatch, argv):
    monkeypatch.setattr("sys.argv", ["defringe-ai", *argv])
    srv.main()


def test_cli_open_status_ls(srv, monkeypatch, asset_png, capsys):
    _run(srv, monkeypatch, ["open", asset_png, "--name", "a"])
    _run(srv, monkeypatch, ["status", "a"])
    _run(srv, monkeypatch, ["ls"])
    out = capsys.readouterr().out
    assert "[a]" in out and "a" in out


def test_cli_edit_mark_commit_undo_redo(srv, monkeypatch, asset_png, capsys):
    _run(srv, monkeypatch, ["open", asset_png, "--name", "a"])
    _run(srv, monkeypatch, ["edit", "mark it", "a"])
    _run(srv, monkeypatch, ["mark", "5,5 10,10", "a"])
    _run(srv, monkeypatch, ["commit", "a"])
    _run(srv, monkeypatch, ["undo", "a"])
    _run(srv, monkeypatch, ["redo", "a"])
    assert Workspace.resolve("a", srv.HOME).status()["head"] == 1


def test_cli_edit_cancel(srv, monkeypatch, asset_png, capsys):
    _run(srv, monkeypatch, ["open", asset_png, "--name", "a"])
    _run(srv, monkeypatch, ["edit", "scratch", "a"])
    _run(srv, monkeypatch, ["mark", "5,5", "a"])
    _run(srv, monkeypatch, ["cancel", "a"])
    assert "cancelled" in capsys.readouterr().out
    assert Workspace.resolve("a", srv.HOME).status()["head"] == 0


def test_cli_shape_and_line_and_edge_detect(srv, monkeypatch, asset_png):
    _run(srv, monkeypatch, ["open", asset_png, "--name", "a"])
    _run(srv, monkeypatch, ["edit", "draw", "a"])
    _run(srv, monkeypatch, ["shape", "circle", "a", "--x", "10", "--y", "10", "--width", "6"])
    _run(srv, monkeypatch, ["line", "0", "0", "9", "9", "a"])
    _run(srv, monkeypatch, ["commit", "a"])
    _run(srv, monkeypatch, ["edge_detect", "a"])
    from defringe_ai.board import Board
    assert Board(srv.HOME).sync()["assets"]["a"]["mask"]["edge"] is True   # overlay, not a pixel step
    assert Workspace.resolve("a", srv.HOME).status()["chain"][-1] == "draw_line"


def test_cli_collapse_export(srv, monkeypatch, asset_png, tmp_path):
    _run(srv, monkeypatch, ["open", asset_png, "--name", "a"])
    _run(srv, monkeypatch, ["collapse", "a"])
    dest = str(tmp_path / "cli_out.png")
    _run(srv, monkeypatch, ["export", dest, "a"])
    assert os.path.exists(dest)


def test_cli_gated_refusals(srv, monkeypatch, asset_png, capsys):
    _run(srv, monkeypatch, ["open", asset_png, "--name", "a"])
    _run(srv, monkeypatch, ["shape", "circle", "a"])       # no session → REFUSED
    _run(srv, monkeypatch, ["mark", "5,5", "a"])           # no session → REFUSED
    _run(srv, monkeypatch, ["line", "0", "0", "5", "5", "a"])
    out = capsys.readouterr().out
    assert out.count("REFUSED") == 3


def test_cli_edge_detect_no_workspace_refused(srv, monkeypatch, capsys):
    _run(srv, monkeypatch, ["edge_detect"])                # nothing open
    assert "REFUSED" in capsys.readouterr().out


def test_cli_serve_dispatch(srv, monkeypatch):
    calls = {}
    monkeypatch.setattr(srv.mcp, "run", lambda *a, **k: calls.setdefault("mcp", True))
    monkeypatch.setattr("defringe_ai.web.app.serve_preview", lambda *a, **k: None)
    monkeypatch.setattr(srv, "_free_port", lambda *a, **k: 40000)
    _run(srv, monkeypatch, ["serve", "--http", "--preview"])
    assert calls.get("mcp") is True


def test_cli_serve_stdio_default(srv, monkeypatch):
    calls = {}
    monkeypatch.setattr(srv.mcp, "run", lambda *a, **k: calls.setdefault("stdio", True))
    _run(srv, monkeypatch, [])                             # no subcommand → stdio serve
    assert calls.get("stdio") is True
