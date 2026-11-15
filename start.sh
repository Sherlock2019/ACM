#!/usr/bin/env bash
# AFM launcher:  ./start.sh [start|stop|restart|status|test|install]
#   start (default) and restart always stop running AFM servers first, then launch fresh.
#   Data (run history, simulated environment) is kept; use "Reset demo" in the UI to restore the scenario.
#   backend  → http://127.0.0.1:8530  (FastAPI)
#   frontend → http://127.0.0.1:5530  (Vite dev server, proxies /api to the backend)
# LLM tool:  mock by default.  Use Claude:  AFM_LLM_PROVIDER=claude ./start.sh restart
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACK_PORT="${AFM_BACKEND_PORT:-8530}"
FRONT_PORT="${AFM_FRONTEND_PORT:-5530}"
LOGS="$ROOT/logs"; mkdir -p "$LOGS"

pid_on() { ss -ltnpH "sport = :$1" 2>/dev/null | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2 || true; }

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
  (cd "$ROOT/frontend" && AFM_API_URL="http://127.0.0.1:$BACK_PORT" setsid nohup npx vite --port "$FRONT_PORT" --host 127.0.0.1 --strictPort \
    > "$LOGS/frontend.log" 2>&1 < /dev/null &)
  local ready=""
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:$BACK_PORT/api/health" >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:$FRONT_PORT" >/dev/null 2>&1; then ready=1; break; fi
    sleep 0.5
  done
  status
  if [ -n "$ready" ]; then
    echo "Open http://127.0.0.1:$FRONT_PORT   (logs in $LOGS)"
  else
    echo "AFM did not come up within 30 s. Last log lines:"; tail -5 "$LOGS/backend.log" "$LOGS/frontend.log"; exit 1
  fi
}

stop() {
  for p in "$BACK_PORT" "$FRONT_PORT"; do
    pid="$(pid_on "$p")"
    if [ -z "$pid" ]; then echo ":$p not running"; continue; fi
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do [ -z "$(pid_on "$p")" ] && break; sleep 0.25; done
    if [ -n "$(pid_on "$p")" ]; then kill -9 "$(pid_on "$p")" 2>/dev/null || true; sleep 0.5; fi
    echo "stopped :$p (pid $pid)"
  done
}

status() {
  for p in "$BACK_PORT" "$FRONT_PORT"; do
    pid="$(pid_on "$p")"; [ -n "$pid" ] && echo ":$p up (pid $pid)" || echo ":$p down"
  done
  curl -fsS "http://127.0.0.1:$BACK_PORT/api/llm/status" 2>/dev/null | sed 's/^/llm: /' || true; echo
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
