"""registry.py — the projects.json mount table (C4/C6): mount, resolve+verify, adopt."""

from __future__ import annotations

import json

import pytest
from PIL import Image

from defringe_ai import identity
from defringe_ai.registry import Registry


def _png(dirpath, name="a.png"):
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / name
    Image.new("RGBA", (4, 4)).save(p)
    return str(p)


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return str(h)


# --- mount -----------------------------------------------------------------

def test_mount_registers_project_and_asset(tmp_path, home):
    asset = _png(tmp_path / "proj")
    m = Registry(home).mount(asset)
    assert m.created is True
    assert m.name == "a"
    assert m.dir == f"{home}/{m.project_id}/{m.asset_id}"
    data = json.loads(open(f"{home}/projects.json").read())
    assert m.project_id in data
    assert data[m.project_id]["assets"][m.asset_id]["path"] == "a.png"


def test_mount_same_path_twice_resumes(tmp_path, home):
    asset = _png(tmp_path / "proj")
    reg = Registry(home)
    first = reg.mount(asset)
    second = reg.mount(asset)
    assert first.asset_id == second.asset_id
    assert second.created is False                  # a resume, not a duplicate
    assert len(reg.assets()) == 1


def test_mount_default_project_is_asset_dir(tmp_path, home):
    a = _png(tmp_path / "proj", "a.png")
    b = _png(tmp_path / "proj", "b.png")
    reg = Registry(home)
    ma, mb = reg.mount(a), reg.mount(b)
    assert ma.project_id == mb.project_id           # same folder → same project
    assert ma.asset_id != mb.asset_id


def test_mount_explicit_project_root_groups_a_tree(tmp_path, home):
    root = tmp_path / "proj"
    a = _png(root, "a.png")
    b = _png(root / "sub", "b.png")
    reg = Registry(home)
    ma = reg.mount(a, project_root=str(root))
    mb = reg.mount(b, project_root=str(root))
    assert ma.project_id == mb.project_id
    assert mb.rel == "sub/b.png"


def test_mount_rejects_non_png(tmp_path, home):
    p = tmp_path / "proj" / "photo.jpg"
    p.parent.mkdir(parents=True)
    Image.new("RGB", (4, 4)).save(p, format="JPEG")
    with pytest.raises(ValueError, match="png-only"):
        Registry(home).mount(str(p))


def test_mount_dedupes_labels(tmp_path, home):
    """Two different assets that would share a basename get distinct labels."""
    a = _png(tmp_path / "one", "shark.png")
    b = _png(tmp_path / "two", "shark.png")
    reg = Registry(home)
    ma, mb = reg.mount(a), reg.mount(b)
    assert {ma.name, mb.name} == {"shark", "shark-2"}


def test_mount_custom_name(tmp_path, home):
    m = Registry(home).mount(_png(tmp_path / "proj"), name="hero")
    assert m.name == "hero"


def test_mount_rename_on_resume(tmp_path, home):
    asset = _png(tmp_path / "proj")
    reg = Registry(home)
    reg.mount(asset)
    m = reg.mount(asset, name="renamed")
    assert m.name == "renamed" and m.created is False


# --- resolve + verify ------------------------------------------------------

def test_resolve_returns_record(tmp_path, home):
    m = Registry(home).mount(_png(tmp_path / "proj"))
    rec = Registry(home).resolve(m.project_id, m.asset_id)
    assert rec["path"] == "a.png" and rec["dir"] == m.dir


def test_resolve_unknown_raises(home):
    with pytest.raises(ValueError, match="no such asset"):
        Registry(home).resolve("nope-pid", "nope-aid")


def test_resolve_detects_tampered_asset_path(tmp_path, home):
    m = Registry(home).mount(_png(tmp_path / "proj"))
    data = json.loads(open(f"{home}/projects.json").read())
    data[m.project_id]["assets"][m.asset_id]["path"] = "somethingelse.png"   # corrupt the table
    open(f"{home}/projects.json", "w").write(json.dumps(data))
    with pytest.raises(ValueError, match="id/path mismatch"):
        Registry(home).resolve(m.project_id, m.asset_id)


def test_resolve_detects_tampered_project_path(tmp_path, home):
    m = Registry(home).mount(_png(tmp_path / "proj"))
    data = json.loads(open(f"{home}/projects.json").read())
    data[m.project_id]["path"] = "/wrong/root"
    open(f"{home}/projects.json", "w").write(json.dumps(data))
    with pytest.raises(ValueError, match="project id/path mismatch"):
        Registry(home).resolve(m.project_id, m.asset_id)


# --- lookups ---------------------------------------------------------------

def test_locate_and_dir_by_name(tmp_path, home):
    m = Registry(home).mount(_png(tmp_path / "proj"))
    reg = Registry(home)
    assert reg.locate("a") == (m.project_id, m.asset_id)
    assert reg.dir_by_name("a") == m.dir
    assert reg.locate("ghost") is None
    assert reg.dir_by_name("ghost") is None


def test_names_sorted(tmp_path, home):
    reg = Registry(home)
    reg.mount(_png(tmp_path / "p", "z.png"))
    reg.mount(_png(tmp_path / "p", "a.png"))
    assert reg.names() == ["a", "z"]


# --- adopt legacy ----------------------------------------------------------

def test_adopt_legacy_registers_flat_dirs(home):
    import os
    for nm in ("shark", "double-exposure"):
        os.makedirs(f"{home}/{nm}")
        open(f"{home}/{nm}/manifest.json", "w").write("{}")
    reg = Registry(home)
    adopted = reg.adopt_legacy()
    assert sorted(adopted) == ["double-exposure", "shark"]
    assert reg.dir_by_name("shark") == f"{home}/shark"      # adopted in place — dir unchanged


def test_adopt_legacy_is_idempotent(home):
    import os
    os.makedirs(f"{home}/shark")
    open(f"{home}/shark/manifest.json", "w").write("{}")
    reg = Registry(home)
    assert reg.adopt_legacy() == ["shark"]
    assert reg.adopt_legacy() == []                         # second pass adopts nothing


def test_adopt_legacy_skips_non_workspace_dirs(home):
    import os
    os.makedirs(f"{home}/session")                          # no manifest.json → not a workspace
    open(f"{home}/projects.json", "w").write("{}")
    assert Registry(home).adopt_legacy() == []


def test_adopt_legacy_dedupes_label_against_registered_asset(home, asset_png):
    """A legacy flat dir whose basename collides with an already-registered label is still
    adopted, under a deduped label — not silently skipped (which would orphan its history)."""
    import os
    reg = Registry(home)
    reg.mount(asset_png, name="shark")                      # register an id-keyed asset labelled "shark"
    os.makedirs(f"{home}/shark")                            # a *different* legacy dir, same basename
    open(f"{home}/shark/manifest.json", "w").write("{}")
    adopted = reg.adopt_legacy()
    assert adopted == ["shark-2"]                           # deduped, not dropped
    assert reg.dir_by_name("shark-2") == f"{home}/shark"    # the legacy dir is reachable
    assert reg.adopt_legacy() == []                         # still idempotent (by identity)


def test_real_path_is_project_root_plus_relative(home, asset_png):
    """real_path points OUTSIDE the workspace home — at the user's actual file (projection's target)."""
    import os
    reg = Registry(home)
    m = reg.mount(asset_png, name="shark")
    real = reg.real_path(m.project_id, m.asset_id)
    assert os.path.samefile(real, asset_png)               # project root + relative asset path
