"""Loads AFM's generic identity, tools and permissions from the versioned config file (read-only)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .models import AFMProfile

PROFILE_PATH = Path(__file__).resolve().parent.parent / "config" / "afm_profile.json"


@lru_cache(maxsize=1)
def load_profile() -> AFMProfile:
    return AFMProfile.model_validate(json.loads(PROFILE_PATH.read_text(encoding="utf-8")))
