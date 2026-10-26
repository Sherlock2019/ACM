#!/usr/bin/env bash
# Start the visual dashboard (it lives in the MLM repository) and print where to open it.
#
#   ./dash.sh            start API + dashboard, print the local and public URLs
#   ./dash.sh stop       stop them
#   ./dash.sh status     check them
#
# MLM is looked for at $SLM_DIR, ../SLM or ../NPLM-Next-Phrase-language-model-.
# The dashboard listens on 0.0.0.0:$SPLM_WEB_PORT (3010); on EC2, open that port in
# the security group and keep the API port (8001) closed.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_PORT="${SPLM_WEB_PORT:-3010}"

find_mlm() {
    for dir in "${SLM_DIR:-}" "$ROOT/../SLM" "$ROOT/../NPLM-Next-Phrase-language-model-"; do
        if [[ -n "$dir" && -x "$dir/start.sh" && -d "$dir/web" ]]; then
            (cd "$dir" && pwd)
            return 0
        fi
    done
    return 1
}

public_ip() {
    # EC2 instance metadata (IMDSv2), then a generic fallback. Short timeouts: off EC2 this just fails.
    local token ip
    token="$(curl -s --max-time 1 -X PUT http://169.254.169.254/latest/api/token \
        -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' 2>/dev/null || true)"
    if [[ -n "$token" ]]; then
        ip="$(curl -s --max-time 1 -H "X-aws-ec2-metadata-token: $token" \
            http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
    fi
    [[ "${ip:-}" =~ ^[0-9.]+$ ]] || ip="$(curl -s --max-time 3 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"
    [[ "${ip:-}" =~ ^[0-9.]+$ ]] && echo "$ip"
}

MLM="$(find_mlm)" || {
    echo "The dashboard is part of MLM, which was not found next to ACM." >&2
    echo "Clone it with: git clone git@github.com:Sherlock2019/NPLM-Next-Phrase-language-model-.git \"$ROOT/../SLM\"" >&2
    echo "or set SLM_DIR to an existing checkout." >&2
    exit 1
}

case "${1:-start}" in
    stop | status)
        exec "$MLM/start.sh" "$1"
        ;;
    start)
        # Live text on /multimodal needs ACM inside MLM's environment; Demo mode works without it.
        if [[ -x "$MLM/.venv/bin/python" ]] && ! "$MLM/.venv/bin/python" -c "import acm" 2>/dev/null; then
            echo "installing ACM into MLM's environment (enables Live text on /multimodal)"
            "$MLM/.venv/bin/python" -m pip install --quiet -e "$ROOT" || echo "warning: ACM install failed; /multimodal stays in Demo mode" >&2
        fi
        SPLM_NO_OPEN="${SPLM_NO_OPEN:-1}" "$MLM/start.sh" start
        echo
        echo "Dashboard:         http://127.0.0.1:$WEB_PORT"
        echo "Multimodal demo:   http://127.0.0.1:$WEB_PORT/multimodal"
        if ip="$(public_ip)"; then
            echo "From elsewhere:    http://$ip:$WEB_PORT/multimodal   (needs inbound TCP $WEB_PORT open)"
        fi
        echo "Stop with: ./dash.sh stop"
        ;;
    *)
        echo "usage: $0 {start|stop|status}" >&2
        exit 2
        ;;
esac
