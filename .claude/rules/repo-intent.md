# Rule: repo intent — don't force structure

**Scope — read before** branching, committing, opening a PR, adding CI/config/packaging,
or any "let's make this proper" restructuring.

This is **a public scratchpad to test an MCP**, not a product.

- **One branch: `master`.** No feature branches, no PRs, no worktrees to babysit.
  **Commit straight to `master`**; push when asked. Never `gh pr create` unless asked.
- **Don't add ceremony** — no CI, no packaging polish, no elaborate configs, no big
  speculative refactors — *unless the user asks for it*. When they do (they may), do it
  cleanly; otherwise keep changes small and direct.
- **Kept folders:** `inputs/` (drop source art) and `workspace/` (runtime edit state the
  server writes) each hold a `.gitkeep`; their **contents are git-ignored**.
- **bg worktree isolation is OFF here** (`.claude/settings.local.json` →
  `worktree.bgIsolation: none`, gitignored). Deliberate: the live server serves static
  files from the **main checkout**, so edits must land there. **Don't `EnterWorktree`** —
  edit in place on `master`.
