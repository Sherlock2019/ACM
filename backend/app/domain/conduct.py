"""AFM's permanent rules of conduct (R01–R32).

They are global (every environment), read-only at runtime and pinned by a SHA-256 of their content.
If the rules file is edited, weakened or truncated without also updating CONDUCT_SHA256 here,
the backend refuses to start (rule R10: a rule change is a separate human-controlled operation).
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from .models import ConductRules, Rule

CONDUCT_PATH = Path(__file__).resolve().parent.parent / "config" / "conduct_rules.json"
CONDUCT_SHA256 = "2237845defb55953abf220f377e51ac24abb74afbd899a42803a569f668aabbd"
EXPECTED_IDS = [f"R{i:02d}" for i in range(1, 33)]


class ConductIntegrityError(RuntimeError):
    pass


def conduct_hash(rules: list[Rule]) -> str:
    payload = [{"id": r.id, "title": r.title, "text": r.text} for r in rules]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@lru_cache(maxsize=1)
def load_conduct() -> ConductRules:
    c = ConductRules.model_validate(json.loads(CONDUCT_PATH.read_text(encoding="utf-8")))
    ids = [r.id for r in c.rules]
    if ids != EXPECTED_IDS or not c.permanent:
        raise ConductIntegrityError("AFM rules of conduct are incomplete or out of order (expected R01–R32, permanent).")
    if conduct_hash(c.rules) != CONDUCT_SHA256:
        raise ConductIntegrityError(
            "AFM rules of conduct changed without a human-controlled update of CONDUCT_SHA256 (rule R10). Refusing to start."
        )
    return c


def rules_version() -> str:
    """Identifies exactly which global rules an assessment or use case was made under."""
    return f"conduct-{CONDUCT_SHA256[:12]}"


def rule_text(rule_id: str) -> str:
    r = next((x for x in load_conduct().rules if x.id == rule_id), None)
    return f"{rule_id} {r.title}" if r else rule_id
