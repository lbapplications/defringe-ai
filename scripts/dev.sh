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

MODE=default   # default (build + serve dist) | dev (server + Vite HMR) | server (no build)
for arg in "$@"; do
  case "$arg" in
    --dev)     MODE=dev ;;
    --server)  MODE=server ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "usage: $0 [--dev|--server]" >&2; exit 2 ;;
  esac
done

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
  [ "$MODE" = dev ] && free_port "$VITE_PORT" "Vite dev"
  echo "» stopped — ports freed."
  exit 0
}
trap cleanup INT TERM

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
echo "» starting server on :$MCP_PORT (MCP) + :$PREVIEW_PORT (edit)  (log: $SERVER_LOG)"
: > "$SERVER_LOG"
uv run defringe-ai serve --http --preview >>"$SERVER_LOG" 2>&1 &
PIDS+=("$!")

# --- Vite dev server (HMR) in --dev -----------------------------------------
if [ "$MODE" = dev ]; then
  free_port "$VITE_PORT" "Vite dev"
  echo "» starting Vite dev on :$VITE_PORT (HMR, proxies /api + /img → :$PREVIEW_PORT)  (log: $WEB_LOG)"
  : > "$WEB_LOG"
  (cd frontend && pnpm dev) >>"$WEB_LOG" 2>&1 &
  PIDS+=("$!")
fi

echo
echo "──────────────────────────────────────────────────────────"
echo "  MCP         : http://localhost:$MCP_PORT/mcp"
if [ "$MODE" = dev ]; then
  echo "  edit (HMR)  : http://localhost:$VITE_PORT"
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
[ "$MODE" = dev ] && { tail -n +1 -F "$WEB_LOG" | sed -u 's/^/[web]    /' & TAILS+=("$!"); }

# Wait on the server(s); when one dies (or Ctrl-C), cleanup runs.
wait "${PIDS[@]}"
