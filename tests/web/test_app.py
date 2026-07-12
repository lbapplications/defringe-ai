"""web/app.py — the edit-screen routes, driven in-process via Starlette's TestClient
(no uvicorn, no sockets). build_app(home) is the factory split out for exactly this.

The window is **session-addressed** (Phase 2, C2): every action posts a `session` id, resolved
server-side to the asset; images are fetched at ``/img/{session}/{i}`` and ``/mask/{session}``.
The `client` fixture hands back the asset's session id alongside its display name."""

from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient

from defringe_ai import web
from defringe_ai.board import Board
from defringe_ai.web import app as webapp
from defringe_ai.workspace import Workspace


@pytest.fixture
def loaded_home(home, asset_png):
    """A home with one opened, board-synced asset named 'a'."""
    Workspace.open_asset(asset_png, home, name="a")
    Board(home).sync()
    return home, "a"


@pytest.fixture
def client(loaded_home):
    home, name = loaded_home
    sid = webapp._session_for(home, name)          # the window's session handle for the asset
    with TestClient(webapp.build_app(home)) as c:
        yield c, home, name, sid


def test_index_not_built(client, monkeypatch, tmp_path):
    c, home, _, _ = client
    monkeypatch.setattr(webapp, "DIST", str(tmp_path / "no-dist"))
    r = c.get("/")
    assert r.status_code == 503 and "not built" in r.text


def test_index_built(client, monkeypatch, tmp_path):
    c, home, _, _ = client
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>hi</h1>")
    monkeypatch.setattr(webapp, "DIST", str(dist))
    r = c.get("/")
    assert r.status_code == 200


def test_chains_lists_asset(client):
    c, home, name, _ = client
    r = c.get("/chains")
    assert r.status_code == 200 and name in r.text


def test_chains_empty(home):
    with TestClient(webapp.build_app(home)) as c:
        assert "No workspaces" in c.get("/chains").text


def test_image_ok_and_404(client):
    c, home, name, s = client
    assert c.get(f"/img/{s}/0").status_code == 200
    assert c.get(f"/img/{s}/99").status_code == 404          # bad index
    assert c.get("/img/ghost-session/0").status_code == 404   # no such session


def test_move_select_lock(client):
    c, home, name, s = client
    assert c.post("/api/move", json={"session": s, "x": 12, "y": 34}).json()["ok"]
    assert c.post("/api/select", json={"session": s}).json()["ok"]
    assert c.post("/api/lock", json={"session": s, "locked": True}).json()["ok"]
    assert Board(home).sync()["assets"][name]["locked"] is True


def test_dot_connect_isolate_flow(client):
    c, home, name, s = client
    for x, y in ([2, 2], [18, 2], [18, 18], [2, 18]):
        c.post("/api/dot", json={"session": s, "x": x, "y": y})
    # isolate refuses before connect
    assert c.post("/api/isolate", json={"session": s}).json()["ok"] is False
    assert c.post("/api/connect", json={"session": s}).json()["ok"]
    assert c.post("/api/isolate", json={"session": s}).json()["ok"]
    assert Workspace.locate(name, home).status()["chain"][-1] == "isolate"


def test_undo_redo_goto_reset(client):
    c, home, name, s = client
    c.post("/api/dot", json={"session": s, "x": 5, "y": 5})
    c.post("/api/dots/clear", json={"session": s})
    assert c.post("/api/undo", json={"session": s}).json()["ok"]
    assert c.post("/api/redo", json={"session": s}).json()["ok"]
    assert c.post("/api/history/goto", json={"session": s, "index": 0}).json()["ok"]
    assert c.post("/api/reset", json={"session": s}).json()["ok"]
    m = Board(home).sync()["assets"][name]["mask"]
    assert m["dots"] == []


def test_reset_unknown_session_degrades(client):
    """A stale/unknown session must NOT 500 — it degrades like the other routes (the finding-#1
    regression: reset was the lone route that raised on an unresolved session)."""
    c, home, name, _ = client
    r = c.post("/api/reset", json={"session": "ghost-session"})
    assert r.status_code == 200 and r.json()["ok"] is False


