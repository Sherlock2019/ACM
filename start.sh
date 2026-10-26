#!/usr/bin/env bash
# ACM launcher: sets up the virtualenv on first run, then runs the CLI.
#
#   ./start.sh                         interactive prompt (type an action, get its consequences)
#   ./start.sh predict "..." [opts]    any acm subcommand: predict | graph | remember | similar
#   ./start.sh test                    run the test suite
#   ./start.sh setup                   (re)install dependencies
#
# MLM (package splm) is installed from $SLM_DIR, default ../SLM.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
SLM_DIR="${SLM_DIR:-$ROOT/../SLM}"
PYTHON="${PYTHON:-python3}"

setup() {
    if [[ ! -x "$VENV/bin/python" ]]; then
        echo "Creating virtualenv in $VENV"
        "$PYTHON" -m venv "$VENV"
    fi
    if [[ ! -d "$SLM_DIR" ]]; then
        echo "MLM not found at $SLM_DIR." >&2
        echo "Clone it with: git clone git@github.com:Sherlock2019/NPLM-Next-Phrase-language-model-.git \"$SLM_DIR\"" >&2
        echo "or set SLM_DIR to an existing checkout." >&2
        exit 1
    fi
    "$VENV/bin/python" -m pip install --upgrade pip >/dev/null
    "$VENV/bin/python" -m pip install -e "$SLM_DIR[parse]" -e "$ROOT[dev]"
}

if ! [[ -x "$VENV/bin/python" ]] || ! "$VENV/bin/python" -c "import acm, splm" 2>/dev/null; then
    setup
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

case "${1:-}" in
    setup)
        setup
        ;;
    test)
        shift
        exec pytest "$@"
        ;;
    "")
        echo "ACM interactive. Enter an action; prefix context lines with '+'. Empty line or Ctrl-D to quit."
        echo "(For the visual dashboard and the multimodal demo, run ./dash.sh instead.)"
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
        exec python -m acm.cli "$@"
        ;;
esac
