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

MLM_REPO="${MLM_REPO:-https://github.com/Sherlock2019/NPLM-Next-Phrase-language-model-.git}"

find_mlm() {
    for dir in "${SLM_DIR:-}" "$ROOT/../SLM" "$ROOT/../NPLM-Next-Phrase-language-model-"; do
        if [[ -n "$dir" && -f "$dir/pyproject.toml" && -d "$dir/web" ]]; then
            (cd "$dir" && pwd)
            return 0
        fi
    done
    # A fresh machine (e.g. EC2): MLM is public, so clone it over HTTPS (no SSH key needed).
    local target="${SLM_DIR:-$ROOT/../SLM}"
    if [[ ! -e "$target" ]] && command -v git > /dev/null; then
        echo "MLM (the meaning layer and the dashboard) was not found; cloning it into $target" >&2
        if git clone --quiet "$MLM_REPO" "$target" >&2; then
            (cd "$target" && pwd)
            return 0
        fi
    fi
    echo "MLM (the meaning layer and the dashboard) was not found next to ACM." >&2
    echo "Clone it with: git clone $MLM_REPO \"$target\"" >&2
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

wait_ports_free() {
    for _ in $(seq 1 20); do  # let stopped servers release their ports
        curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$WEB_PORT/" \
            || curl -s -o /dev/null --max-time 1 "http://127.0.0.1:8001/health" || return 0
        sleep 1
    done
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
        echo "   refreshed web/public/demo/demo_results.json, inference_suite.json and docs/demo/tabletop_report.html"
    else
        echo "   warning: could not refresh; the dashboard uses the bundled results" >&2
    fi

    echo "== 4/4 MLM API + dashboard (ACM mode: / opens the ACM demo)"
    # The mode is fixed when the dashboard starts, so a running one is restarted in ACM mode.
    if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$WEB_PORT/"; then
        "$MLM/start.sh" stop > /dev/null
        wait_ports_free
    fi
    # Let the dev server serve its client code to this machine's public IP and LAN address too.
    local origins
    origins="$(public_ip || true),$(hostname -I 2>/dev/null | tr ' ' ',')"
    SPLM_ALLOWED_DEV_ORIGINS="${SPLM_ALLOWED_DEV_ORIGINS:-$origins}" \
        NEXT_PUBLIC_APP_MODE=acm SPLM_NO_OPEN="${SPLM_NO_OPEN:-1}" "$MLM/start.sh" start
    # MLM's launcher moves to the next free port when the default is taken; report the real one.
    local actual
    actual="$(grep -Eo 'Local: +http://localhost:[0-9]+' "$MLM/logs/web.log" 2>/dev/null | tail -1 | grep -Eo '[0-9]+$' || true)"
    [[ -n "$actual" ]] && WEB_PORT="$actual"

    echo
    echo "POC is running:"
    echo "  Home (start here)    http://127.0.0.1:$WEB_PORT/            (every action has consequences: choose what to explore)"
    echo "  Tour                 http://127.0.0.1:$WEB_PORT/acm/tour    (how ACM works · vs an LLM · text/image/video)"
    echo "  ACM demo             http://127.0.0.1:$WEB_PORT/acm        (phrase · image · video, one Run Demo button)"
    echo "  What happens next?   http://127.0.0.1:$WEB_PORT/acm/inference   (53 actions, 280+ answers with reasoning)"
    echo "  Image / Video Chat   http://127.0.0.1:$WEB_PORT/acm/scene  (recognise objects, simulate, ask about any object)"
    echo "  Multimodal details   http://127.0.0.1:$WEB_PORT/multimodal"
    echo "  Dashboard            http://127.0.0.1:$WEB_PORT"
    if ip="$(public_ip)"; then
        echo "  From elsewhere       http://$ip:$WEB_PORT/   (needs inbound TCP $WEB_PORT open)"
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
        wait_ports_free
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
