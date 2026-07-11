# Rule: server ops — running & restarting the live edit server

**Scope — read before** starting, stopping, or restarting the preview server, or
debugging why a change didn't show up.

## Run

**Preferred: `./scripts/dev.sh`** — one entry point, streams the log, and shuts down
cleanly (Ctrl-C frees the ports). `--dev` adds Vite HMR, `--server` skips the build. See
[dev](dev.md). The raw command below is the manual equivalent (what the script runs):

```bash
cd /home/kerna/defringe-ai
DEFRINGE_HOME=$PWD/workspace uv run defringe-ai serve --http --preview
```

MCP on **:47823/mcp**, edit screen on **:47824** (uncommon ports; auto-bump if taken). The
edit screen is the **built** Vite app in `web/dist`; an unbuilt checkout still boots and
shows a "run pnpm build" hint. First time / after frontend deps change: `cd frontend &&
pnpm install`.

## Two ways to run the UI

- **Prod (what the Python server serves):** `cd frontend && pnpm build` → `web/dist`, then
  the running server serves it at :47824. Rebuild + hard-refresh to see UI changes.
- **Dev (live HMR while iterating):** `cd frontend && pnpm dev` → Vite on **:47825**,
  proxying `/api`, `/img`, and the SSE stream to the Python server on :47824. Edit React and
  it hot-reloads instantly — no build, no server restart. Use `http://localhost:47825`.

## Restart correctly (two real gotchas)

- **Relaunch in its OWN Bash call**, detached: `nohup … >> log 2>&1 < /dev/null & disown`.
  Do **not** chain the launch after a `pkill` in the *same* command — the `pkill`'s
  **exit 144** (just the signal; the kill worked) tears down the just-spawned child.
- **What needs what to show up:**
  - **Python change** (imageops/board/workspace/history/app.py) → **restart the server**
    (the SSE build-stamp then auto-reloads open tabs).
  - **Frontend change** (`frontend/src/**`) → in **dev** (`pnpm dev`) it HMR-reloads
    instantly; in **prod** it needs `pnpm build` + a tab refresh (rebuilding `web/dist`
    doesn't restart Python, so the build-stamp auto-reload does NOT fire — refresh yourself).

## After restart

Verify ports are up, then confirm state survived (it lives on disk in `workspace/`):
the board and edit chains come back exactly as left. See [repo-intent](repo-intent.md) —
edit in the main checkout (bgIsolation is off), which is what the running server serves.
