"""Pre-checks and the test runner for real-project mode.

Commands run as fixed argument lists (never through a shell), inside the workspace, with a reduced
environment (no secrets, temporary HOME), a timeout and an output cap. This REDUCES exposure; it is
NOT a sandbox: a test can still read the user's files and reach the network.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import time

from .models import CommandResult, PrecheckItem
from .workspace import git

TIMEOUT_S = 180
MAX_OUTPUT = 200_000
SHELLS = {"sh", "bash", "zsh", "dash", "fish", "ksh", "csh", "tcsh", "pwsh", "powershell", "cmd", "cmd.exe"}
FORBIDDEN_FIRST = {"sudo", "su", "doas", "gh", "ssh", "scp", "rsync", "curl", "wget", "rm", "dd", "mkfs", "chmod", "chown"}
SHELL_CHARS = re.compile(r"[|;&`$<>\n]")
KEEP_ENV = ("PATH", "LANG", "LC_ALL", "TERM", "TZ")
TEST_LINE = [re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+(\S+)"),  # pytest -rA summary
             re.compile(r"^\s*--- (PASS|FAIL|SKIP): (\S+)")]  # go test -v
MISSING = [re.compile(p) for p in (r"No module named ['\"]?([\w.]+)", r"command not found", r"ModuleNotFoundError", r"Cannot find module")]


def check_commands(commands: list[list[str]]) -> list[PrecheckItem]:
    items: list[PrecheckItem] = []
    if not commands:
        return [PrecheckItem(name="Test commands", status="FAIL", detail="Add at least one test command, so predictions can be measured.")]
    for i, argv in enumerate(commands):
        label = f"Command {i + 1}: {' '.join(argv)[:120]}"
        first = os.path.basename(argv[0]) if argv else ""
        if not argv or any((not a) or "\x00" in a for a in argv):
            items.append(PrecheckItem(name=label, status="FAIL", detail="Empty argument."))
        elif first in SHELLS:
            items.append(PrecheckItem(name=label, status="FAIL", detail="Shells are not allowed; give the program and its arguments directly."))
        elif first in FORBIDDEN_FIRST:
            items.append(PrecheckItem(name=label, status="FAIL", detail=f"'{first}' is not allowed in real-project tests (privileges, network or deletion)."))
        elif first == "git" and any(a in {"push", "remote", "config", "clean", "reset", "checkout"} for a in argv[1:]):
            items.append(PrecheckItem(name=label, status="FAIL", detail="git commands that push, reconfigure, reset or discard work are not allowed."))
        elif any(SHELL_CHARS.search(a) for a in argv):
            items.append(PrecheckItem(name=label, status="FAIL", detail="Shell characters (| ; & ` $ < >) are not interpreted and not allowed: commands run without a shell."))
        else:
            items.append(PrecheckItem(name=label, status="PASS", detail="Fixed argument list, run inside the workspace without a shell."))
    return items


def patch_paths(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        m = re.match(r"^diff --git a/(\S+) b/(\S+)", line)
        if m:
            paths += [m.group(1), m.group(2)]
        m = re.match(r"^(?:\+\+\+|---) (?:[ab]/)?(\S+)", line)
        if m and m.group(1) != "/dev/null":
            paths.append(m.group(1))
    return sorted(set(paths))


def check_patch(ws: str, patch: str) -> list[PrecheckItem]:
    if not patch.strip():
        return [PrecheckItem(name="Patch", status="FAIL", detail="Add the exact change as a unified diff (git diff format).")]
    paths = patch_paths(patch)
    bad = [p for p in paths if p.startswith("/") or ".." in p.split("/") or p == ".git" or p.startswith(".git/") or "\\" in p]
    items = [PrecheckItem(name="Patch stays inside the workspace", status="FAIL" if bad or not paths else "PASS",
                          detail=(f"Not allowed: {', '.join(bad)[:200]}" if bad else "No file paths found in the patch." if not paths
                                  else f"Changes {len(paths)} path(s): {', '.join(paths)[:300]}"))]
    if not bad and paths:
        p = git(["-C", ws, "apply", "--check", "--whitespace=nowarn", "-"], input_text=patch if patch.endswith("\n") else patch + "\n")
        items.append(PrecheckItem(name="Patch applies cleanly (git apply --check)", status="PASS" if p.returncode == 0 else "FAIL",
                                  detail="Applies to the recorded commit." if p.returncode == 0 else (p.stderr.strip()[:300] or "git apply --check failed.")))
    return items


def apply_patch(ws: str, patch: str) -> tuple[bool, str]:
    p = git(["-C", ws, "apply", "--whitespace=nowarn", "-"], input_text=patch if patch.endswith("\n") else patch + "\n")
    return p.returncode == 0, (p.stderr or "").strip()[:300]


def parse_tests(output: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in output.splitlines():
        for rx in TEST_LINE:
            m = rx.match(line)
            if m:
                word = m.group(1).upper()
                out[m.group(2)] = {"PASS": "passed", "PASSED": "passed", "FAIL": "failed", "FAILED": "failed", "ERROR": "error",
                                   "SKIP": "skipped", "SKIPPED": "skipped", "XFAIL": "xfail", "XPASS": "xpass"}[word]
    return out


def run(ws: str, argv: list[str], phase: str, timeout: int = TIMEOUT_S) -> CommandResult:
    env = {k: os.environ[k] for k in KEEP_ENV if k in os.environ}
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="acfm-home-") as home:
        env.update(HOME=home, CI="1", NO_COLOR="1", PYTHONDONTWRITEBYTECODE="1", GIT_TERMINAL_PROMPT="0", PIP_NO_INPUT="1", TMPDIR=home)
        try:
            proc = subprocess.Popen(argv, cwd=ws, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    start_new_session=True)
        except FileNotFoundError:
            return CommandResult(phase=phase, argv=argv, error=f"'{argv[0]}' is not installed or not on PATH.")
        except OSError as e:
            return CommandResult(phase=phase, argv=argv, error=f"Could not start the command: {e.strerror}.")
        timed_out = False
        try:
            raw, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            raw, _ = proc.communicate()
    text = raw[-MAX_OUTPUT:].decode(errors="replace") if raw else ""
    error = f"Timed out after {timeout} s." if timed_out else ""
    tests = parse_tests(text)
    if not error and proc.returncode != 0 and not tests and any(rx.search(text) for rx in MISSING):
        error = "A tool or dependency is missing (install the project's dependencies yourself; ACFM never installs them)."
    return CommandResult(phase=phase, argv=argv, exit_code=None if timed_out else proc.returncode, timed_out=timed_out,
                         duration_ms=int((time.monotonic() - t0) * 1000), output_tail=text[-6000:], tests=tests, error=error)
