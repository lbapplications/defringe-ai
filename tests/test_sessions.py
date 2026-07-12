"""sessions.py — the opaque session layer (C5/C6): open/resume, resolve, name_of, advance."""

from __future__ import annotations

import json

import pytest

from defringe_ai.registry import Registry
from defringe_ai.sessions import Sessions


@pytest.fixture
def mounted(home, asset_png):
    """A mounted asset → (home, project_id, asset_id, name). The bridge sessions resolve over."""
    m = Registry(home).mount(asset_png, name="shark")
    return home, m.project_id, m.asset_id, m.name


# --- open / resume ---------------------------------------------------------

def test_open_mints_a_session(mounted):
    home, pid, aid, name = mounted
    s = Sessions(home).open(pid, aid, name)
    assert s.created is True and s.name == "shark"
    assert s.project_id == pid and s.asset_id == aid
    data = json.loads(open(f"{home}/session/working_session.json").read())
    assert data[s.id]["asset_id"] == aid                     # persisted to the working set
    assert json.loads(open(f"{home}/session/sessions.json").read())[s.id]   # and the ledger


def test_open_same_asset_resumes_one_handle(mounted):
    home, pid, aid, name = mounted
    sessions = Sessions(home)
    first = sessions.open(pid, aid, name)
    second = sessions.open(pid, aid, name)
    assert first.id == second.id                             # one live handle per asset (C6)
    assert second.created is False
    assert len(sessions.working()) == 1


def test_open_refreshes_a_renamed_label(mounted):
    home, pid, aid, _ = mounted
    sessions = Sessions(home)
    sid = sessions.open(pid, aid, "shark").id
    resumed = sessions.open(pid, aid, "hero")                # same identity, new label
    assert resumed.id == sid and resumed.created is False
    assert sessions.get(sid)["name"] == "hero"               # display field followed the rename


# --- resolve ---------------------------------------------------------------

def test_name_of_resolves_live_through_the_registry(mounted):
    home, pid, aid, name = mounted
    sid = Sessions(home).open(pid, aid, name).id
    assert Sessions(home).name_of(sid) == "shark"


def test_name_of_reflects_a_registry_rename(mounted):
    home, pid, aid, name = mounted
    sid = Sessions(home).open(pid, aid, name).id
    # rename the label in the registry, then confirm the session resolves to the NEW label
    data = json.loads(open(f"{home}/projects.json").read())
    data[pid]["assets"][aid]["name"] = "renamed"
    open(f"{home}/projects.json", "w").write(json.dumps(data))
    assert Sessions(home).name_of(sid) == "renamed"          # resolved live, not cached on the session


def test_blank_session_raises_with_guidance(home):
    with pytest.raises(ValueError, match="needs a session"):
        Sessions(home).resolve("")


def test_unknown_session_raises(home):
    with pytest.raises(ValueError, match="unknown session"):
        Sessions(home).resolve("nope-not-a-session")


# --- cursor (server-owned) -------------------------------------------------

def test_advance_moves_the_cursor(mounted):
    home, pid, aid, name = mounted
    sessions = Sessions(home)
    sid = sessions.open(pid, aid, name).id
    assert sessions.get(sid)["state_id"] is None
    sessions.advance(sid, state_id="state_2", mask_id="mask_0.png")
    s = sessions.get(sid)
    assert s["state_id"] == "state_2" and s["mask_id"] == "mask_0.png"


def test_advance_is_a_noop_when_unchanged(mounted):
    home, pid, aid, name = mounted
    sessions = Sessions(home)
    sid = sessions.open(pid, aid, name).id
    sessions.advance(sid, state_id="state_1", mask_id=None)
    before = open(f"{home}/session/working_session.json").read()
    sessions.advance(sid, state_id="state_1", mask_id=None)   # same cursor → no rewrite
    assert open(f"{home}/session/working_session.json").read() == before


def test_advance_unknown_session_is_silent(home):
    Sessions(home).advance("ghost", state_id="state_0", mask_id=None)   # no raise, no file


# --- listing ---------------------------------------------------------------

def test_by_name_reverse_lookup(mounted):
    home, pid, aid, name = mounted
    sid = Sessions(home).open(pid, aid, name).id
    assert Sessions(home).by_name() == {"shark": sid}
