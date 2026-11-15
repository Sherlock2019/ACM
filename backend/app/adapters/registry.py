"""Which environment adapters exist. Only the three local simulations are implemented."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain.models import FutureAdapter
from .base import EnvironmentAdapter
from .inventory.adapter import InventoryAdapter
from .playground.adapter import PlaygroundAdapter
from .webapp.adapter import WebAppAdapter


TEMPLATES_DIR = Path(__file__).with_name("templates")


def simulation_templates(adapters: list[EnvironmentAdapter]) -> list[dict[str, Any]]:
    """One simulation template per use case: the three adapters plus templates without an adapter."""
    out = []
    for a in adapters:
        s = a._scenario.get("simulation")
        if s:
            out.append({**s, "template_id": a.environment_id, "adapter_id": a.environment_id, "status": "simulated",
                        "tagline": a.summary, "environment_type": "Simulated environment", "environment_name": a.name,
                        "mode": "plan", "target_identifier": "", "evidence": "", "source_note": ""})
    for f in sorted(TEMPLATES_DIR.glob("*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        out.append({**t, "adapter_id": ""})
    for t in out:
        assert len(t["thinking"]) == 16, f"template {t['template_id']} must have 16 steps"
    return out


def default_adapters() -> list[EnvironmentAdapter]:
    # display order: simplest example, main demonstration, business example
    return [PlaygroundAdapter(), WebAppAdapter(), InventoryAdapter()]


FUTURE_ADAPTERS = [
    FutureAdapter(name="AWS infrastructure", kind="cloud", status="not_implemented", note="No AWS adapter exists. AFM cannot inspect or change AWS resources."),
    FutureAdapter(name="SAP", kind="business system", status="not_implemented", note="No SAP adapter exists."),
    FutureAdapter(name="Real Python repository", kind="code", status="not_implemented", note="The web-app demo is fictional; no real repository is read."),
    FutureAdapter(name="Real web server", kind="infrastructure", status="not_implemented", note="No real server configuration is read or changed."),
    FutureAdapter(name="Spreadsheet", kind="document", status="not_implemented", note="No spreadsheet adapter exists."),
    FutureAdapter(name="Mobile application", kind="application", status="not_implemented", note="No mobile adapter exists."),
    FutureAdapter(name="Data readiness agent", kind="analysis", status="not_connected", note="Exists as a separate project (~/DataReady); not connected to AFM."),
]