def test_window_edit_advances_session_cursor(client):
    """C5 — the window's edits (not just the MCP tools') advance the session cursor, so an agent
    sharing the session with the human sees an up-to-date ``state_id``/``mask_id`` after a window
    derive/undo. This was the half-kept-C5 gap: the routes resolved the session but never advanced
    it. A ghost session on a mutating route must still no-op cleanly (the ``not name`` guard)."""
    from defringe_ai.sessions import Sessions

    c, home, name, s = client
    sess = Sessions(home)
    assert sess.get(s)["mask_id"] is None                      # no overlay yet → no mask cursor
    c.post("/api/derive", json={"session": s, "op": "edge", "lo": 40, "hi": 120})
    assert sess.get(s)["mask_id"] == "mask_0.png"              # derive pushed an overlay → cursor moved
    c.post("/api/undo", json={"session": s})
    assert sess.get(s)["mask_id"] is None                      # undo walked the overlay head back → cursor followed
    assert c.post("/api/undo", json={"session": "ghost-session"}).json()["ok"]  # unknown session: no crash


def test_build_state_and_sig_direct(loaded_home):
    home, name = loaded_home
    state = webapp.build_state(home)
    assert state and state[0]["name"] == name
    assert state[0]["session"]                                          # every asset carries a session
    assert state[0]["edge"] is False and state[0]["edge_rev"] == ""     # no overlay yet
    assert isinstance(webapp._sig(state), str)


def test_mask_edge_route_and_state(client):
    c, home, name, s = client
    assert c.get(f"/mask/{s}").status_code == 404                       # no overlay yet
    from defringe_ai import imageops as ops
    img = Workspace.locate(name, home).current_array()
    ov = ops.Transform.matrix_sweep(ops.Transform.edge_detect(img))
    Board(home).push_overlay(name, ov, "edge → mask")
    assert c.get(f"/mask/{s}").status_code == 200
    assert c.get("/mask/ghost-session").status_code == 404
    st = next(a for a in webapp.build_state(home) if a["name"] == name)
    assert st["edge"] is True and st["edge_rev"] != ""
    rev0 = st["edge_rev"]
    Board(home).push_overlay(name, ov, "simplify_contour")
    st = next(a for a in webapp.build_state(home) if a["name"] == name)
    assert st["edge_rev"] != rev0
    Board(home).undo(name)
    st = next(a for a in webapp.build_state(home) if a["name"] == name)
    assert st["edge_rev"] == rev0


def test_derive_edge_close_bridge_buttons(client):
    from defringe_ai import imageops as ops

    c, home, name, s = client
    assert c.post("/api/derive", json={"session": s, "op": "edge", "lo": 40, "hi": 120}).json()["ok"]
    st = next(a for a in webapp.build_state(home) if a["name"] == name)
    assert st["edge"] is True
    ov = ops.Io.load(Workspace.locate(name, home).overlay_path())
    assert ov[..., 3].min() == 0 and ov[..., 3].max() == 255
    assert c.post("/api/derive", json={"session": s, "op": "close", "radius": 3}).json()["ok"]
    assert c.post("/api/derive", json={"session": s, "op": "bridge", "max_link": 60}).json()["ok"]
    labels = [x["label"] for x in Board(home).sync()["assets"][name]["history"]["actions"]]
    assert "edge → mask" in labels and "close" in labels and "bridge" in labels


def test_derive_keep_largest_drops_noise(client):
    from defringe_ai import imageops as ops

    c, home, name, s = client
    c.post("/api/derive", json={"session": s, "op": "edge", "lo": 40, "hi": 120})
    before = ops.Io.load(Workspace.locate(name, home).overlay_path())
    assert c.post("/api/derive", json={"session": s, "op": "keep", "keep": 1}).json()["ok"]
    after = ops.Io.load(Workspace.locate(name, home).overlay_path())
    assert (after[..., 3] > 0).sum() <= (before[..., 3] > 0).sum()
    labels = [x["label"] for x in Board(home).sync()["assets"][name]["history"]["actions"]]
    assert "keep largest" in labels


def test_derive_close_before_edge_errs(client):
    c, home, name, s = client
    r = c.post("/api/derive", json={"session": s, "op": "close"}).json()
    assert r["ok"] is False and "Edge first" in r["error"]


def test_derive_unknown_op_and_bad_asset(client):
    c, home, name, s = client
    c.post("/api/derive", json={"session": s, "op": "edge"})
    assert c.post("/api/derive", json={"session": s, "op": "zzz"}).json()["ok"] is False
    assert c.post("/api/derive", json={"session": "ghost-session", "op": "edge"}).json()["ok"] is False


def test_web_package_reexport():
    assert web is not None
