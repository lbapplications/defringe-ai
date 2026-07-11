# HARNESS — how to work in defringe-ai (provider-agnostic)

**This is the authoritative, provider-agnostic guidance for this repo** — the rules any AI
agent must follow, independent of which assistant loads it (Claude, or anything else). The
rules it enforces live in **`harness_driver/`**, one **orthogonal** concern per file.

Provider entry points **chain into this file** — e.g. Claude Code's `CLAUDE.md` holds only
personal/provider prefs and says "read HARNESS.md". Follow this file as if it were inlined
into whatever loaded you. Onboarding another provider = a thin entry file pointing here;
never copy rules out of `harness_driver/` (single source). See
[onboarding](harness_driver/onboarding.md).

**The project:** an experiment in agent-driven image editing — a small MCP server that
hands a vision-capable agent deterministic raster transforms it calls, looks at, and
re-tunes, to probe whether an agent can edit images *effectively* this way. UI/game asset
prep is one motivating case; the question is general.

- **What it is / how to run it / the full tool reference → [README.md](README.md)** (user-facing).
- **How to work in this repo → the rules below.** This file is just the map.

## Rules — read the ones in scope before you act

Guidance lives in `harness_driver/`, one **orthogonal** concern per file. Don't scatter a
concern across files or inline it here — put it in its rule and link. Read the rule(s)
that match what you're about to do:

| Rule | Read it when you're about to… |
|---|---|
| [repo-intent](harness_driver/repo-intent.md) | branch, commit, open a PR, or add any structure/ceremony (spoiler: master-only, no PRs, edit in place) |
| [architecture](harness_driver/architecture.md) | navigate or add code — the layers and what stays orthogonal to what |
| [frontend](harness_driver/frontend.md) | touch `frontend/` — the Vite/React/Konva edit screen, its taxonomy, and how it's built/served |
| [tools](harness_driver/tools.md) | add or edit an image tool — a tool isn't real until it's MCP-registered; NumPy/Pydantic/README standards + the gate |
| [orthogonalization](harness_driver/orthogonalization.md) | add a class/module, move code between areas, or surface a taxonomy shift |
| [docstrings](harness_driver/docstrings.md) | write or edit ANY function — Google-style, kept in sync |
| [coordinates](harness_driver/coordinates.md) | do any geometry / pixel-indexing / dot / drawing work (the `arr[y,x]` trap) |
| [undo](harness_driver/undo.md) | touch undo, `history.py`, or the board mask |
| [server-ops](harness_driver/server-ops.md) | start / stop / restart the live server, or debug a change not showing up |
| [dev](harness_driver/dev.md) | change how the project is run/developed — `scripts/dev.sh`, ports, build/run flow (keep the README dev section in sync) |
| [onboarding](harness_driver/onboarding.md) | change how an agent/provider is onboarded — the entry chain or the README Setup guide |

When a task spans concerns, read each matching rule — they're written to compose, not
overlap. New guidance goes into the single rule it belongs to (or a new rule), keeping
concerns orthogonal.
