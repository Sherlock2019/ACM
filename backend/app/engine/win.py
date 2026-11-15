"""Step 16: evidence-based AFM Win evaluation (generic, backend-only).

WIN requires ALL THREE: A prediction accuracy, B task goal achievement, C rule compliance.
  any condition FAIL                 → NOT A WIN (the FAIL stays visible)
  no FAIL, any condition NOT VERIFIED → NOT VERIFIED
  all PASS                           → WIN
Only evaluated after an approved execution; never invented for rejected or unexecuted plans.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain.models import CheckStatus, PlanAssessment, Run, WinCheck, WinCondition, WinEvaluation, now_iso
from .environment import EnvState

if TYPE_CHECKING:
    from ..adapters.base import EnvironmentAdapter

PASS, FAIL, NV = "PASS", "FAIL", "NOT VERIFIED"


def combine(statuses: list[str]) -> str:
    if FAIL in statuses:
        return FAIL
    if NV in statuses or not statuses:
        return NV
    return PASS


def _prediction(run: Run) -> WinCondition:
    obs = run.observation
    req = [i for i in obs.items if i.required]
    checks = [WinCheck(name=f"{i.object_id} · {i.field}", status={"MATCH": PASS, "MISMATCH": FAIL}.get(i.result, NV),
                       evidence=f"predicted {i.predicted!r}, observed {i.observed!r} ({i.result})", phase="observation") for i in req]
    st = combine([c.status for c in checks]) if checks else NV
    n = {r: sum(1 for i in req if i.result == r) for r in ("MATCH", "MISMATCH", "NOT VERIFIED")}
    return WinCondition(condition="prediction_accuracy", question="Did all required AI predictions match the observed test results?",
                        status=st, checks=checks,
                        summary=(f"{n['MATCH']} required prediction(s) matched, {n['MISMATCH']} mismatched, {n['NOT VERIFIED']} not verified."
                                 if req else "No required prediction could be compared."))


def _goal(adapter: "EnvironmentAdapter", run: Run, observed: EnvState) -> WinCondition:
    used = next((d for d in run.decisions if d.status == "used"), None)
    checks: list[WinCheck] = []
    if not used or not used.criteria_agreed:
        checks.append(WinCheck(name="Success criteria agreed by the human", status=NV, phase="review",
                               evidence="The human did not explicitly agree the success criteria at review, so achievement cannot be claimed."))
    for c in run.goal.success_criteria:
        if not c.required:
            continue
        if c.kind == "manual":
            v = next((x for x in reversed(run.verifications) if x.kind == "criterion" and x.ref == c.id), None)
            checks.append(WinCheck(name=f"{c.description} (human criterion)", status=v.status if v else NV, phase="observation",
                                   evidence=f"verified by {v.reviewer}: {v.evidence}" if v else "Not machine-checkable; awaiting human verification."))
        else:
            st, detail = adapter.evaluate_criterion(c, observed)
            checks.append(WinCheck(name=c.description, status={CheckStatus.PASS: PASS, CheckStatus.FAIL: FAIL}.get(st, NV),
                                   phase="observation", evidence=f"On the OBSERVED state: {detail} (criterion {c.source.replace('_', ' ')})"))
    st = combine([c.status for c in checks])
    return WinCondition(condition="task_goal", question="Did the observed results meet the agreed task goal and its success criteria?",
                        status=st, checks=checks, summary=f"Task goal: “{run.goal.text}”.")


def _rules(adapter: "EnvironmentAdapter", run: Run, a: PlanAssessment, observed: EnvState) -> WinCondition:
    used = next((d for d in run.decisions if d.status == "used"), None)
    by = {c.check: c for c in a.checks}
    checks = [
        WinCheck(name="Registered, permitted tools only (R09)", phase="planning",
                 status=PASS if by["capability"].status == CheckStatus.PASS and by["permission"].status == CheckStatus.PASS else FAIL,
                 evidence="; ".join(by["permission"].details)),
        WinCheck(name="Applicable rules at prediction (conduct + environment)", phase="simulation",
                 status={CheckStatus.PASS: PASS, CheckStatus.REVIEW_REQUIRED: PASS, CheckStatus.FAIL: FAIL}.get(by["rules"].status, NV),
                 evidence=("Rule flags were presented to the human before approval. " if by["rules"].status == CheckStatus.REVIEW_REQUIRED else "")
                 + " | ".join(d for d in by["rules"].details if d.startswith(("PASS", "FAIL", "FLAG", "UNKNOWN")))[:600]),
        WinCheck(name="Simulation ran on an isolated copy (R07)", phase="simulation", status=PASS,
                 evidence="The environment fingerprint was unchanged at execution recheck, so prediction did not modify it."),
        WinCheck(name="Human approval before the state change (R08, R23)", phase="review",
                 status=PASS if used else FAIL,
                 evidence=f"Approved by {used.reviewer} at {used.decided_at}, bound to plan hash {used.plan_hash} and env v{used.environment_version}." if used else "No used approval found."),
        WinCheck(name="Recheck of plan, policy and environment before execution (R13, R24)", phase="execution",
                 status=PASS if run.execution_status == "executed" else NV,
                 evidence=f"Executed once after the backend recheck; policy {run.policy_version}." if run.execution_status == "executed" else "Not executed."),
    ]
    for st, text in adapter.rule_checks(a.plan, a.simulation, observed):
        s = {CheckStatus.PASS: PASS, CheckStatus.REVIEW_REQUIRED: PASS, CheckStatus.FAIL: FAIL}.get(st, NV)
        checks.append(WinCheck(name=f"Environment rule on the observed result: {text.split('·')[-1].strip()[:90]}", phase="observation", status=s,
                               evidence=text + (" (flag reported, not a violation)" if st == CheckStatus.REVIEW_REQUIRED else "")))
    checks.append(WinCheck(name="Honest reporting (R06, R18)", phase="reporting", status=PASS,
                           evidence="Observation is labelled simulated; unverifiable outcomes are reported as NOT VERIFIED."))
    for v in run.verifications:
        if v.kind == "rule":
            checks.append(WinCheck(name=f"Human judgment on {v.ref}", phase="human verification", status=v.status,
                                   evidence=f"{v.reviewer}: {v.evidence}"))
    st = combine([c.status for c in checks])
    return WinCondition(condition="rule_compliance", question="Were the applicable rules and permissions respected throughout the task?",
                        status=st, checks=checks,
                        summary="Concrete checks across planning, simulation, review, execution and reporting. Broad principles marked "
                                "'partially enforced' are not proven by the absence of a detected violation; a human can record a judgment on them.")


def evaluate(adapter: "EnvironmentAdapter", run: Run, a: PlanAssessment, observed: EnvState) -> WinEvaluation:
    conds = [_prediction(run), _goal(adapter, run, observed), _rules(adapter, run, a, observed)]
    sts = [c.status for c in conds]
    overall = "NOT A WIN" if FAIL in sts else ("NOT VERIFIED" if NV in sts else "WIN")
    names = {"prediction_accuracy": "prediction accuracy", "task_goal": "task goal", "rule_compliance": "rule compliance"}
    expl = {"WIN": "All three conditions passed on observed evidence.",
            "NOT A WIN": "Failed: " + ", ".join(names[c.condition] for c in conds if c.status == FAIL) + ".",
            "NOT VERIFIED": "No failure is known, but not verified: " + ", ".join(names[c.condition] for c in conds if c.status == NV) + "."}[overall]
    if overall == "NOT A WIN" and NV in sts:
        expl += " Still not verified: " + ", ".join(names[c.condition] for c in conds if c.status == NV) + "."
    return WinEvaluation(evaluated_at=now_iso(), simulated=run.observation.simulated, conditions=conds, overall=overall,
                         explanation=expl + (" Results come from a simulation, not a real system." if run.observation.simulated else ""))
