# Rule: server ops — running & restarting the live edit server

**Scope — read before** starting, stopping, or restarting the preview server, or
debugging why a change didn't show up.

## Run

```bash
cd /home/kerna/defringe-ai
DEFRINGE_HOME=$PWD/workspace uv run defringe-ai serve --http --preview
```

MCP on **:47823/mcp**, edit screen on **:47824** (uncommon ports; auto-bump if taken).

## Restart correctly (two real gotchas)

- **Relaunch in its OWN Bash call**, detached: `nohup … >> log 2>&1 < /dev/null & disown`.
  Do **not** chain the launch after a `pkill` in the *same* command — the `pkill`'s
  **exit 144** (just the signal; the kill worked) tears down the just-spawned child.
- **What needs what to show up:**
  - **Python change** (imageops/board/workspace/history/app.py) → **restart the server**.
  - **canvas.js change** → **restart** (the SSE build-stamp then auto-reloads open tabs).
  - **canvas.html / canvas.css change** → **hard-refresh the tab** (static files reload
    from disk; no restart needed, but no auto-reload either).

## After restart

Verify ports are up, then confirm state survived (it lives on disk in `workspace/`):
the board and edit chains come back exactly as left. See [repo-intent](repo-intent.md) —
edit in the main checkout (bgIsolation is off), which is what the running server serves.
