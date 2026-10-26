#!/usr/bin/env bash
# ACM launcher. With no arguments it starts the whole POC:
#
#   ./start.sh                         set up ACM, refresh the demo results, start the MLM API +
#                                      dashboard (detached), print the URLs (incl. public IP)
#   ./start.sh stop | status | restart the API + dashboard
#   ./start.sh cli                     interactive prompt (type an action, get its consequences)
#   ./start.sh predict "..." [opts]    any acm subcommand: predict | graph | remember | similar | demo
#   ./start.sh test                    run the test suite
#   ./start.sh setup                   (re)install dependencies
#
# MLM (package splm, and the dashboard) is found at $SLM_DIR, ../SLM or
# ../NPLM-Next-Phrase-language-model-. The dashboard listens on 0.0.0.0:$SPLM_WEB_PORT
# (3010); on EC2 open that port in the security group and keep the API port (8001) closed.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
PYTHON="${PYTHON:-python3}"
WEB_PORT="${SPLM_WEB_PORT:-3010}"

find_mlm() {
    for dir in "${SLM_DIR:-}" "$ROOT/../SLM" "$ROOT/../NPLM-Next-Phrase-language-model-"; do
        if [[ -n "$dir" && -f "$dir/pyproject.toml" && -d "$dir/web" ]]; then
            (cd "$dir" && pwd)
            return 0
        fi
    done
    echo "MLM (the meaning layer and the dashboard) was not found next to ACM." >&2
    echo "Clone it with: git clone git@github.com:Sherlock2019/NPLM-Next-Phrase-language-model-.git \"$ROOT/../SLM\"" >&2
    echo "or set SLM_DIR to an existing checkout." >&2
    return 1
}

MLM="$(find_mlm)" || exit 1

setup() {
    if [[ ! -x "$VENV/bin/python" ]]; then
        echo "Creating virtualenv in $VENV"
        "$PYTHON" -m venv "$VENV"
    fi
    "$VENV/bin/python" -m pip install --upgrade pip >/dev/null
    "$VENV/bin/python" -m pip install -e "$MLM[parse]" -e "$ROOT[dev]"
}

public_ip() {
    # EC2 instance metadata (IMDSv2), then a generic lookup. Short timeouts: off EC2 this just fails.
    local token ip=""
    token="$(curl -s --max-time 1 -X PUT http://169.254.169.254/latest/api/token \
        -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' 2>/dev/null || true)"
    if [[ -n "$token" ]]; then
        ip="$(curl -s --max-time 1 -H "X-aws-ec2-metadata-token: $token" \
            http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
    fi
    [[ "$ip" =~ ^[0-9.]+$ ]] || ip="$(curl -s --max-time 3 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"
    [[ "$ip" =~ ^[0-9.]+$ ]] && echo "$ip"
}

start_poc() {
    echo "== 1/4 ACM environment: ready ($VENV)"

    echo "== 2/4 Live text: ACM inside MLM's environment"
    if [[ -x "$MLM/.venv/bin/python" ]]; then
        if "$MLM/.venv/bin/python" -c "import acm" 2>/dev/null; then
            echo "   already installed"
        else
            "$MLM/.venv/bin/python" -m pip install --quiet -e "$ROOT" \
                && echo "   installed" || echo "   warning: install failed; /multimodal stays in Demo mode" >&2
        fi
    else
        echo "   MLM's environment is created in step 4; Live text is enabled on the next ./start.sh"
    fi

    echo "== 3/4 Demo results from the current ACM code"
    if python -m acm.cli demo --json "$MLM/web/public/demo/demo_results.json" > /dev/null; then
        echo "   refreshed web/public/demo/demo_results.json and docs/demo/tabletop_report.html"
    else
        echo "   warning: could not refresh; the dashboard uses the bundled results" >&2
    fi

    echo "== 4/4 MLM API + dashboard"
    SPLM_NO_OPEN="${SPLM_NO_OPEN:-1}" "$MLM/start.sh" start

    echo
    echo "POC is running:"
    echo "  Dashboard            http://127.0.0.1:$WEB_PORT"
    echo "  Multimodal demo      http://127.0.0.1:$WEB_PORT/multimodal"
    if ip="$(public_ip)"; then
        echo "  From elsewhere       http://$ip:$WEB_PORT/multimodal   (needs inbound TCP $WEB_PORT open)"
    fi
    echo "  Static report        $ROOT/docs/demo/tabletop_report.html"
    echo "  ACM prompt           ./start.sh cli"
    echo "  Stop                 ./start.sh stop"
}

case "${1:-start}" in
    stop | status)
        exec "$MLM/start.sh" "$1"
        ;;
esac

if ! [[ -x "$VENV/bin/python" ]] || ! "$VENV/bin/python" -c "import acm, splm" 2>/dev/null; then
    setup
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# Parsing new text needs Stanza (with PyTorch). MLM's environment usually has it already;
# when it also has ACM, use it for the CLI instead of installing the parser twice.
if ! python -c "import stanza" 2>/dev/null && [[ -x "$MLM/.venv/bin/python" ]] \
    && "$MLM/.venv/bin/python" -c "import acm, stanza" 2>/dev/null; then
    python() { "$MLM/.venv/bin/python" "$@"; }
fi

case "${1:-start}" in
    start)
        start_poc
        ;;
    restart)
        "$MLM/start.sh" stop
        sleep 1
        start_poc
        ;;
    setup)
        setup
        ;;
    test)
        shift
        exec pytest "$@"
        ;;
    cli)
        echo "ACM interactive. Enter an action; prefix context lines with '+'. Empty line or Ctrl-D to quit."
        context=()
        while IFS= read -r -p "acm> " line; do
            [[ -z "$line" ]] && break
            if [[ "$line" == +* ]]; then
                context+=(--context "${line#+}")
                echo "  (context added: $(( ${#context[@]} / 2 )) line(s) for the next action)"
                continue
            fi
            python -m acm.cli predict "$line" "${context[@]}" || true
            context=()
        done
        ;;
    *)
        python -m acm.cli "$@"  # not exec: `python` may be the function above
        ;;
esac
