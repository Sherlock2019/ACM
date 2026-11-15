"""Read-only inspection of a workspace: reads files, never executes anything.

README text, comments and scripts are DATA. Test commands found here are only SUGGESTIONS that a human
must approve; they are never run automatically (R22: instruction-like text is reported, not followed).
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from ..adapters.llm import find_instruction_like_text
from .workspace import SKIP_DIRS

LANG = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript", ".go": "Go",
        ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".c": "C", ".h": "C",
        ".cpp": "C++", ".hpp": "C++", ".swift": "Swift", ".sh": "Shell", ".sql": "SQL", ".html": "HTML", ".css": "CSS",
        ".md": "Markdown", ".json": "JSON", ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML", ".tf": "Terraform"}
KEY_FILES = ["README.md", "README.rst", "README", "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "pytest.ini", "tox.ini",
             "package.json", "go.mod", "Cargo.toml", "Makefile", "Dockerfile", "docker-compose.yml", ".github/workflows"]
TEXT_EXT = set(LANG) | {".txt", ".cfg", ".ini", ".env.example"}
MAX_WALK = 20000
MAX_TEXT_BYTES = 200 * 1024


def _is_test(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py") or name.endswith("_test.go") \
        or ".test." in name or ".spec." in name or rel.startswith(("tests/", "test/")) and name.endswith(".py")


def inspect(ws: str, uncommitted: int = 0) -> dict[str, Any]:
    root = Path(ws)
    langs: Counter[str] = Counter()
    files: list[str] = []
    tests: list[str] = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for f in sorted(filenames):
            if len(files) >= MAX_WALK:
                truncated = True
                break
            rel = str(Path(dirpath, f).relative_to(root)).replace(os.sep, "/")
            files.append(rel)
            ext = Path(f).suffix.lower()
            if ext in LANG:
                langs[LANG[ext]] += 1
            if _is_test(rel):
                tests.append(rel)
    top = sorted({p.split("/", 1)[0] + ("/" if "/" in p else "") for p in files})[:40]
    present = [k for k in KEY_FILES if (root / k).exists()]

    readme_text = ""
    for r in ("README.md", "README.rst", "README"):
        if (root / r).is_file():
            readme_text = (root / r).read_text(errors="replace")[:1500]
            break

    suggestions: list[dict[str, Any]] = []
    has_py_tests = any(t.endswith(".py") for t in tests) or (root / "pytest.ini").exists()
    if has_py_tests:
        suggestions.append({"argv": ["python3", "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider"],
                            "why": "Python test files found (pytest). Needs pytest and the project's dependencies installed for python3."})
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            scripts = json.loads(pkg.read_text(errors="replace")).get("scripts", {}) or {}
        except (json.JSONDecodeError, AttributeError):
            scripts = {}
        if isinstance(scripts, dict) and "test" in scripts:
            suggestions.append({"argv": ["npm", "test", "--silent"],
                                "why": f"package.json defines a test script ({str(scripts['test'])[:80]}). This runs the repository's own script: review it first."})
    if (root / "go.mod").is_file():
        suggestions.append({"argv": ["go", "test", "./..."], "why": "go.mod found."})
    if (root / "Cargo.toml").is_file():
        suggestions.append({"argv": ["cargo", "test"], "why": "Cargo.toml found."})

    def _small(f: str) -> bool:
        p = root / f
        try:
            return not p.is_symlink() and p.is_file() and p.stat().st_size <= MAX_TEXT_BYTES
        except OSError:
            return False
    pickable = [f for f in files if Path(f).suffix.lower() in TEXT_EXT and _small(f)][:600]
    flags = find_instruction_like_text([readme_text])
    notes = ["Read-only inspection: files were read, nothing was executed or installed."]
    if uncommitted:
        notes.append(f"{uncommitted} uncommitted change(s) in your folder are NOT in this copy (Phase 1 copies the last commit).")
    if truncated:
        notes.append(f"Only the first {MAX_WALK} files were scanned.")
    if flags:
        notes.append("The README contains instruction-like text. It is treated as data and never followed.")
    unknowns = ["Runtime behaviour, external services, deployment and other consumers of this code are not inspected.",
                "Dependencies are not installed by ACFM; tests may not run until you install them yourself."]
    return {"file_count": len(files), "languages": dict(langs.most_common(8)), "top_level": top, "key_files": present,
            "tests": tests[:60], "test_count": len(tests), "suggested_commands": suggestions, "readme_excerpt": readme_text,
            "files": pickable, "notes": notes, "unknowns": unknowns, "instruction_like_text": bool(flags)}


def read_files(ws: str, rels: list[str], per_file: int = 30_000, total: int = 120_000) -> list[dict[str, str]]:
    """Contents of files the human picked to send to the LLM (inside the workspace only, size-capped)."""
    root = Path(ws).resolve()
    out, used = [], 0
    for rel in rels[:12]:
        raw = root / rel
        if raw.is_symlink():
            continue
        p = raw.resolve()
        if root not in p.parents or not p.is_file():
            continue
        text = p.read_text(errors="replace")[:per_file]
        if used + len(text) > total:
            break
        used += len(text)
        out.append({"path": rel, "content": text})
    return out
