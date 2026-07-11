"""server.py — the MCP tools + the CLI, both over an isolated tmp HOME (the `srv` fixture
points server.HOME at tmp). Tools are plain functions under the official-SDK @mcp.tool(),
so we call them directly."""

from __future__ import annotations

import os

import pytest

from defringe_ai.workspace import Workspace


@pytest.fixture
def app(srv, asset_png):
    """server module with one asset opened + active."""
    srv.open_asset(asset_png, name="shark")
    return srv


# --- discovery / workspace listing -----------------------------------------

def test_taxonomy_and_list(app):
    tax = app.taxonomy()
    assert "edge_detect" in tax["categories"]["derive"]
    assert set(app.GATED) == set(tax["gated"])
    ls = app.list_workspaces()
    assert ls["active"] == "shark" and "shark" in ls["workspaces"]


def test_list_shapes(app):
    s = app.list_shapes()
    assert "circle" in s["shapes"] and "center" in s["anchors"]


# --- session gate ----------------------------------------------------------

def test_gate_refuses_then_allows(app):
    with pytest.raises(ValueError):
        app.mark([[5, 5]])                     # gated: no session
    app.edit("draw a dot")
    st = app.mark([[5, 5]], radius=2)
    assert st["marked"] == 1
    app.commit()
    assert Workspace.active(app.HOME).status()["head"] == 1


def test_cancel_restores(app):
    app.edit("scratch")
    app.mark([[5, 5]])
    app.cancel()
    assert Workspace.active(app.HOME).status()["head"] == 0


def test_transform_tools_through_the_gate(app):
    """Each gated transform MCP wrapper, once, inside a session."""
    app.edit("run the transforms")
    assert app.key_background(bg="white")["chain"][-1] == "key_background"
    assert app.defringe(erode_px=1)["chain"][-1] == "defringe"
    assert app.trim_alpha()["chain"][-1] == "trim_alpha"
    assert app.crop(0, 0, 10, 10)["chain"][-1] == "crop"
    assert app.upscale(factor=1.5)["chain"][-1] == "upscale"
    assert app.silhouette_mask()["chain"][-1] == "silhouette_mask"
    ln = app.draw_line(0, 0, 9, 9, color="red")
    assert ln["line"]["to"] == [9, 9]
    app.commit()


def test_draw_shape_gate_and_geometry(app):
    with pytest.raises(ValueError):
        app.draw_shape()                        # gated
    app.edit("shape it")
    st = app.draw_shape(shape="circle", x=10, y=10, width=6, height=6, color="red")
    assert st["drew"]["shape"] == "circle"
    assert "clipped" in st


# --- derive: edge_detect + adaptive edge_detect_tune -----------------------

def test_edge_detect_in_place_and_undoable(app):
    st = app.edge_detect(lo=50, hi=150)
    assert st["chain"][-1] == "edge_detect" and st["head"] == 1
    app.undo()                                  # restores the original
    assert Workspace.active(app.HOME).status()["head"] == 0


def test_edge_detect_no_workspace_raises(srv):
    with pytest.raises(ValueError):
        srv.edge_detect()                       # nothing open


def test_edge_detect_tune_good_immediately(app):
    start = app.edge_detect_tune()
    assert start.done is False and start.probe == 1
    done = app.edge_detect_tune(verdict="good")
    assert done.done is True
    assert Workspace.active(app.HOME).status()["chain"][-1] == "edge_detect"


def test_edge_detect_tune_two_more_converges(app):
    app.edge_detect_tune()                      # start (probe 1)
    app.edge_detect_tune(verdict="more")        # nos 1, probe 2
    res = app.edge_detect_tune(verdict="more")  # nos 2 → commit
    assert res.done is True and res.nos == 2


def test_edge_detect_tune_reduce_caps_at_three_probes(app):
    app.edge_detect_tune()                      # probe 1
    app.edge_detect_tune(verdict="reduce")      # probe 2
    app.edge_detect_tune(verdict="reduce")      # probe 3
    res = app.edge_detect_tune(verdict="reduce")  # probe 4 > max → commit
    assert res.done is True


def test_edge_detect_tune_bad_verdict_raises(app):
    app.edge_detect_tune()
    with pytest.raises(ValueError):
        app.edge_detect_tune(verdict="banana")


def test_edge_detect_tune_no_workspace_raises(srv):
    with pytest.raises(ValueError):
        srv.edge_detect_tune()


# --- isolate flow ----------------------------------------------------------

def test_seed_connect_isolate(app):
    ms = app.seed([[2, 2], [18, 2], [18, 18], [2, 18]])
    assert ms.dots == 4
    cm = app.connect()
    assert cm.outline >= 3
    res = app.isolate()
    assert res.chain[-1] == "isolate"
    # cutout: outside the polygon is transparent
    img = Workspace.active(app.HOME).current_array()
    assert img[0, 0, 3] == 0


def test_isolate_without_outline_raises(app):
    with pytest.raises(ValueError):
        app.isolate()


def test_clear_seeds(app):
    app.seed([[2, 2], [18, 18]])
    ms = app.clear_seeds()
    assert ms.dots == 0


# --- workspace controls ----------------------------------------------------

def test_status_collapse_move_select_export(app, tmp_path):
    assert app.status()["workspace"] == "shark"
    app.edge_detect(lo=50, hi=150)
    app.collapse()
    assert app.status()["chain"] == ["collapsed"]
    mv = app.move(30, 40, scale=1.5)
    assert mv["placement"]["x"] == 30
    sel = app.select()
    assert sel["selected"] == "shark"
    dest = str(tmp_path / "out.png")
    assert app.export(dest)["exported"] == dest


def test_redo_after_undo(app):
    app.edge_detect(lo=50, hi=150)
    app.undo()
    app.redo()
    assert app.status()["head"] == 1


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


# --- CLI (main) ------------------------------------------------------------

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
    assert Workspace.resolve("a", srv.HOME).status()["chain"][-1] == "edge_detect"


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
