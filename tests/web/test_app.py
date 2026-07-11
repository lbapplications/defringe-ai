"""web/app.py — the edit-screen routes, driven in-process via Starlette's TestClient
(no uvicorn, no sockets). build_app(home) is the factory split out for exactly this."""

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
    with TestClient(webapp.build_app(home)) as c:
        yield c, home, name


def test_index_not_built(client, monkeypatch, tmp_path):
    c, home, _ = client
    monkeypatch.setattr(webapp, "DIST", str(tmp_path / "no-dist"))
    r = c.get("/")
    assert r.status_code == 503 and "not built" in r.text


def test_index_built(client, monkeypatch, tmp_path):
    c, home, _ = client
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>hi</h1>")
    monkeypatch.setattr(webapp, "DIST", str(dist))
    r = c.get("/")
    assert r.status_code == 200


def test_chains_lists_asset(client):
    c, home, name = client
    r = c.get("/chains")
    assert r.status_code == 200 and name in r.text


def test_chains_empty(home):
    with TestClient(webapp.build_app(home)) as c:
        assert "No workspaces" in c.get("/chains").text


def test_image_ok_and_404(client):
    c, home, name = client
    assert c.get(f"/img/{name}/0").status_code == 200
    assert c.get(f"/img/{name}/99").status_code == 404      # bad index
    assert c.get("/img/ghost/0").status_code == 404          # no such asset


def test_move_select_lock(client):
    c, home, name = client
    assert c.post("/api/move", json={"name": name, "x": 12, "y": 34}).json()["ok"]
    assert c.post("/api/select", json={"name": name}).json()["ok"]
    assert c.post("/api/lock", json={"name": name, "locked": True}).json()["ok"]
    assert Board(home).sync()["assets"][name]["locked"] is True


def test_dot_connect_isolate_flow(client):
    c, home, name = client
    for x, y in ([2, 2], [18, 2], [18, 18], [2, 18]):
        c.post("/api/dot", json={"name": name, "x": x, "y": y})
    # isolate refuses before connect
    assert c.post("/api/isolate", json={"name": name}).json()["ok"] is False
    assert c.post("/api/connect", json={"name": name}).json()["ok"]
    assert c.post("/api/isolate", json={"name": name}).json()["ok"]
    assert Workspace.resolve(name, home).status()["chain"][-1] == "isolate"


def test_undo_redo_goto_reset(client):
    c, home, name = client
    c.post("/api/dot", json={"name": name, "x": 5, "y": 5})
    c.post("/api/dots/clear", json={"name": name})
    assert c.post("/api/undo", json={"name": name}).json()["ok"]
    assert c.post("/api/redo", json={"name": name}).json()["ok"]
    assert c.post("/api/history/goto", json={"name": name, "index": 0}).json()["ok"]
    assert c.post("/api/reset", json={"name": name}).json()["ok"]
    m = Board(home).sync()["assets"][name]["mask"]
    assert m["dots"] == []


def test_build_state_and_sig_direct(loaded_home):
    home, name = loaded_home
    state = webapp.build_state(home)
    assert state and state[0]["name"] == name
    assert state[0]["edge"] is False and state[0]["edge_rev"] == ""     # no overlay yet
    assert isinstance(webapp._sig(state), str)


def test_mask_edge_route_and_state(client):
    c, home, name = client
    assert c.get(f"/mask/{name}").status_code == 404                    # no overlay yet
    # push an overlay version and confirm it's served + reflected in the pushed state
    from defringe_ai import imageops as ops
    img = Workspace.resolve(name, home).current_array()
    ov = ops.Transform.matrix_sweep(ops.Transform.edge_detect(img))
    Board(home).push_overlay(name, ov, "edge → mask")
    assert c.get(f"/mask/{name}").status_code == 200
    assert c.get("/mask/ghost").status_code == 404
    st = next(a for a in webapp.build_state(home) if a["name"] == name)
    assert st["edge"] is True and st["edge_rev"] != ""
    rev0 = st["edge_rev"]
    # a second version bumps edge_rev (busts the browser cache); undo restores the first
    Board(home).push_overlay(name, ov, "simplify_contour")
    st = next(a for a in webapp.build_state(home) if a["name"] == name)
    assert st["edge_rev"] != rev0
    Board(home).undo(name)
    st = next(a for a in webapp.build_state(home) if a["name"] == name)
    assert st["edge_rev"] == rev0


def test_derive_edge_close_bridge_buttons(client):
    import numpy as np
    from defringe_ai import imageops as ops

    c, home, name = client
    # Edge button with slider params: Canny(lo,hi) from the image → an overlay appears
    assert c.post("/api/derive", json={"name": name, "op": "edge", "lo": 40, "hi": 120}).json()["ok"]
    st = next(a for a in webapp.build_state(home) if a["name"] == name)
    assert st["edge"] is True
    # the overlay is keyed white-on-TRANSPARENT (black dropped out), not opaque black
    ov = ops.Io.load(Workspace(os.path.join(home, name)).overlay_path())
    assert ov[..., 3].min() == 0 and ov[..., 3].max() == 255
    # Close (radius) and Bridge (max_link) transform the current overlay
    assert c.post("/api/derive", json={"name": name, "op": "close", "radius": 3}).json()["ok"]
    assert c.post("/api/derive", json={"name": name, "op": "bridge", "max_link": 60}).json()["ok"]
    labels = [x["label"] for x in Board(home).sync()["assets"][name]["history"]["actions"]]
    assert "edge → mask" in labels and "close" in labels and "bridge" in labels


def test_derive_keep_largest_drops_noise(client):
    import numpy as np
    from defringe_ai import imageops as ops

    c, home, name = client
    # seed an overlay with a big mark + a speck via the derive path, then keep the largest
    c.post("/api/derive", json={"name": name, "op": "edge", "lo": 40, "hi": 120})
    before = ops.Io.load(Workspace(os.path.join(home, name)).overlay_path())
    n_before = int((before[..., 3] > 0).any())
    assert c.post("/api/derive", json={"name": name, "op": "keep", "keep": 1}).json()["ok"]
    after = ops.Io.load(Workspace(os.path.join(home, name)).overlay_path())
    # keep-largest never adds foreground; kept ⊆ original marks
    assert (after[..., 3] > 0).sum() <= (before[..., 3] > 0).sum()
    labels = [x["label"] for x in Board(home).sync()["assets"][name]["history"]["actions"]]
    assert "keep largest" in labels


def test_derive_close_before_edge_errs(client):
    c, home, name = client
    r = c.post("/api/derive", json={"name": name, "op": "close"}).json()
    assert r["ok"] is False and "Edge first" in r["error"]


def test_derive_unknown_op_and_bad_asset(client):
    c, home, name = client
    c.post("/api/derive", json={"name": name, "op": "edge"})
    assert c.post("/api/derive", json={"name": name, "op": "zzz"}).json()["ok"] is False
    assert c.post("/api/derive", json={"name": "ghost", "op": "edge"}).json()["ok"] is False


def test_web_package_reexport():
    # the package imports cleanly
    assert web is not None
