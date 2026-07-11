"""identity.py — deterministic project/asset ids + the png intake gate (C3/C8)."""

from __future__ import annotations

import uuid

import pytest
from PIL import Image

from defringe_ai import identity


# --- id derivation ---------------------------------------------------------

def test_ids_are_full_uuids_not_truncated():
    pid = identity.project_id("/some/root")
    aid = identity.asset_id("a/b.png")
    # a real uuid5 round-trips through uuid.UUID and is version 5 — never a short slug
    assert str(uuid.UUID(pid)) == pid and uuid.UUID(pid).version == 5
    assert str(uuid.UUID(aid)) == aid and uuid.UUID(aid).version == 5


def test_ids_are_deterministic():
    assert identity.project_id("/x/y") == identity.project_id("/x/y")
    assert identity.asset_id("shark.png") == identity.asset_id("shark.png")


def test_distinct_paths_give_distinct_ids():
    assert identity.asset_id("a.png") != identity.asset_id("b.png")
    assert identity.project_id("/one") != identity.project_id("/two")


def test_root_normalization_collapses_spellings(tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    a = identity.project_id(str(d))
    b = identity.project_id(str(d) + "/")           # trailing slash
    c = identity.project_id(str(tmp_path / "proj" / "."))   # dot segment
    assert a == b == c


def test_rel_normalization_collapses_spellings():
    assert identity.asset_id("a/b.png") == identity.asset_id("./a/b.png")
    assert identity.asset_id("a/b.png") == identity.asset_id("a//b.png")
    assert identity.asset_id("a/b.png") == identity.asset_id("/a/b.png")   # leading slash stripped


def test_norm_rel_is_forward_slashed_and_relative():
    assert identity.norm_rel("a\\b.png").endswith("b.png")   # backslashes normalized on any os
    assert not identity.norm_rel("/x/y.png").startswith("/")


def test_relativize(tmp_path):
    root = tmp_path / "proj"
    (root / "sub").mkdir(parents=True)
    asset = root / "sub" / "a.png"
    asset.write_bytes(b"x")
    assert identity.relativize(str(asset), str(root)) == "sub/a.png"


# --- png gate --------------------------------------------------------------

def _png(path, tmp_path):
    p = tmp_path / path
    Image.new("RGBA", (4, 4)).save(p)
    return str(p)


def test_is_png_true_for_real_png(tmp_path):
    assert identity.is_png(_png("a.png", tmp_path))


def test_is_png_false_for_jpg_bytes(tmp_path):
    p = tmp_path / "a.jpg"
    Image.new("RGB", (4, 4)).save(p, format="JPEG")
    assert not identity.is_png(str(p))


def test_is_png_ignores_extension_lie(tmp_path):
    """A jpg renamed .png is still rejected — we read the signature, not the name."""
    p = tmp_path / "liar.png"
    Image.new("RGB", (4, 4)).save(p, format="JPEG")
    assert not identity.is_png(str(p))


def test_is_png_false_for_missing():
    assert not identity.is_png("/no/such/file.png")


def test_ensure_png_passes_for_png(tmp_path):
    identity.ensure_png(_png("ok.png", tmp_path))          # no raise


def test_ensure_png_rejects_missing(tmp_path):
    with pytest.raises(ValueError, match="no such asset"):
        identity.ensure_png(str(tmp_path / "ghost.png"))


def test_ensure_png_rejects_non_png_with_reason(tmp_path):
    p = tmp_path / "photo.jpg"
    Image.new("RGB", (4, 4)).save(p, format="JPEG")
    with pytest.raises(ValueError, match="png-only"):
        identity.ensure_png(str(p))
