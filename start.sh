#!/usr/bin/env bash
# AFM launcher:  ./start.sh [start|stop|restart|status|test|install]
#   start (default) and restart always stop running AFM servers first, then launch fresh.
#   Data (run history, simulated environment) is kept; use "Reset demo" in the UI to restore the scenario.
#   backend  → http://127.0.0.1:8530  (FastAPI)
#   frontend → http://127.0.0.1:5530  (Vite dev server, proxies /api to the backend)
# LLM tool:  mock by default.  Use Claude:  AFM_LLM_PROVIDER=claude ./start.sh restart
#   Ports:  AFM_FRONTEND_PORT / AFM_BACKEND_PORT, from the command line or backend/.env, e.g.
#           AFM_FRONTEND_PORT=3010 ./start.sh      (the UI binds 127.0.0.1 only: use an SSH tunnel from another machine)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/logs"; mkdir -p "$LOGS"
# ports: command line > backend/.env > defaults (only the two port lines are read here)
env_port() { [ -f "$ROOT/backend/.env" ] && grep -E "^$1=[0-9]+\s*$" "$ROOT/backend/.env" | tail -1 | cut -d= -f2 | tr -d '[:space:]' || true; }
BACK_PORT="${AFM_BACKEND_PORT:-$(env_port AFM_BACKEND_PORT)}"; BACK_PORT="${BACK_PORT:-8530}"
FRONT_PORT="${AFM_FRONTEND_PORT:-$(env_port AFM_FRONTEND_PORT)}"; FRONT_PORT="${FRONT_PORT:-5530}"
# where the UI listens: 127.0.0.1 (this machine only, default) or 0.0.0.0 (public, NO LOGIN). The backend always stays on 127.0.0.1.
env_val() { [ -f "$ROOT/backend/.env" ] && grep -E "^$1=" "$ROOT/backend/.env" | tail -1 | cut -d= -f2- | tr -d "[:space:]\"'" || true; }
UI_HOST="${AFM_HOST:-$(env_val AFM_HOST)}"; UI_HOST="${UI_HOST:-127.0.0.1}"
case "$UI_HOST" in 127.0.0.1|0.0.0.0|localhost) ;; *) echo "AFM_HOST must be 127.0.0.1 or 0.0.0.0 (got '$UI_HOST')"; exit 1 ;; esac
BASE_PATH="${AFM_BASE_PATH:-$(env_val AFM_BASE_PATH)}"; BASE_PATH="${BASE_PATH:-/acm/}"
HOME_PATH="/$(echo "$BASE_PATH" | sed 's#^/*##; s#/*$##')"; HOME_PATH="${HOME_PATH%/}/home"; [ "$BASE_PATH" = "/" ] && HOME_PATH="/"

pid_on() { ss -ltnpH "sport = :$1" 2>/dev/null | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2 || true; }
listening() { [ -n "$(ss -ltnH "sport = :$1" 2>/dev/null)" ]; }
is_ours() {  # a process we started from this folder (backend venv or frontend vite)
  local cwd; cwd="$(readlink "/proc/$1/cwd" 2>/dev/null || true)"
  [ "$cwd" = "$ROOT/backend" ] || [ "$cwd" = "$ROOT/frontend" ]
}

install() {
  if [ ! -x "$ROOT/backend/.venv/bin/python" ]; then
    python3 -m venv "$ROOT/backend/.venv"
  fi
  "$ROOT/backend/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
  (cd "$ROOT/frontend" && npm install --no-audit --no-fund)
}

