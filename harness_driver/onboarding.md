# Rule: onboarding — the provider-agnostic setup chain, kept documented

**Scope — read before** changing how a new agent/provider is onboarded: the entry chain
(`CLAUDE.md` → `HARNESS.md` → `harness_driver/`), adding a provider entry point, moving
where the rules live, or the README **Setup** guide.

## The model

- **Rules are provider-agnostic and live in `harness_driver/`** — one orthogonal concern
  per file. **`HARNESS.md`** (repo root) is the authoritative map that enforces them.
- **Each provider gets a thin entry file that chains to `HARNESS.md`** and holds only that
  provider's personal/tool prefs (Claude Code: `CLAUDE.md`). The entry file says "read
  HARNESS.md"; it does **not** restate the rules.
- **Onboarding a new provider = add its entry file pointing at `HARNESS.md`.** Never copy
  rules out of `harness_driver/` into a provider file — single source, or they drift.

## Keep it documented (the sync obligation)

Any change to the setup/onboarding flow — a new provider entry, the chain, where the rules
live, the bootstrap steps — updates the **`## Setup`** section of **README.md** in the same
change. A setup change that rewires things but not the README leaves the next person (or
agent) unable to onboard. Same discipline as the README-sync obligation for
[tools](tools.md) and the dev-docs obligation in [dev](dev.md).
