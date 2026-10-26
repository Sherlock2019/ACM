#!/usr/bin/env bash
# Alias for ./start.sh, which now starts the whole POC (dashboard included).
#   ./dash.sh [start|stop|status|restart]
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/start.sh" "${1:-start}"
