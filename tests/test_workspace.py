"""workspace.py — the on-disk asset + reversible edit chain + edit-session gate."""

from __future__ import annotations

import numpy as np
import pytest

from defringe_ai import imageops as ops
from defringe_ai.workspace import Workspace, _get_active


def _double(img):
    return img[::1]  # identity-ish; a trivial op that still snapshots


def test_open_asset_seeds_step_zero(home, asset_png):
    ws = Workspace.open_asset(asset_png, home)
    st = ws.status()
    assert st["head"] == 0 and st["steps"] == 1
    assert st["chain"] == ["open"]
    assert st["width"] == 20 and st["height"] == 20


def test_open_asset_missing_source_raises(home):
    with pytest.raises(ValueError):
        Workspace.open_asset("/no/such/file.png", home)


def test_open_asset_reopen_is_clean(home, asset_png):
    Workspace.open_asset(asset_png, home, name="dup")
    ws = Workspace.open_asset(asset_png, home, name="dup")   # same path → resume the one asset
    assert ws.status()["steps"] == 1


def test_active_and_resolve(home, asset_png, asset_png2):
    Workspace.open_asset(asset_png, home, name="one")
    assert _get_active(home) == "one"
    assert Workspace.active(home).status()["workspace"] == "one"
    Workspace.open_asset(asset_png2, home, name="two")
    # resolve by name switches active
    assert Workspace.resolve("one", home).status()["workspace"] == "one"
    assert _get_active(home) == "one"
    # blank resolves to active
    assert Workspace.resolve("", home).status()["workspace"] == "one"


def test_active_with_none_raises(home):
    with pytest.raises(ValueError):
        Workspace.active(home)


def test_resolve_unknown_raises(home):
    with pytest.raises(ValueError):
        Workspace.resolve("ghost", home)


def test_locate_adopts_legacy_flat_dir(home, asset_png):
    """A pre-identity flat workspace resolves via locate's adopt-on-miss (no board sync needed)."""
    import os
    import shutil

    Workspace.open_asset(asset_png, home, name="legacy")     # build a real workspace
    from defringe_ai.registry import Registry

    real = Registry(home).dir_by_name("legacy")
    flat = os.path.join(home, "legacy")
    shutil.copytree(real, flat)                              # replicate it as an old flat dir
    os.remove(os.path.join(home, "projects.json"))          # wipe the registry → only the flat dir remains
    assert Workspace.locate("legacy", home).status()["steps"] == 1


def test_list_all(home, asset_png, asset_png2):
    assert Workspace.list_all(home) == []
    Workspace.open_asset(asset_png, home, name="a")
    Workspace.open_asset(asset_png2, home, name="b")
    assert Workspace.list_all(home) == ["a", "b"]


def test_open_same_path_twice_resumes(home, asset_png):
    """Identity keys on the path (C6): reopening the same file resumes the one asset."""
    Workspace.open_asset(asset_png, home, name="a")
    Workspace.resolve("a", home).apply("crop", ops.Transform.crop, {"x": 0, "y": 0, "w": 8, "h": 8})
    again = Workspace.open_asset(asset_png, home)      # same path → resume, not a fresh seed
    assert again.status()["steps"] == 2               # the earlier edit survived
    assert Workspace.list_all(home) == ["a"]


def test_list_all_missing_home(tmp_path):
    assert Workspace.list_all(str(tmp_path / "nope")) == []


def test_apply_undo_redo_reset_and_truncation(opened):
    home, name = opened
    ws = Workspace.resolve(name, home)
    ws.apply("edge_detect", ops.Transform.edge_detect, {"lo": 50, "hi": 150})
    ws.apply("silhouette_mask", ops.Transform.silhouette_mask, {})
    assert ws.status()["head"] == 2 and ws.status()["steps"] == 3
    ws.undo()
    assert ws.status()["head"] == 1
    ws.redo()
    assert ws.status()["head"] == 2
    # undo then apply truncates the redo tail
    ws.undo()
    ws.apply("crop", ops.Transform.crop, {"x": 0, "y": 0, "w": 10, "h": 10})
    st = ws.status()
    assert st["head"] == 2 and st["steps"] == 3
    assert st["chain"][-1] == "crop"
    ws.reset()
    assert ws.status()["head"] == 0


