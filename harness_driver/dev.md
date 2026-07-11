# Rule: dev experience — one entry point, graceful shutdown, kept documented

**Scope — read before** changing anything about how the project is *run or developed
locally*: `scripts/dev.sh`, the ports, the build/run flow, logs, or adding another
long-running process. Related: [server-ops](server-ops.md) (the raw run/restart mechanics),
[frontend](frontend.md) (build vs HMR).

## The standard

- **One entry point: `scripts/dev.sh`.** Running the stack for a human goes through this
  script, not a pile of remembered flags. It runs the Python server (MCP + edit screen) and,
  with `--dev`, the Vite HMR server too. Modes: `default` (build → serve `web/dist`), `--dev`
  (server + Vite HMR), `--server` (server only, no build).
- **Graceful shutdown is non-negotiable.** A `trap cleanup INT TERM` must: disable
  re-entrancy (`trap '' INT TERM`), reap the log tails, kill the spawned parents, **and
  free the ports** (`uv run` is a parent; the real listener is a child that a bare `kill`
  leaves holding the port). Ctrl-C ⇒ ports free for the next run. No orphaned servers.
- **Free ports before binding.** Start-up calls `free_port` on each port so a server a
  previous session left behind can't wedge the run (mirrors the restart gotcha in
  [server-ops](server-ops.md)).
- **Ports are fixed and listed:** 47823 MCP, 47824 edit screen, 47825 Vite dev. Logs go to
  `logs/` (gitignored).

## Keep it documented (the sync obligation)

Any change to the dev experience — a new/renamed flag, a port, the run or build flow, an
added process, log locations — updates **both** in the same change:

1. the **`## Dev`** section of **README.md** (the user-facing how-to), and
2. **this rule** (the invariants above).

A dev-experience change that updates the script but not the docs is half-done — the next
person (or agent) runs it wrong. Treat this like the README-sync obligation for tools
([tools](tools.md)).
