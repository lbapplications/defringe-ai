# Rule: repo intent — don't force structure

**Scope — read before** branching, committing, opening a PR, adding CI/config/packaging,
or any "let's make this proper" restructuring.

This is **an experiment: can an agent edit images *effectively* when handed deterministic
raster tools?** A public scratchpad to probe that question — **not a product.** (UI/game
asset prep is one motivating use case, not the mission.)

- **Default is `master`, straight-line.** While shaping, **commit straight to `master`**;
  push when asked. No feature branches, no worktrees to babysit, and **never `gh pr create`
  unless asked**. This is the fiddle-repo default, not a ban.
- **When a PR *is* opened, it goes through the gate.** The repo carries a lightweight
  governance seam — `make check` → the `soft_lint/` non-deterministic linter (an agent judges
  the diff against `harness_driver/`, mapped by `HARNESS.md`). Opening a PR (when asked) is
  sanctioned *because* that gate exists: the PR is the unit the soft-lint reviews. The gate is
  advisory (`BREAK` = fix first, `SCRUTINY` = merge with sign-off) — it informs, doesn't
  hard-block. So the stance is: default to straight-to-`master` for shaping, and when the work
  warrants a PR, run it through `make check` rather than bolting on heavier ceremony.
- **Don't add *other* ceremony** — no CI, no packaging polish, no elaborate configs, no big
  speculative refactors — *unless the user asks for it*. The soft-lint gate is the one
  sanctioned piece of process; everything past it stays opt-in. When the user does ask, do it
  cleanly; otherwise keep changes small and direct.
- **Kept folders:** `inputs/` (drop source art) and `workspace/` (runtime edit state the
  server writes) each hold a `.gitkeep`; their **contents are git-ignored**.
- **bg worktree isolation is OFF here** (`.claude/settings.local.json` →
  `worktree.bgIsolation: none`, gitignored). Deliberate: the live server serves static
  files from the **main checkout**, so edits must land there. **Don't `EnterWorktree`** —
  edit in place on `master`.
