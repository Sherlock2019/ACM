"""Environment adapter interface.

The generic AFM core (engine/) talks to environments ONLY through this interface. All business-specific
objects, actions, simulation rules, goal parsing and success criteria live in an adapter.

An adapter that cannot inspect, simulate or execute declares it in `capabilities`; the core then reports
"unsupported" instead of pretending. Every adapter must label evidence honestly and must never claim
that its catalog contains every real dependency.
"""
from __future__ import annotations

import copy
import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..domain.models import (
    CheckStatus,
    Consequence,
    EnvObject,
    Evidence,
    GoalCriterion,
    GoalSpec,
    Plan,
    Relationship,
    Rule,
    SimulationResult,
    ToolSpec,
    now_iso,
)
from ..engine.environment import EnvState


class AdapterError(Exception):
    """Raised by simulate_action when an action cannot be applied. `code` is machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class EnvironmentAdapter(ABC):
    # --- identity (set by subclasses) ---------------------------------------------------------
    environment_id: str
    name: str
    adapter_name: str
    kind: str = "simulated"
    summary: str = ""
    connection_status: str = "Local simulation. Not connected to any real system."
    capabilities: dict[str, bool] = {"inspect": True, "simulate": True, "execute": True}
    scenario_path: Path

    # error codes from simulate_action that are definite rule violations: code -> rule label
    error_rules: dict[str, str] = {}

    def __init__(self) -> None:
        self._scenario = json.loads(self.scenario_path.read_text(encoding="utf-8"))

    # --- static description (from the scenario file) ------------------------------------------
    def describe_environment(self) -> dict[str, Any]:
        return {"environment_id": self.environment_id, "name": self.name, "kind": self.kind,
                "adapter": self.adapter_name, "summary": self.summary, "connection_status": self.connection_status,
                "capabilities": dict(self.capabilities), "limitations": self.limitations()}

    def rules(self) -> list[Rule]:
        return [Rule.model_validate(r) for r in self._scenario.get("rules", [])]

    def tools(self) -> list[ToolSpec]:
        return [ToolSpec.model_validate({**t, "scope": "environment"}) for t in self._scenario.get("tools", [])]

    def demo_goals(self) -> list[str]:
        return list(self._scenario.get("demo_goals", []))

    def definitions(self) -> list[str]:
        return list(self._scenario.get("definitions", []))

    def limitations(self) -> list[str]:
        return list(self._scenario.get("limitations", []))

    def layout(self) -> dict[str, list[float]]:
        return dict(self._scenario.get("layout", {}))

    def initial_state(self) -> EnvState:
        ts = now_iso()
        objs = []
        for o in self._scenario["objects"]:
            o = copy.deepcopy(o)
            o["last_observed"] = ts if o["evidence"] != Evidence.unknown.value else None
            objs.append(EnvObject.model_validate(o))
        rels = [Relationship.model_validate(r) for r in self._scenario["relationships"]]
        return EnvState(objects={o.id: o for o in objs}, relationships=rels)

    # --- helpers for subclasses ----------------------------------------------------------------
    def goal_id(self, text: str) -> str:
        return "g-" + hashlib.sha256(f"{self.environment_id}:{text.strip().lower()}".encode()).hexdigest()[:8]

    def unsupported(self, text: str, why: str, clarification: str | None = None, missing: list[str] | None = None) -> GoalSpec:
        forms = self._scenario.get("goal_forms", [])
        return GoalSpec(
            goal_id=self.goal_id(text), environment_id=self.environment_id, text=text, supported=False,
            explanation=why,
            clarification_needed=clarification or (("Try one of: " + " · ".join(forms)) if forms else None),
            missing_information=missing or [],
        )

    # --- behavior (implemented by each adapter) ------------------------------------------------
    @abstractmethod
    def interpret_goal(self, text: str, state: EnvState) -> GoalSpec:
        """Map goal text to structured success criteria (and the R30 pre-check), or report unsupported."""

    @abstractmethod
    def propose_plans(self, goal: GoalSpec, state: EnvState) -> list[Plan]:
        """Deterministic candidate plans for a supported goal."""

    @abstractmethod
    def simulate_action(self, action, state: EnvState, step: int) -> list[Consequence]:
        """Apply ONE state-changing action to `state` (a copy) and return its consequences. Raise AdapterError."""

    def connected_effects(self, before: EnvState, after: EnvState, plan: Plan, step: int) -> list[Consequence]:
        """Effects computed once on the final predicted state (e.g. derived reachability). Default: none."""
        return []

    @abstractmethod
    def evaluate_criterion(self, criterion: GoalCriterion, predicted: EnvState) -> tuple[CheckStatus, str]:
        """Judge one success criterion against the predicted state."""

    def rule_checks(self, plan: Plan, sim: SimulationResult, predicted: EnvState) -> list[tuple[CheckStatus, str]]:
        """Environment-specific rule checks on a feasible prediction. Default: none."""
        return []

    def measure(self, state: EnvState, object_id: str, key: str) -> Any:
        """Re-measure an observable value after execution. Raise KeyError if it cannot be measured."""
        raise KeyError(key)

    def mock_llm_proposals(self) -> list[dict[str, Any]]:
        """Canned proposals for the offline mock LLM (deliberately includes invalid ones)."""
        return list(self._scenario.get("mock_llm_proposals", []))
