"""Generic planning: goal interpretation and plan generation are delegated to the adapter; the LLM
proposal gate and the recommendation are generic.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ..domain.models import GoalSpec, LLMRejection, PermissionClass, Plan, PlanAssessment, Recommendation, ToolSpec

RULE_CHANGE_KEYS = ("skip_approval", "auto_approve", "rule_changes", "permissions", "new_rules", "disable_rules")
EXECUTABLE_KEYS = ("command", "shell", "sql", "code", "script")


def validate_llm_proposal(raw: Any, goal_id: str, index: int, tools: dict[str, ToolSpec]) -> Plan | LLMRejection:
    """LLM (or human-typed) proposals pass the same schema + tool + permission gate as deterministic ones.
    Nothing in them is executed; text that looks like code or commands is rejected data (R09, R22)."""
    if not isinstance(raw, dict):
        return LLMRejection(raw={"value": str(raw)[:300]}, reasons=["Proposal is not a structured object."])
    reasons = [f"Field '{k}' tries to change rules, permissions or approval. Only a separate human-controlled operation can do that (R10)."
               for k in RULE_CHANGE_KEYS if k in raw]
    reasons += [f"Field '{k}' contains executable content. AFM never runs code, shell commands or SQL from LLM output (R22)."
                for k in EXECUTABLE_KEYS if k in raw]
    if reasons:
        return LLMRejection(raw=raw, reasons=reasons)
    raw = dict(raw)
    # Claude's structured output carries parameters as a JSON string; normalise it
    for a in raw.get("actions", []) if isinstance(raw.get("actions"), list) else []:
        if isinstance(a, dict) and "parameters_json" in a:
            try:
                a["parameters"] = json.loads(a.pop("parameters_json") or "{}")
            except json.JSONDecodeError:
                return LLMRejection(raw=raw, reasons=["Malformed plan: parameters_json is not valid JSON."])
    try:
        plan = Plan.model_validate({**{k: v for k, v in raw.items() if k != "assumptions" or isinstance(v, list)},
                                    "plan_id": f"L{index}", "goal_id": goal_id, "proposed_by": "llm"})
    except ValidationError as e:
        msgs = sorted({f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()})
        return LLMRejection(raw=raw, reasons=["Malformed plan (schema validation failed): " + "; ".join(msgs)])
    for a in plan.actions:
        spec = tools.get(a.tool)
        if spec is None:
            reasons.append(f"Unknown tool '{a.tool}': not registered for this environment (R09).")
        elif spec.permission == PermissionClass.prohibited:
            reasons.append(f"'{a.tool}' is prohibited and unavailable for execution (R24).")
        elif a.operation != spec.operation:
            reasons.append(f"'{a.tool}' does not support operation '{a.operation}'.")
    if reasons:
        return LLMRejection(raw=raw, reasons=reasons)
    for a in plan.actions:  # the LLM can never choose a permission class (R09)
        a.permission = tools[a.tool].permission
    return plan


def recommend(assessments: list[PlanAssessment], goal: GoalSpec) -> Recommendation:
    if not goal.supported:
        return Recommendation(plan_id=None, reason="No recommendation: the goal is not supported. " + goal.explanation)
    ok = [a for a in assessments if a.meets_goal_and_rules]
    if not ok:
        return Recommendation(plan_id=None, reason="No candidate plan meets the goal and the rules with the known data. AFM will not invent an approved plan (R16, R26).")
    # R12: fewer warnings, then fewer changed objects; R27: reversible first; then fewer actions
    key = lambda a: (a.warnings, a.changed_objects, 0 if a.reversible else 1, len(a.plan.actions), a.plan.plan_id)
    best = sorted(ok, key=key)[0]
    why_not = []
    for a in assessments:
        if a.plan.plan_id == best.plan.plan_id:
            continue
        failed = [d for c in a.checks if c.check in ("goal", "rules") for d in c.details if d.startswith(("FAIL", "UNKNOWN", "FLAG"))]
        if failed:
            why_not.append(f"{a.plan.plan_id} ({a.plan.title}): {failed[0].split('· ', 1)[-1]}")
        elif a.meets_goal_and_rules and a.warnings > best.warnings:
            why_not.append(f"{a.plan.plan_id}: meets the goal but leaves {a.warnings} predicted warning(s).")
        elif a.meets_goal_and_rules:
            why_not.append(f"{a.plan.plan_id}: also meets the goal but changes more objects or is less reversible (R12, R27).")
    reason = f"{best.plan.plan_id} ({best.plan.title}) meets every success criterion and passes the rule checks in simulation (R31)."
    if best.warnings:
        reason += f" Trade-off: it still has {best.warnings} predicted warning(s) to review (R32)."
    if why_not:
        reason += " Not chosen: " + " ".join(why_not)
    reason += " This follows from the environment's configured behavior and known data only. It is not a guarantee about the real world, and it still needs your approval."
    return Recommendation(plan_id=best.plan.plan_id, reason=reason)
