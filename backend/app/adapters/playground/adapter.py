"""Generic Object Playground: Input A → Processor B (×2) → Display C. The simplest AFM example."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...domain.models import Action, CheckStatus, Consequence, GoalCriterion, GoalSpec, PermissionClass, Plan, SimulationResult
from ...engine.environment import EnvState
from ..base import AdapterError, EnvironmentAdapter

S = CheckStatus
RULE_SET = "PLAY-1 set_value: the input object holds the new value"
RULE_PROC = "PLAY-2 processor.input = A.value; processor.output = input × factor (factor 2)"
RULE_DISP = "PLAY-3 display.shown = processor.output (refreshes immediately)"
_OTHER_DOMAIN = r"\b(order|warehouse|inventory|stock|port|server|database|monitor)\b"


class PlaygroundAdapter(EnvironmentAdapter):
    environment_id = "object-playground"
    name = "Generic Object Playground"
    adapter_name = "ObjectPlaygroundAdapter"
    summary = "See how one change flows through connected objects."
    scenario_path = Path(__file__).with_name("scenario.json")
    error_rules = {
        "invalid_value": "P2 Values must be whole numbers between -1000 and 1000.",
        "derived_value": "P1 Only the input object can be set directly.",
        "no_change": "The plan would not change anything.",
    }

    def interpret_goal(self, text: str, state: EnvState) -> GoalSpec:
        t = " ".join(text.strip().split())
        low = t.lower()
        if not t:
            return self.unsupported(t, "The goal is empty.")
        if re.search(_OTHER_DOMAIN, low):
            return self.unsupported(t, "This goal does not fit the Generic Object Playground: it has Objects A, B and C only. Select the matching playground instead.")
        if re.search(r"\b(delete|remove)\b", low):
            return self.unsupported(t, "Deleting objects is prohibited (rule P3).")
        if re.search(r"\bobject\s*(b|c)\b|\bprocessor\b|\bdisplay\b", low) and not re.search(r"\bobject\s*a\b|\binput\b", low):
            return self.unsupported(t, "B's output and C's display are derived from A (rule P1). Change Object A instead, and AFM will predict how B and C follow.",
                                    clarification="Try: “Change Object A's value to 10 and show me what will happen.”")
        m = re.search(r"(?:object\s*a|input)\b.*?\b(?:to|=)\s*(-?\d+)", low)
        if not m:
            return self.unsupported(t, "AFM could not map this goal. This playground understands “Change Object A's value to <N>”.",
                                    missing=["The new value for Object A."] if re.search(r"object\s*a|input", low) else None)
        v = int(m.group(1))
        cur = state.objects["obj-a"].state["value"]
        return GoalSpec(
            goal_id=self.goal_id(t), environment_id=self.environment_id, text=t, supported=True,
            intent="set_input", parameters={"value": v}, success_criteria=[
                GoalCriterion(id="c1", kind="a_value", params={"value": v}, description=f"Object A's value is {v}.")],
            explanation="Mapped to structured criteria. B and C are not part of the goal; AFM predicts how they follow.",
            intended_benefits=[f"Object A changes from {cur} to {v}."],
            potential_negative_effects=["Everything connected downstream (B's output, C's display) will change too."],
            missing_information=[] if v != cur else [f"Object A already holds {v}; nothing would change."],
        )

    def propose_plans(self, goal: GoalSpec, state: EnvState) -> list[Plan]:
        v = goal.parameters["value"]
        cur = state.objects["obj-a"].state["value"]
        return [Plan(plan_id="P1", goal_id=goal.goal_id, title=f"Set Object A to {v}", actions=[Action(
            action_id="P1-a1", tool="set_value", operation="set", target_object_id="obj-a", parameters={"value": v},
            expected_preconditions=[f"Object A currently holds {cur}."], permission=PermissionClass.requires_approval,
            purpose=f"Change Object A's value from {cur} to {v}.")],
            assumptions=["B and C follow the configured behavior exactly."], known_limitations=["A teaching model with no unknown dependencies."])]

    def simulate_action(self, action: Action, state: EnvState, step: int) -> list[Consequence]:
        if action.tool != "set_value":
            raise AdapterError("unsupported_action", f"No simulation rule exists for '{action.tool}' in the playground.")
        tgt = state.objects.get(action.target_object_id)
        if tgt is None:
            raise AdapterError("missing_object", f"Object '{action.target_object_id}' does not exist in the known environment.")
        if tgt.type != "input":
            raise AdapterError("derived_value", f"{tgt.name} is derived and cannot be set directly (rule P1).")
        v = action.parameters.get("value")
        if set(action.parameters) != {"value"} or not isinstance(v, int) or isinstance(v, bool) or not -1000 <= v <= 1000:
            raise AdapterError("invalid_value", f"set_value needs {{value: int between -1000 and 1000}}; got {action.parameters}.")
        a, b, c = tgt, state.objects["obj-b"], state.objects["obj-c"]
        if a.state["value"] == v:
            raise AdapterError("no_change", f"{a.name} already holds {v}.")
        a0, b0, c0 = a.state["value"], dict(b.state), c.state["shown"]
        a.state["value"] = v
        b.state["input"] = v
        b.state["output"] = v * b.state["factor"]
        c.state["shown"] = b.state["output"]
        return [
            Consequence(step=step, affected_object_id=a.id, relationship_to_target="target", before={"value": a0}, predicted_after={"value": v},
                        description=f"{a.name}: value {a0} → {v}.", type="direct", evidence_rule=RULE_SET, status="known_in_simulation"),
            Consequence(step=step, affected_object_id=b.id, relationship_to_target="fed by target",
                        before={"input": b0["input"], "output": b0["output"]}, predicted_after={"input": v, "output": b.state["output"]},
                        description=f"{b.name}: output {b0['output']} → {b.state['output']} (input {v} × factor {b.state['factor']}).",
                        type="connected", evidence_rule=RULE_PROC, status="known_in_simulation"),
            Consequence(step=step, affected_object_id=c.id, relationship_to_target="fed by Object B", before={"shown": c0},
                        predicted_after={"shown": c.state["shown"]}, description=f"{c.name}: shows {c0} → {c.state['shown']}.",
                        type="connected", evidence_rule=RULE_DISP, status="known_in_simulation"),
        ]

    def evaluate_criterion(self, c: GoalCriterion, predicted: EnvState) -> tuple[CheckStatus, str]:
        if c.kind == "a_value":
            v = predicted.objects["obj-a"].state["value"]
            return (S.PASS if v == c.params["value"] else S.FAIL), f"Object A holds {v} (goal: {c.params['value']})."
        return S.UNKNOWN, f"Unknown criterion kind '{c.kind}'."

    def rule_checks(self, plan: Plan, sim: SimulationResult, predicted: EnvState) -> list[tuple[CheckStatus, str]]:
        return [(S.PASS, "P1 Only the input object is set directly; B and C change through configured behavior."),
                (S.PASS, "P2 The new value is a whole number within -1000…1000."),
                (S.PASS, "P3 No object is deleted.")]

    def measure(self, state: EnvState, object_id: str, key: str) -> Any:
        return state.objects[object_id].state[key]
