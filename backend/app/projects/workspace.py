"""ACFM test workspaces: a separate copy of the user's project. The user's folder is never written to.

- Local Git project  → `git clone --no-hardlinks` of the folder, detached at its current commit.
                        Uncommitted changes are NOT copied (reported in the inspection).
- Local plain folder → file copy (heavy/dependency folders skipped), then a local git baseline commit.
- GitHub (public)    → `git clone --depth 1`, optional branch/tag or commit.

Every git call disables hooks and fsmonitor and never prompts for credentials. No dependency is installed
and no repository script runs while creating a workspace.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from ..domain.errors import AFMError

ROOT_DEFAULT = Path(__file__).resolve().parents[3] / "workspaces"
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".tox", "dist", "build", ".next", "target"}
MAX_COPY_BYTES = 300 * 1024 * 1024
MAX_COPY_FILES = 30000
GITHUB_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100}?)(?:\.git)?/?$")
REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def root() -> Path:
    r = Path(os.environ.get("AFM_WORKSPACES_DIR") or ROOT_DEFAULT).resolve()
    r.mkdir(parents=True, exist_ok=True)
    return r


def git_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="/bin/false", SSH_ASKPASS="/bin/false", GCM_INTERACTIVE="never", GIT_CONFIG_NOSYSTEM="1")
    return env


def git(args: list[str], cwd: str | Path | None = None, timeout: int = 60, input_text: str | None = None) -> subprocess.CompletedProcess:
    cmd = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "submodule.recurse=false", *args]
    try:
        return subprocess.run(cmd, cwd=cwd, env=git_env(), capture_output=True, text=True, timeout=timeout, input=input_text)
    except FileNotFoundError:
        raise AFMError("git_missing", "git is not installed on this machine.", 503)
    except subprocess.TimeoutExpired:
        raise AFMError("git_timeout", f"git took longer than {timeout} s.", 504)


def _ok(p: subprocess.CompletedProcess, what: str) -> str:
    if p.returncode != 0:
        msg = (p.stderr or p.stdout or "").strip().splitlines()[-1:] or ["unknown error"]
        raise AFMError("workspace_failed", f"{what} failed: {msg[0][:300]}", 400)
    return p.stdout.strip()


def _new_dir(name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", name)[:40] or "project"
    d = root() / f"{safe}-{uuid.uuid4().hex[:8]}"
    return d


def is_git_repo(path: Path) -> bool:
    p = git(["-C", str(path), "rev-parse", "--show-toplevel"], timeout=20)
    return p.returncode == 0 and Path(p.stdout.strip()).resolve() == path.resolve()


def fingerprint(path: Path, kind: str) -> str:
    """Read-only fingerprint of the user's folder (HEAD + status for git, file list for plain folders)."""
    h = hashlib.sha256()
    if kind == "git_clone":
        head = git(["--no-optional-locks", "-C", str(path), "rev-parse", "HEAD"], timeout=20).stdout.strip()
        status = git(["--no-optional-locks", "-C", str(path), "status", "--porcelain=v1"], timeout=60).stdout
        h.update(head.encode()); h.update(status.encode())
    else:
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for f in sorted(filenames):
                fp = Path(dirpath, f)
                try:
                    st = fp.lstat()
                except OSError:
                    continue
                h.update(f"{fp.relative_to(path)}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()[:24]


def validate_local(path_text: str) -> Path:
    if not path_text or "\x00" in path_text:
        raise AFMError("invalid_input", "Enter the absolute path of a project folder.", 400)
    p = Path(os.path.expanduser(path_text.strip()))
    if not p.is_absolute():
        raise AFMError("invalid_input", "The project path must be absolute (for example /home/you/my-project).", 400)
    p = p.resolve()
    if not p.is_dir():
        raise AFMError("not_found", "That folder does not exist or is not readable.", 404)
    if p == Path("/") or p == Path.home().resolve():
        raise AFMError("invalid_input", "Choose a project folder, not the whole disk or home folder.", 400)
    r = root()
    if p == r or r in p.parents:
        raise AFMError("invalid_input", "That folder is inside the ACFM test workspace already.", 400)
    return p


def validate_github(url: str, ref: str) -> tuple[str, str, str]:
    url = (url or "").strip()
    if "@" in url.split("github.com")[0] or re.search(r"https://[^/]*@", url):
        raise AFMError("invalid_input", "Do not put credentials in the URL. Phase 1 supports public repositories only.", 400)
    m = GITHUB_RE.match(url)
    if not m:
        raise AFMError("invalid_input", "Use a public GitHub URL like https://github.com/owner/repository.", 400)
    ref = (ref or "").strip()
    if ref and (not REF_RE.match(ref) or ref.startswith("-") or ".." in ref):
        raise AFMError("invalid_input", "The branch, tag or commit contains characters that are not allowed.", 400)
    return f"https://github.com/{m.group(1)}/{m.group(2)}.git", m.group(2), ref


def create_from_local(path_text: str) -> dict:
    src = validate_local(path_text)
    dest = _new_dir(src.name)
    if is_git_repo(src):
        head = _ok(git(["--no-optional-locks", "-C", str(src), "rev-parse", "HEAD"], timeout=20), "Reading the project's current commit")
        _ok(git(["clone", "--no-hardlinks", "--no-recurse-submodules", "-q", "--", str(src), str(dest)], timeout=300), "Copying the project (git clone)")
        if _ok(git(["-C", str(dest), "rev-parse", "HEAD"]), "Reading the copy") != head:
            _ok(git(["-C", str(dest), "checkout", "-q", "--detach", head]), "Checking out the project's current commit")
        dirty = git(["--no-optional-locks", "-C", str(src), "status", "--porcelain=v1"], timeout=60).stdout.splitlines()
        return dict(workspace=str(dest), workspace_kind="git_clone", commit=head, name=src.name, origin=str(src),
                    origin_fingerprint=fingerprint(src, "git_clone"), uncommitted=len(dirty))
    # plain folder: copy with limits, then a local baseline commit in the copy only
    total, count = 0, 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            count += 1
            try:
                total += Path(dirpath, f).lstat().st_size
            except OSError:
                pass
            if count > MAX_COPY_FILES or total > MAX_COPY_BYTES:
                raise AFMError("too_large", "The folder is too large to copy (limit 30,000 files / 300 MB, dependency folders excluded).", 400)
    shutil.copytree(src, dest, symlinks=True, ignore=shutil.ignore_patterns(*SKIP_DIRS))
    _ok(git(["init", "-q", "-b", "acfm-baseline", str(dest)]), "Creating the baseline")
    _ok(git(["-C", str(dest), "add", "-A"], timeout=120), "Creating the baseline")
    _ok(git(["-C", str(dest), "-c", "user.name=ACFM", "-c", "user.email=acfm@localhost", "-c", "commit.gpgsign=false",
             "commit", "-q", "--allow-empty", "-m", "ACFM baseline copy"], timeout=120), "Creating the baseline")
    head = _ok(git(["-C", str(dest), "rev-parse", "HEAD"]), "Reading the copy")
    return dict(workspace=str(dest), workspace_kind="folder_copy", commit=head, name=src.name, origin=str(src),
                origin_fingerprint=fingerprint(src, "folder_copy"), uncommitted=0)


def create_from_github(url: str, ref: str = "") -> dict:
    clone_url, name, ref = validate_github(url, ref)
    dest = _new_dir(name)
    args = ["clone", "--depth", "1", "--no-recurse-submodules", "-q"]
    if ref and not SHA_RE.match(ref):
        args += ["--branch", ref]
    p = git(args + ["--", clone_url, str(dest)], timeout=300)
    if p.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        err = (p.stderr or "").lower()
        if "not found" in err or "authentication" in err or "could not read username" in err or "terminal prompts disabled" in err:
            raise AFMError("not_found", "Repository not found or not public. Phase 1 supports public GitHub repositories only.", 404)
        if "remote branch" in err:
            raise AFMError("not_found", f"Branch or tag '{ref}' was not found.", 404)
        raise AFMError("workspace_failed", "Cloning from GitHub failed (network or repository error).", 400)
    if ref and SHA_RE.match(ref):
        f = git(["-C", str(dest), "fetch", "-q", "--depth", "1", "origin", ref], timeout=180)
        c = git(["-C", str(dest), "checkout", "-q", "--detach", "FETCH_HEAD"]) if f.returncode == 0 else f
        if c.returncode != 0:
            shutil.rmtree(dest, ignore_errors=True)
            raise AFMError("not_found", f"Commit '{ref}' could not be fetched from GitHub.", 404)
    head = _ok(git(["-C", str(dest), "rev-parse", "HEAD"]), "Reading the clone")
    return dict(workspace=str(dest), workspace_kind="github_clone", commit=head, name=name, origin=url.strip(), origin_fingerprint="", uncommitted=0)


def workspace_state(ws: str) -> tuple[str, bool]:
    """(HEAD commit, clean?) of a workspace, used by the recheck before execution."""
    head = git(["-C", ws, "rev-parse", "HEAD"]).stdout.strip()
    status = git(["-C", ws, "status", "--porcelain=v1"]).stdout.strip()
    return head, status == ""


def remove(ws: str) -> bool:
    """Delete a workspace, only ever inside the ACFM workspace root."""
    p = Path(ws).resolve()
    r = root()
    if p == r or r not in p.parents:
        raise AFMError("forbidden", "Refusing to delete a folder outside the ACFM test workspace.", 403)
    if p.exists():
        shutil.rmtree(p)
        return True
    return False
