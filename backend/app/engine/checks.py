"""Five separate generic checks, all deterministic and outside the LLM:

A. capability  B. permission  C. rule compliance  D. goal evaluation  E. human review
Domain-specific judgments come from the adapter (error_rules, rule_checks, evaluate_criterion).
A plan is never reported compliant if a required check is UNKNOWN or FAIL (R20).
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from ..domain.models import CheckResult, CheckStatus, GoalSpec, PermissionClass, Plan, PlanAssessment, SimulationResult
from .environment import EnvState
from .simulator import tool_index

if TYPE_CHECKING:
    from ..adapters.base import EnvironmentAdapter

S = CheckStatus
GENERIC_ERROR_RULES = {
    "prohibited_action": "R09/R24 Prohibited actions are never available, with or without approval.",
    "read_only_violation": "R09 A read-only tool must not change state.",
    "rejected_before_prediction": "R09/R24 Rejected at the step-9 pre-check (unregistered, unsupported or prohibited action); not simulated.",
}


def plan_hash(plan: Plan) -> str:
    """Binds an approval to the exact plan: id, goal, ordered actions and every parameter (R23)."""
    payload = plan.model_dump(mode="json", include={"plan_id", "goal_id", "actions"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _worst(statuses: list[CheckStatus]) -> CheckStatus:
    for s in (S.FAIL, S.UNKNOWN, S.REVIEW_REQUIRED):
        if s in statuses:
            return s
    return S.PASS


def check_capability(plan: Plan, tools) -> CheckResult:
    sts, det = [], []
    for a in plan.actions:
        spec = tools.get(a.tool)
        if spec is None:
            sts.append(S.FAIL); det.append(f"{a.action_id}: tool '{a.tool}' is not registered in this environment.")
        elif not spec.executable:
            sts.append(S.FAIL); det.append(f"{a.action_id}: '{a.tool}' is not available for execution.")
        elif a.operation != spec.operation:
            sts.append(S.FAIL); det.append(f"{a.action_id}: '{a.tool}' does not support operation '{a.operation}'.")
        else:
            sts.append(S.PASS); det.append(f"{a.action_id}: '{a.tool}' ({a.operation}) exists.")
    return CheckResult(check="capability", label="A. Capability: does the tool and action exist?", status=_worst(sts), details=det)


def check_permission(plan: Plan, tools) -> CheckResult:
    sts, det = [], []
    for a in plan.actions:
        spec = tools.get(a.tool)
        perm = spec.permission if spec else PermissionClass.unknown
        if perm == PermissionClass.prohibited:
            sts.append(S.FAIL); det.append(f"{a.action_id}: '{a.tool}' is prohibited.")
        elif perm == PermissionClass.unknown:
            sts.append(S.UNKNOWN); det.append(f"{a.action_id}: no permission is configured for '{a.tool}'.")
        elif perm == PermissionClass.requires_approval:
            sts.append(S.PASS); det.append(f"{a.action_id}: '{a.tool}' is allowed only with explicit human approval.")
        else:
            sts.append(S.PASS); det.append(f"{a.action_id}: '{a.tool}' is allowed (read-only or simulation).")
    return CheckResult(check="permission", label="B. Permission: may AFM use the tool this way?", status=_worst(sts), details=det)


def check_rules(adapter: "EnvironmentAdapter", plan: Plan, sim: SimulationResult, predicted: EnvState, tools) -> CheckResult:
    sts, det = [], []
    for err in sim.errors:
        rule = GENERIC_ERROR_RULES.get(err.code) or adapter.error_rules.get(err.code)
        if rule:
            sts.append(S.FAIL); det.append(f"FAIL · {rule} {err.message}")
        else:
            sts.append(S.UNKNOWN)
            det.append(f"UNKNOWN · Step {err.step} could not be simulated ({err.code}): {err.message} Rule compliance cannot be confirmed (R16, R20).")
    if sim.feasible:
        sts.append(S.PASS)
        det.append("PASS · R06/R11 Every consequence is labelled known in simulation, conditional or unknown; none is stored as an observation.")
        det.append(f"PASS · R17/R19 {len(sim.unknowns)} unknown(s) and the plan's assumptions are reported; the prediction covers known dependencies only.")
        for status, text in adapter.rule_checks(plan, sim, predicted):
            sts.append(status)
            det.append(text if text.startswith(("PASS", "FAIL", "FLAG", "UNKNOWN")) else f"{status.value} · {text}")
    if any((s := tools.get(a.tool)) and s.modifies_state for a in plan.actions):
        det.append("R08 This plan changes simulated state, so it needs explicit human approval (see E).")
    return CheckResult(check="rules", label="C. Rule compliance: does the action or predicted result break a rule?", status=_worst(sts), details=det)


def check_goal(adapter: "EnvironmentAdapter", goal: GoalSpec, sim: SimulationResult, predicted: EnvState) -> CheckResult:
    label = "D. Goal: does the predicted result meet the goal's success criteria?"
    if not goal.supported or not goal.success_criteria:
        return CheckResult(check="goal", label=label, status=S.UNKNOWN, details=["The goal could not be mapped to supported success criteria."])
    if not sim.feasible:
        return CheckResult(check="goal", label=label, status=S.UNKNOWN, details=["The plan cannot be carried out, so there is no predicted outcome to evaluate."])
    sts, det = [], []
    for c in goal.success_criteria:
        if c.kind == "manual":  # human-written criteria cannot be predicted by code; a human verifies them after execution
            det.append(f"MANUAL · {c.description} (human criterion, verified after execution)")
            continue
        st, text = adapter.evaluate_criterion(c, predicted)
        sts.append(st); det.append(f"{st.value} · {text}")
    if not sts:
        return CheckResult(check="goal", label=label, status=S.UNKNOWN, details=det + ["No machine-checkable criterion: the goal cannot be predicted."])
    return CheckResult(check="goal", label=label, status=_worst(sts), details=det)


def check_review(plan: Plan, tools) -> CheckResult:
    mod = [a for a in plan.actions if (s := tools.get(a.tool)) and s.modifies_state]
    label = "E. Human review: does this need explicit approval?"
    if mod:
        return CheckResult(check="human_review", label=label, status=S.REVIEW_REQUIRED,
                           details=[f"{a.action_id}: '{a.tool}' changes simulated state. Approve before execution." for a in mod])
    return CheckResult(check="human_review", label=label, status=S.PASS, details=["Read-only plan: no approval needed."])


def assess(adapter: "EnvironmentAdapter", plan: Plan, goal: GoalSpec, sim: SimulationResult, predicted: EnvState,
           blocked: frozenset[str] = frozenset()) -> PlanAssessment:
    tools = tool_index(adapter, blocked)
    checks = [check_capability(plan, tools), check_permission(plan, tools), check_rules(adapter, plan, sim, predicted, tools),
              check_goal(adapter, goal, sim, predicted), check_review(plan, tools)]
    by = {c.check: c.status for c in checks}
    blockers = [c.label.split(":")[0] for c in checks[:3] if c.status in (S.FAIL, S.UNKNOWN)]
    modifies = by["human_review"] == S.REVIEW_REQUIRED
    if not sim.feasible:
        approvable, why = False, "The plan cannot be carried out in the simulation."
    elif blockers:
        approvable, why = False, f"Not approvable: {', '.join(blockers)} did not pass (R20, R24)."
    elif not modifies:
        approvable, why = False, "Read-only plan: nothing to approve."
    elif by["goal"] != S.PASS:
        approvable, why = True, "Approvable, but WARNING: the predicted result does not meet the goal."
    elif by["rules"] == S.REVIEW_REQUIRED:
        approvable, why = True, "Approvable: the goal is met, but a rule flagged something for your attention."
    else:
        approvable, why = True, "Approvable: capability, permission and rules pass; the goal is met in simulation."
    meets = approvable and by["goal"] == S.PASS
    direct = [c for c in sim.consequences if c.type == "direct" and c.relationship_to_target == "target"]
    summary = direct[0].description if direct else (sim.errors[0].message if sim.errors else "No state change.")
    rev = [tools[a.tool].reversible for a in plan.actions if a.tool in tools and tools[a.tool].modifies_state]
    reversible = None if not rev or any(r is None for r in rev) else all(rev)
    return PlanAssessment(
        plan=plan, plan_hash=plan_hash(plan), simulation=sim, checks=checks,
        approvable=approvable, approvable_reason=why, meets_goal_and_rules=meets, summary=summary,
        warnings=sum(1 for c in sim.consequences if c.effect == "warning"),
        benefits=sum(1 for c in sim.consequences if c.effect == "benefit"),
        changed_objects=len(sim.predicted_objects), reversible=reversible,
    )