# Always a fresh launch: stop whatever is on our ports first, then start both apps.
start() {
  [ -x "$ROOT/backend/.venv/bin/python" ] && [ -d "$ROOT/frontend/node_modules" ] || install
  # fail fast if another program holds a port (another app, another user, Docker...), before stopping the running ACFM
  for p in "$BACK_PORT" "$FRONT_PORT"; do
    local who; who="$(pid_on "$p")"
    if listening "$p" && { [ -z "$who" ] || ! is_ours "$who"; }; then
      echo "Port $p is used by another program${who:+ (pid $who: $(tr '\0' ' ' < /proc/$who/cmdline 2>/dev/null | cut -c1-80))}."
      [ -z "$who" ] && echo "  It belongs to another user or to Docker. See it with:  sudo ss -ltnp 'sport = :$p'"
      echo "  Stop that program, or choose another port, e.g.  AFM_FRONTEND_PORT=3020 ./start.sh"
      exit 1
    fi
  done
  stop
  # optional backend/.env (git-ignored): AFM_LLM_PROVIDER, ANTHROPIC_API_KEY, AFM_CLAUDE_MODEL, ...
  if [ -f "$ROOT/backend/.env" ]; then
    if grep -q "your-anthropic-api-key-here" "$ROOT/backend/.env"; then
      set -a; . <(grep -v '^ANTHROPIC_API_KEY=your-anthropic-api-key-here' "$ROOT/backend/.env"); set +a
    else
      set -a; . "$ROOT/backend/.env"; set +a
    fi
    echo "loaded backend/.env (values not shown)"
  fi
  echo "starting backend :$BACK_PORT (LLM tool: ${AFM_LLM_PROVIDER:-mock}) and frontend :$FRONT_PORT ..."
  (cd "$ROOT/backend" && AFM_LLM_PROVIDER="${AFM_LLM_PROVIDER:-mock}" setsid nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$BACK_PORT" \
    > "$LOGS/backend.log" 2>&1 < /dev/null &)
  (cd "$ROOT/frontend" && AFM_API_URL="http://127.0.0.1:$BACK_PORT" AFM_BASE_PATH="$BASE_PATH" setsid nohup npx vite --port "$FRONT_PORT" --host "$UI_HOST" --strictPort \
    > "$LOGS/frontend.log" 2>&1 < /dev/null &)
  local ready=""
  for _ in $(seq 1 60); do
    if curl -fsS -m 3 "http://127.0.0.1:$BACK_PORT/api/health" >/dev/null 2>&1 && curl -fsS -m 3 -o /dev/null "http://127.0.0.1:$FRONT_PORT" >/dev/null 2>&1; then ready=1; break; fi
    sleep 0.5
  done
  status
  if [ -n "$ready" ]; then
    echo "Open http://127.0.0.1:$FRONT_PORT$HOME_PATH   (logs in $LOGS)"
    if [ "$UI_HOST" = "0.0.0.0" ]; then
      ip="$(curl -fsS -m 2 http://checkip.amazonaws.com 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')"
      echo "PUBLIC: http://${ip:-<server-ip>}:$FRONT_PORT$HOME_PATH  (port $FRONT_PORT must be open in the firewall / security group)"
      echo "WARNING: no login. Anyone who reaches this address can use everything, including real-project mode"
      echo "         (it can clone repositories and run approved commands on this server) and your LLM credits."
    fi
  else
    echo "AFM did not come up within 30 s. Last log lines:"; tail -5 "$LOGS/backend.log" "$LOGS/frontend.log"; exit 1
  fi
}

stop() {
  # stop every server started from THIS folder, whatever port it uses (so a launch on a new port leaves no old copy behind);
  # never stop another program, even if it uses one of our ports
  local seen=" " stopped=""
  while read -r port pid; do
    case "$seen" in *" $pid "*) continue ;; esac; seen="$seen$pid "
    is_ours "$pid" || continue
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    kill -0 "$pid" 2>/dev/null && { kill -9 "$pid" 2>/dev/null || true; sleep 0.5; }
    echo "stopped :$port (pid $pid)"; stopped=1
  done < <(ss -ltnpH 2>/dev/null | while read -r _ _ _ addr _ users; do
             # listeners of other users / Docker show no pid: skip them (|| true: set -e must not end the scan)
             pid="$(grep -oE 'pid=[0-9]+' <<<"$users" | head -1 | cut -d= -f2 || true)"; [ -n "$pid" ] && echo "${addr##*:} $pid"; done || true)
  [ -n "$stopped" ] || echo "ACFM was not running"
  for p in "$BACK_PORT" "$FRONT_PORT"; do
    if listening "$p"; then local who; who="$(pid_on "$p")"; echo ":$p is used by another program${who:+ (pid $who)}, left running"; fi
  done
  return 0
}

status() {
  for p in "$BACK_PORT" "$FRONT_PORT"; do
    pid="$(pid_on "$p")"; [ -n "$pid" ] && echo ":$p up (pid $pid)" || echo ":$p down"
  done
  curl -fsS -m 5 "http://127.0.0.1:$BACK_PORT/api/llm/status" 2>/dev/null | sed 's/^/llm: /' || true; echo
}

tests() {
  (cd "$ROOT/backend" && .venv/bin/python -m pytest -q)
  (cd "$ROOT/frontend" && npm run build)
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) start ;;
  status) status ;;
  test) tests ;;
  install) install ;;
  *) echo "usage: $0 [start|stop|restart|status|test|install]"; exit 1 ;;
esac
