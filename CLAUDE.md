# defringe-ai

**An experiment in agent-driven image editing.** A small MCP server that hands a
vision-capable AI deterministic raster transforms it calls, looks at, and re-tunes — a
testbed for whether an agent can edit images *effectively* this way. UI/game asset prep
is one motivating case; the question is general.

- **What it is / how to run it / the full tool reference → [README.md](README.md)** (user-facing).
- **How to work in this repo → the rules below.** This file is just the map.

## Always: show me what you did

When I ask you to do something, I expect to **see the result** — not just a description of
it. Ran a tool on an image? Show the output image. Changed code or docs? Show the diff.
Cleared/edited state? Show the before→after. "Looking" is half the loop this repo exists to
test — so surface the artifact every time, don't make me ask for it.

## Rules — read the ones in scope before you act

Guidance lives in `.claude/rules/`, one **orthogonal** concern per file. Don't scatter a
concern across files or inline it here — put it in its rule and link. Read the rule(s)
that match what you're about to do:

| Rule | Read it when you're about to… |
|---|---|
| [repo-intent](.claude/rules/repo-intent.md) | branch, commit, open a PR, or add any structure/ceremony (spoiler: master-only, no PRs, edit in place) |
| [architecture](.claude/rules/architecture.md) | navigate or add code — the layers and what stays orthogonal to what |
| [frontend](.claude/rules/frontend.md) | touch `frontend/` — the Vite/React/Konva edit screen, its taxonomy, and how it's built/served |
| [tools](.claude/rules/tools.md) | add or edit an image tool — a tool isn't real until it's MCP-registered; NumPy/Pydantic/README standards + the gate |
| [orthogonalization](.claude/rules/orthogonalization.md) | add a class/module, move code between areas, or surface a taxonomy shift |
| [docstrings](.claude/rules/docstrings.md) | write or edit ANY function — Google-style, kept in sync |
| [coordinates](.claude/rules/coordinates.md) | do any geometry / pixel-indexing / dot / drawing work (the `arr[y,x]` trap) |
| [undo](.claude/rules/undo.md) | touch undo, `history.py`, or the board mask |
| [server-ops](.claude/rules/server-ops.md) | start / stop / restart the live server, or debug a change not showing up |

When a task spans concerns, read each matching rule — they're written to compose, not
overlap. New guidance goes into the single rule it belongs to (or a new rule), keeping
concerns orthogonal.
