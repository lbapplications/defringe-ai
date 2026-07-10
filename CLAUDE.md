# defringe-ai

**AI-native image tooling — "free Photoshop for UI."** A small MCP server that hands a
vision-capable AI deterministic raster transforms it calls, looks at, and re-tunes.

- **What it is / how to run it / the full tool reference → [README.md](README.md)** (user-facing).
- **How to work in this repo → the rules below.** This file is just the map.

## Rules — read the ones in scope before you act

Guidance lives in `.claude/rules/`, one **orthogonal** concern per file. Don't scatter a
concern across files or inline it here — put it in its rule and link. Read the rule(s)
that match what you're about to do:

| Rule | Read it when you're about to… |
|---|---|
| [repo-intent](.claude/rules/repo-intent.md) | branch, commit, open a PR, or add any structure/ceremony (spoiler: master-only, no PRs, edit in place) |
| [architecture](.claude/rules/architecture.md) | navigate or add code — the layers and what stays orthogonal to what |
| [tools](.claude/rules/tools.md) | add or edit an image tool — the class-set taxonomy + the edit-session gate |
| [coordinates](.claude/rules/coordinates.md) | do any geometry / pixel-indexing / dot / drawing work (the `arr[y,x]` trap) |
| [undo](.claude/rules/undo.md) | touch undo, `history.py`, or the board mask |
| [server-ops](.claude/rules/server-ops.md) | start / stop / restart the live server, or debug a change not showing up |

When a task spans concerns, read each matching rule — they're written to compose, not
overlap. New guidance goes into the single rule it belongs to (or a new rule), keeping
concerns orthogonal.
