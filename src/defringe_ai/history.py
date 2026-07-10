"""Per-image undo/redo — an orthogonal substrate, independent of WHAT changed.

The engine knows nothing about dots, pixels, or placement. It stores opaque **mementos**
(a snapshot of one image's state, just a dict) on a **timeline of actions**, with an
optional open **focus** that bundles many sub-steps into a single committed action.

    Memento   a snapshot of one image's state (opaque dict)
    Action    { label, state: Memento }            one committed step on the timeline
    Focus      base Memento + [sub-step Mementos]   an open transaction (bundle)
    History   [Action, ...] + head + optional Focus

Undo is *focus-aware*: with a focus open it pops the last sub-step (e.g. the last dot);
with no focus it walks the committed timeline. Commit a focus and its sub-steps collapse
to ONE action, so a later timeline-undo jumps past the whole bundle in a single step.

Orthogonality: any subsystem records a change by handing over a fresh snapshot and gets a
snapshot back on undo. New tools need zero undo code — they mutate through the same gate.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

Memento = dict  # opaque per-image state: {mask, locked, x, y, scale, pixel_head, ...}


def _clone(m: Memento) -> Memento:
    return copy.deepcopy(m)


@dataclass
class Action:
    label: str
    state: Memento

    def to_dict(self) -> dict:
        return {"label": self.label, "state": self.state}

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(d["label"], d["state"])


@dataclass
class Focus:
    label: str
    base: Memento                       # state when the focus opened (for cancel)
    steps: list[Memento] = field(default_factory=list)

    def current(self) -> Memento:
        return self.steps[-1] if self.steps else self.base

    def to_dict(self) -> dict:
        return {"label": self.label, "base": self.base, "steps": self.steps}

    @classmethod
    def from_dict(cls, d: dict) -> "Focus":
        return cls(d["label"], d["base"], list(d.get("steps", [])))


class History:
    """One image's timeline. Construct with the initial state; mutate through commit/
    step/end_focus; observe with `state`, `can_undo`, `can_redo`, `timeline`."""

    def __init__(self, initial: Memento, label: str = "open"):
        self._actions: list[Action] = [Action(label, _clone(initial))]
        self._head: int = 0
        self._focus: Focus | None = None

    # --- observation -------------------------------------------------------

    @property
    def state(self) -> Memento:
        """The live state: the open focus's tip if one is open, else the head action."""
        src = self._focus.current() if self._focus is not None else self._actions[self._head].state
        return _clone(src)

    @property
    def in_focus(self) -> bool:
        return self._focus is not None

    @property
    def focus_label(self) -> str | None:
        return self._focus.label if self._focus is not None else None

    @property
    def can_undo(self) -> bool:
        return self._head > 0 or bool(self._focus and self._focus.steps)

    @property
    def can_redo(self) -> bool:
        return self._focus is None and self._head < len(self._actions) - 1

    def timeline(self) -> list[str]:
        marks = [a.label for a in self._actions]
        if 0 <= self._head < len(marks):
            marks[self._head] = "* " + marks[self._head]
        if self._focus is not None:
            marks.append(f"~ {self._focus.label} ({len(self._focus.steps)})")
        return marks

    # --- committing a standalone action ------------------------------------

    def commit(self, label: str, state: Memento) -> None:
        """Record one atomic action. Ends any open focus first, drops the redo tail."""
        self.end_focus()
        del self._actions[self._head + 1:]
        self._actions.append(Action(label, _clone(state)))
        self._head = len(self._actions) - 1

    # --- focus (a bundle of sub-steps) -------------------------------------

    def begin_focus(self, label: str) -> None:
        if self._focus is None:
            self._focus = Focus(label, _clone(self._actions[self._head].state))

    def step(self, label: str, state: Memento) -> None:
        """Add a sub-step to the open focus (opening one labelled `label` if needed).
        If a focus with a *different* label is open, collapse it first."""
        if self._focus is not None and self._focus.label != label:
            self.end_focus()
        if self._focus is None:
            self.begin_focus(label)
        self._focus.steps.append(_clone(state))

    def end_focus(self) -> None:
        """Collapse the open focus into one committed action (no-op if empty/none)."""
        f, self._focus = self._focus, None
        if f is None or not f.steps:
            return
        del self._actions[self._head + 1:]
        self._actions.append(Action(f.label, _clone(f.current())))
        self._head = len(self._actions) - 1

    def cancel_focus(self) -> None:
        """Discard the open focus; live state falls back to the current head action."""
        self._focus = None

    # --- undo / redo -------------------------------------------------------

    def undo(self) -> bool:
        """Focus-aware. Pop the last sub-step if a focus is open; otherwise step the
        committed head back one. Returns False when there's nothing left to undo."""
        if self._focus is not None:
            if self._focus.steps:
                self._focus.steps.pop()
                return True
            self._focus = None            # empty focus — drop it, fall through to timeline
        if self._head == 0:
            return False
        self._head -= 1
        return True

    def redo(self) -> bool:
        if self._focus is not None or self._head >= len(self._actions) - 1:
            return False
        self._head += 1
        return True

    # --- persistence -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "actions": [a.to_dict() for a in self._actions],
            "head": self._head,
            "focus": self._focus.to_dict() if self._focus is not None else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "History":
        h = cls.__new__(cls)
        h._actions = [Action.from_dict(a) for a in d.get("actions", [])] or [Action("open", {})]
        h._head = max(0, min(int(d.get("head", 0)), len(h._actions) - 1))
        f = d.get("focus")
        h._focus = Focus.from_dict(f) if f else None
        return h
