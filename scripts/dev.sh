#!/usr/bin/env bash
# dev.sh — run the defringe-ai server (MCP + the live edit screen) with a clean,
# graceful shutdown, streaming its log into this one terminal. Ctrl-C stops
# everything and frees the ports, so the next run always rebinds cleanly (no more
# orphaned server a Claude session left behind).
#
#   MCP         : http://localhost:47823/mcp
#   edit screen : http://localhost:47824        (the built Vite UI in web/dist)
#
#   ./scripts/dev.sh           # build the frontend, run the server (serves web/dist)
#   ./scripts/dev.sh --dev     # run the server + Vite dev server (HMR) on :47825
#   ./scripts/dev.sh --server  # server only — skip the frontend build
#   ./scripts/dev.sh --reset   # (modifier) remount inputs/*.png from scratch first, then serve
set -euo pipefail

# Anchor to the repo root (this script lives in <root>/scripts) so uv, workspace/,
# and frontend/ resolve regardless of where it's invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MCP_PORT=47823
PREVIEW_PORT=47824
VITE_PORT=47825
LOG_DIR="$ROOT/logs"
SERVER_LOG="$LOG_DIR/server.log"
WEB_LOG="$LOG_DIR/web.log"
# The server keys its on-disk state off DEFRINGE_HOME; pin it to the repo's workspace/.
export DEFRINGE_HOME="$ROOT/workspace"

MODE=default   # default (build+dist) | dev (server+Vite HMR) | server (no build)
RESET=0        # --reset modifier: remount inputs/*.png from scratch before serving
for arg in "$@"; do
  case "$arg" in
    --dev)     MODE=dev ;;
    --server)  MODE=server ;;
    --reset)   RESET=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "usage: $0 [--dev|--server] [--reset]" >&2; exit 2 ;;
  esac
done

# Vite HMR runs only for --dev. (The old --watch mode auto-restarted the Python server on .py
# edits; that's dropped — the SSE build stamp already auto-reloads open tabs when the server
# comes back with new code, and the process relaunch is handled outside dev.sh.)
if [ "$MODE" = dev ]; then VITE=1; else VITE=0; fi

mkdir -p "$LOG_DIR"

# free_port <port> <label> — kill whatever is listening so we can rebind.
free_port() {
  local port="$1" label="$2" pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "$port"/tcp 2>/dev/null || true)"
  fi
  if [ -n "$pids" ]; then
    echo "» stopping existing $label on :$port (pids: $pids)"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
}

PIDS=()
TAILS=()
cleanup() {
  # Ignore further Ctrl-C/TERM while we tear down so a double tap can't re-enter
  # this and leave orphans.
  trap '' INT TERM
  echo
  echo "» shutting down…"
  # Kill the log tails first so their death rattle stays in the log file, not the
  # terminal after the prompt returns.
  for t in "${TAILS[@]:-}"; do
    [ -n "$t" ] && kill "$t" 2>/dev/null || true
  done
  # `uv run` is the parent; the actual server is a child that holds the ports. Kill
  # the parents we spawned, then free the ports to reap the real listeners so the
  # next run (or a test) binds cleanly.
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  free_port "$MCP_PORT" MCP
  free_port "$PREVIEW_PORT" "edit screen"
  [ "$VITE" = 1 ] && free_port "$VITE_PORT" "Vite dev"
  echo "» stopped — ports freed."
  exit 0
}
trap cleanup INT TERM

# --- reset (optional) -------------------------------------------------------
# --reset gives a clean, projectable board for testing: wipe the runtime edit state and
# remount the source art from scratch. We mount COPIES in a gitignored live/ — projection
# (merge / live C7) overwrites whatever file it's pointed at, so the pristine inputs/ must
# never be the mount target. CLI `open` now also board-selects, so each copy lands on the
# window board as a real-file-backed (projectable) asset.
if [ "$RESET" = 1 ]; then
  echo "» --reset: remounting inputs/*.png from scratch"
  # 1. wipe workspace/ runtime state, keeping only the tracked .gitkeep.
  find "$ROOT/workspace" -mindepth 1 -not -name .gitkeep -delete 2>/dev/null || true
  # 2. copy source art → gitignored live/ (inputs/ stays pristine).
  rm -rf "$ROOT/live"; mkdir -p "$ROOT/live"
  shopt -s nullglob
  srcs=("$ROOT"/inputs/*.png)
  if [ ${#srcs[@]} -eq 0 ]; then
    echo "  (no inputs/*.png found — nothing to remount)"
  else
    for src in "${srcs[@]}"; do cp "$src" "$ROOT/live/"; done
    # 3. mount + board-select each copy (drives the engine directly; no server needed).
    for img in "$ROOT"/live/*.png; do
      echo "  mounting $(basename "$img")"
      uv run defringe-ai open "$img" >/dev/null
    done
    echo "» reset complete — ${#srcs[@]} asset(s) mounted, workspace/ clean"
  fi
  shopt -u nullglob
fi

# --- frontend ---------------------------------------------------------------
# default mode serves the BUILT bundle from web/dist; dev mode runs Vite HMR instead.
if [ "$MODE" != server ] && [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "» installing frontend deps (frontend/node_modules missing)"
  (cd frontend && pnpm install)
fi
if [ "$MODE" = default ]; then
  echo "» building frontend → src/defringe_ai/web/dist"
  (cd frontend && pnpm build)
fi

# --- server (Python: MCP + preview) -----------------------------------------
free_port "$MCP_PORT" MCP
free_port "$PREVIEW_PORT" "edit screen"
: > "$SERVER_LOG"
echo "» starting server on :$MCP_PORT (MCP) + :$PREVIEW_PORT (edit)  (log: $SERVER_LOG)"
uv run defringe-ai serve --http --preview >>"$SERVER_LOG" 2>&1 &
PIDS+=("$!")

# --- Vite dev server (HMR) in --dev -----------------------------------------
if [ "$VITE" = 1 ]; then
  free_port "$VITE_PORT" "Vite dev"
  echo "» starting Vite dev on :$VITE_PORT (HMR, proxies /api + /img → :$PREVIEW_PORT)  (log: $WEB_LOG)"
  : > "$WEB_LOG"
  (cd frontend && pnpm dev) >>"$WEB_LOG" 2>&1 &
  PIDS+=("$!")
fi

echo
echo "──────────────────────────────────────────────────────────"
echo "  MCP         : http://localhost:$MCP_PORT/mcp"
if [ "$VITE" = 1 ]; then
  echo "  edit (HMR)  : http://localhost:$VITE_PORT   ← test here (live frontend + backend)"
  echo "  edit (dist) : http://localhost:$PREVIEW_PORT"
else
  echo "  edit screen : http://localhost:$PREVIEW_PORT"
fi
echo "  logs        : $LOG_DIR  (Ctrl-C stops everything, frees ports)"
echo "──────────────────────────────────────────────────────────"
echo

# Stream the log(s) with a prefix so they're distinguishable in one terminal.
# (TAILS is declared up top so an early Ctrl-C during build can still reap them.)
tail -n +1 -F "$SERVER_LOG" | sed -u 's/^/[server] /' & TAILS+=("$!")
[ "$VITE" = 1 ] && { tail -n +1 -F "$WEB_LOG" | sed -u 's/^/[web]    /' & TAILS+=("$!"); }

# Wait on the server(s); when one dies (or Ctrl-C), cleanup runs.
wait "${PIDS[@]}"