def test_head_and_set_head_clamp(opened):
    home, name = opened
    ws = Workspace.resolve(name, home)
    ws.apply("edge_detect", ops.Transform.edge_detect, {"lo": 50, "hi": 150})
    assert ws.head() == 1
    ws.set_head(999)                    # clamped to last
    assert ws.head() == 1
    ws.set_head(-5)                     # clamped to 0
    assert ws.head() == 0


def test_collapse_flattens(opened):
    home, name = opened
    ws = Workspace.resolve(name, home)
    ws.apply("edge_detect", ops.Transform.edge_detect, {"lo": 50, "hi": 150})
    ws.collapse()
    st = ws.status()
    assert st["steps"] == 1 and st["head"] == 0
    assert st["chain"] == ["collapsed"]


def test_edit_session_commit(opened):
    home, name = opened
    ws = Workspace.resolve(name, home)
    ws.begin_edit("do a thing")
    assert ws.in_session()
    ws.apply("edge_detect", ops.Transform.edge_detect, {"lo": 50, "hi": 150})
    ws.commit_edit()
    assert not ws.in_session()
    assert ws.status()["head"] == 1


def test_edit_session_cancel_restores(opened):
    home, name = opened
    ws = Workspace.resolve(name, home)
    ws.begin_edit("scratch")
    ws.apply("edge_detect", ops.Transform.edge_detect, {"lo": 50, "hi": 150})
    ws.cancel_edit()
    assert not ws.in_session()
    assert ws.status()["head"] == 0
    assert ws.status()["chain"] == ["open"]


def test_cancel_without_session_is_noop(opened):
    home, name = opened
    ws = Workspace.resolve(name, home)
    assert ws.cancel_edit()["head"] == 0


def test_scratch_store(opened):
    home, name = opened
    ws = Workspace.resolve(name, home)
    assert ws.scratch_get("k", "default") == "default"
    ws.scratch_set("k", {"a": 1})
    assert ws.scratch_get("k") == {"a": 1}
    ws.scratch_clear("k")
    assert ws.scratch_get("k") is None
    ws.scratch_clear("k")               # clearing a missing key is fine


def _ov(shape=(20, 20)):
    ov = np.zeros((*shape, 4), np.uint8)
    ov[5:15, 5:15] = (0, 255, 0, 255)
    return ov


def test_overlay_chain_push_and_head(opened):
    home, name = opened
    ws = Workspace.resolve(name, home)
    assert ws.overlay_head() == -1                      # none before any push
    assert ws.overlay_path() is None

    assert ws.push_overlay(_ov(), "edge → mask") == 0    # first version
    assert ws.push_overlay(_ov(), "simplify_contour") == 1
    assert ws.overlay_head() == 1

    import os
    assert os.path.exists(ws.overlay_path())            # current version file exists
    assert ws.overlay_path(0).endswith("0000-edge → mask.png")


def test_overlay_head_clamps_and_reads_versions(opened):
    home, name = opened
    ws = Workspace.resolve(name, home)
    ws.push_overlay(_ov(), "a")
    ws.push_overlay(_ov(), "b")
    ws.set_overlay_head(999)                            # clamped to last
    assert ws.overlay_head() == 1
    ws.set_overlay_head(0)                              # revert to first version
    assert ws.overlay_head() == 0 and ws.overlay_path().endswith("0000-a.png")
    ws.set_overlay_head(-5)                             # clamped to -1 = no overlay
    assert ws.overlay_head() == -1 and ws.overlay_path() is None


def test_export(opened, tmp_path):
    home, name = opened
    dest = str(tmp_path / "out" / "final.png")
    res = Workspace.resolve(name, home).export(dest)
    assert res["exported"] == dest
    import os

    assert os.path.exists(dest)
