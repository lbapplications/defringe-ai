# soft_lint instructions — the non-deterministic PR linter

**You are reviewing a PR against this repo's rules.** This is the *soft* lane of
`make check`: an instruction set, not a program. It is advisory and judgment-based — the
deterministic (mechanical) linters are a separate lane that isn't wired yet. Review the
**diff**, not the whole repo.

The rules live in `harness_driver/`, mapped by `HARNESS.md`. Read the rule a change touches
before judging it.

## Method — 80/20

For each rule the diff actually touches, assign one verdict:

- **PASS** — the diff clearly respects the rule.
- **SCRUTINY** — plausibly fine but leans on human judgment; it *can* merge, but say **why
  it's borderline** and **what a reviewer should check**. This is the 20% — most of
  soft_lint's value lives here.
- **BREAK** — the diff clearly violates a mechanical invariant; name it and the fix.

Bias toward **PASS**. Reserve **BREAK** for clear, mechanical violations. Use **SCRUTINY**
for judgment calls. Never block on style — block only on a real invariant. Only review
rules the diff touches (a docs-only PR doesn't get the NumPy check).

## Per-rule soft checks

Each maps to a `harness_driver/` rule — read it for the full standard.

- **repo-intent** — no new ceremony (CI/config/packaging/feature branches) unless the PR
  states the user asked for it. `SCRUTINY` when structure is added.
- **architecture** — layers stay orthogonal; `server.py` stays thin; state lives on disk.
  `BREAK` if a layer reaches across (e.g. a tool class touching the board).
- **frontend** — all server I/O goes through `state.ts` (no ad-hoc `fetch` in a component);
  `Canvas`/`Toolbox` don't import each other; the server is the source of truth. `BREAK`
  on a stray `fetch(` in a component.
- **tools** — a new tool is `@mcp.tool()`-registered **and** in `TAXONOMY` **and** in the
  README, returns a Pydantic model if it mutates, and is vectorised NumPy. `BREAK` if a
  headline capability is reachable only from a web route / left unregistered. `SCRUTINY` on
  a `for` loop in `imageops/` (is it per-pixel/point Python?).
- **orthogonalization** — one idea per class/module; tool classes import `utils` only, never
  each other; a shared concept moves to `utils`; a **taxonomy shift** is surfaced in the PR
  summary and mirrored everywhere (class, `TAXONOMY`, README, rule) in the same diff.
  `BREAK` on a sideways import between tool classes.
- **docstrings** — every forward-facing function (MCP tool, CLI handler, tool-class
  `@staticmethod`) has a Google-style docstring, updated in the **same diff** as any
  signature/behaviour change. `BREAK` on a signature change with a stale/absent docstring.
- **coordinates** — API is `(x, y)` top-left; numpy indexes `arr[y, x]`; size `(W,H)` =
  shape `(H,W,C)`. `SCRUTINY` on any new geometry / pixel indexing.
- **undo** — mask edits are undoable; moves are **not** tracked; history is the per-image
  engine; reset erases history. `SCRUTINY` on history/board changes.
- **server-ops / dev** — a port/flag/run-flow change updates the README **Dev** section.
  `BREAK` if `scripts/dev.sh` changed but the README Dev section didn't.
- **onboarding** — the provider-agnostic chain holds (provider file → `HARNESS.md` →
  `harness_driver/`); no rules are copied out of `harness_driver/`; a setup change updates
  the README **Setup** section.

## Output

A short report — for each touched rule: the verdict, `file:line`, and a one-line reason.
End with:

```
soft-lint: <N> break · <M> scrutiny — <fix first | merge with reviewer sign-off>
```

`BREAK`s should be fixed before merge; `SCRUTINY` items may merge with a reviewer's
explicit sign-off. This lane never hard-blocks on its own — it informs the gate.
