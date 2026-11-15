"""Generic AFM orchestration across environments:
assess → review → approve/reject → execute once → observe → store.

All approval and execution checks are enforced here on the backend, not only in the UI.
This local workflow is a prototype: it has no authentication or production-grade authorization.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from ..adapters.base import EnvironmentAdapter
from ..adapters.llm import LLMAdapter, get_llm
from ..adapters.registry import default_adapters
from ..domain.conduct import load_conduct, rules_version
from ..domain.errors import AFMError, Conflict, Forbidden, NotFound
from ..domain.models import (
    ComparisonItem, Decision, EnvironmentDescription, Evidence, GoalCriterion, HumanVerification, Observation, Plan, PlanAssessment, Run,
    SimulationError, SimulationResult, now_iso,
)
from ..domain.profile import load_profile
from ..storage.db import Database
from . import checks, planner, win
from .environment import EnvironmentStore, EnvState
from .simulator import simulate, tool_index


@dataclass
class Runtime:
    adapter: EnvironmentAdapter
    store: EnvironmentStore


class AFMService:
    def __init__(self, db: Database | None = None, llm: LLMAdapter | None = None, adapters: list[EnvironmentAdapter] | None = None):
        load_conduct()  # refuses to start if the permanent rules were tampered with (R10)
        self.db = db or Database()
        self.envs: dict[str, Runtime] = {}
        for a in adapters or default_adapters():
            self.envs[a.environment_id] = Runtime(a, EnvironmentStore(self.db, a))
        self.llm = llm or get_llm()

    def set_llm(self, llm: LLMAdapter) -> None:
        """Switch the LLM tool live (from the 'Use your LLM model' settings). Rules and the gate are unaffected."""
        self.llm = llm

    # ------------------------------------------------------------------ environments
    def env(self, env_id: str) -> Runtime:
        rt = self.envs.get(env_id)
        if rt is None:
            raise NotFound("unknown_environment", f"Environment '{env_id}' has no adapter. Available: {', '.join(self.envs)}.")
        return rt

    def describe(self, env_id: str) -> EnvironmentDescription:
        rt = self.env(env_id)
        a, v = rt.adapter, rt.store.view()
        d = a.describe_environment()
        return EnvironmentDescription(
            **d, rules=a.rules(), tools=a.tools(), demo_goals=a.demo_goals(), definitions=a.definitions(),
            object_count=len(v.objects), relationship_count=len(v.relationships), version=v.version, fingerprint=v.fingerprint,
        )

    def reset(self, env_id: str) -> int:
        return self.env(env_id).store.reset()

    # ------------------------------------------------------------------ runs
    def _save(self, run: Run) -> Run:
        self.db.save_run(run.run_id, run.created_at, run.status, run.model_dump(mode="json"))
        return run

    def get_run(self, run_id: str) -> Run:
        raw = self.db.get_run(run_id)
        if raw is None:
            raise NotFound("unknown_run", f"Run '{run_id}' does not exist.")
        try:
            return Run.model_validate(raw)
        except Exception:
            raise NotFound("legacy_run", f"Run '{run_id}' was made by an earlier AFM version and cannot be opened.")

    def list_runs(self) -> list[Run]:
        out = []
        for r in self.db.list_runs():
            try:
                out.append(Run.model_validate(r))
            except Exception:
                continue  # runs from the earlier single-environment version are kept on disk but not shown
        return out

    @staticmethod
    def _assessment(run: Run, plan_id: str) -> PlanAssessment:
        a = next((x for x in run.assessments if x.plan.plan_id == plan_id), None)
        if a is None:
            raise NotFound("unknown_plan", f"Plan '{plan_id}' is not part of run {run.run_id}.")
        return a

    def _assess_plan(self, rt: Runtime, plan: Plan, goal, state: EnvState, version: int, fp: str,
                     blocked: frozenset[str] = frozenset()) -> PlanAssessment:
        # step 9: pre-check actions against capabilities and permissions BEFORE predicting anything
        tools = tool_index(rt.adapter, blocked)
        cap, perm = checks.check_capability(plan, tools), checks.check_permission(plan, tools)
        if cap.status != checks.S.PASS or perm.status != checks.S.PASS:
            why = "; ".join(d for d in cap.details + perm.details if "exists" not in d and "allowed" not in d) or "pre-check failed"
            sim = SimulationResult(plan_id=plan.plan_id, environment_id=rt.adapter.environment_id, environment_version=version,
                                   environment_fingerprint=fp, simulated_at=now_iso(), applies_to="Not simulated: rejected at the step-9 pre-check.",
                                   feasible=False, consequences=[], errors=[SimulationError(step=0, action_id="-", code="rejected_before_prediction", message=why)],
                                   predicted_objects={}, unknowns=[])
            a = checks.assess(rt.adapter, plan, goal, sim, state.copy(), blocked)
            return a.model_copy(update={"rejected_before_prediction": True, "summary": f"Rejected before prediction: {why}"})
        sim, predicted = simulate(rt.adapter, state, plan, version, fp, blocked)
        return checks.assess(rt.adapter, plan, goal, sim, predicted, blocked)

    def policy_version(self, rt: Runtime, blocked: frozenset[str] | list[str] = frozenset()) -> str:
        """Fingerprint of everything that decides permissions: rules of conduct, profile tools, adapter rules/tools, blocked tools."""
        payload = {"conduct": rules_version(), "profile_tools": [t.model_dump(mode="json") for t in load_profile().tools],
                   "rules": [r.model_dump() for r in rt.adapter.rules()], "tools": [t.model_dump(mode="json") for t in rt.adapter.tools()],
                   "blocked": sorted(blocked)}
        return "policy-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]

    def interpret(self, env_id: str, goal_text: str):
        rt = self.env(env_id)
        return rt.adapter.interpret_goal(goal_text, rt.store.snapshot())

    def assess(self, env_id: str, goal_text: str, include_llm: bool = True, usecase_id: str | None = None,
               task_role: str | None = None, usecase_rules: list[str] | None = None, blocked_tools: list[str] | None = None,
               human_criteria: list[str] | None = None, desired_input: str = "", desired_output: str = "") -> Run:
        rt = self.env(env_id)
        blocked = frozenset(blocked_tools or [])
        with rt.store.lock:
            state = rt.store.snapshot()
            version, fp = rt.store.version, state.fingerprint()
        goal = rt.adapter.interpret_goal(goal_text, state)
        goal.desired_input, goal.desired_output = desired_input.strip()[:500], desired_output.strip()[:500]
        if goal.supported:  # human-written criteria are kept as such: not machine-checkable, verified by a human after execution
            goal.success_criteria += [GoalCriterion(id=f"h{i}", kind="manual", source="human", description=t.strip()[:300])
                                      for i, t in enumerate(human_criteria or [], start=1) if t.strip()]
        run = Run(run_id="run-" + uuid.uuid4().hex[:8], created_at=now_iso(), environment_id=env_id, environment_name=rt.adapter.name,
                  rules_version=rules_version(), usecase_id=usecase_id, task_role=task_role, usecase_rules=usecase_rules or [],
                  blocked_tools=sorted(blocked), policy_version=self.policy_version(rt, blocked), goal=goal,
                  environment_version=version, environment_fingerprint=fp, status="awaiting_review")
        # step 1 task goal; identity, rules and permissions are standing context, loaded before anything is inspected
        run.log("goal", f"Task goal received in {rt.adapter.name}: “{goal.text}”. Supported: {goal.supported}.")
        run.log("rules", f"Loaded the permanent rules of conduct ({rules_version()}), {len(rt.adapter.rules())} {rt.adapter.name} rule(s) and policy {run.policy_version}; the goal is judged against them.")
        if task_role:
            run.log("role", f"Task role: {task_role}. It sets task context only; AFM's identity, rules, permissions and approval are unchanged.")
        if usecase_rules:
            run.log("rules", f"{len(usecase_rules)} use-case rule(s) recorded; blocked tools: {', '.join(sorted(blocked)) or 'none'}.")
        if not goal.supported:
            run.status = "unsupported_goal"
            run.recommendation = planner.recommend([], goal)
            run.log("stop", goal.explanation)
            return self._save(run)
        run.log("pre-check", f"R30 goal pre-check: {len(goal.intended_benefits)} intended benefit(s), {len(goal.potential_negative_effects)} possible negative effect(s), {len(goal.missing_information)} missing item(s).")
        run.log("inspect", f"Read-only inspection of {rt.adapter.name} v{version} ({len(state.objects)} known objects) via {rt.adapter.adapter_name}.")
        for plan in rt.adapter.propose_plans(goal, state):
            a = self._assess_plan(rt, plan, goal, state, version, fp, blocked)
            run.assessments.append(a)
            run.log("pre-check" if a.rejected_before_prediction else "simulate",
                    f"{plan.plan_id}: {a.summary}" if a.rejected_before_prediction else f"{plan.plan_id} passed the pre-check and was simulated on a copy: {a.summary}")
        if include_llm:
            tools = tool_index(rt.adapter, blocked)
            known = {"environment_id": env_id, "environment_name": rt.adapter.name,
                     "objects": [{"id": o.id, "type": o.type, "name": o.name, "state": o.state} for o in state.objects.values()],
                     "tools": [{"name": t.name, "operation": t.operation, "parameters": t.parameters, "target_types": t.target_types}
                               for t in tools.values() if t.scope == "environment"],
                     "mock_proposals": rt.adapter.mock_llm_proposals()}
            try:
                proposals = self.llm.propose_plans(goal.text, known)
            except AFMError as e:
                proposals = []
                run.log("llm", f"LLM ({self.llm.name}) unavailable, continuing with deterministic plans only (R19): {e.message}")
            for i, raw in enumerate(proposals, start=1):
                res = planner.validate_llm_proposal(raw, goal.goal_id, i, tools)
                if isinstance(res, Plan):
                    run.assessments.append(self._assess_plan(rt, res, goal, state, version, fp, blocked))
                    run.log("llm", f"LLM proposal {res.plan_id} passed the schema gate and was simulated like any other plan.")
                else:
                    run.llm_rejections.append(res)
                    run.log("llm", f"LLM proposal rejected: {res.reasons[0]}")
        run.recommendation = planner.recommend(run.assessments, goal)
        if run.recommendation.plan_id is None:
            run.status = "no_viable_plan"
        run.log("recommend", run.recommendation.reason)
        return self._save(run)

    def simulate_adhoc(self, env_id: str, raw_plan: dict[str, Any], goal_text: str | None = None) -> PlanAssessment:
        """Simulate any structured plan (e.g. typed by a human) through the same gate."""
        rt = self.env(env_id)
        state = rt.store.snapshot()
        goal = rt.adapter.interpret_goal(goal_text or (rt.adapter.demo_goals() or [""])[0], state)
        res = planner.validate_llm_proposal(raw_plan, goal.goal_id, 0, tool_index(rt.adapter))
        if not isinstance(res, Plan):
            raise AFMError("invalid_plan", " ".join(res.reasons), 422)
        res.proposed_by = "human"
        return self._assess_plan(rt, res, goal, state, rt.store.version, state.fingerprint())

    # ------------------------------------------------------------------ review & decision
    def review(self, run_id: str, plan_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        rt = self.env(run.environment_id)
        a = self._assessment(run, plan_id)
        state = rt.store.snapshot()
        affected = sorted({c.affected_object_id for c in a.simulation.consequences})
        stale = (rt.store.version != run.environment_version) or (state.fingerprint() != run.environment_fingerprint)
        return {"run_id": run.run_id, "environment_id": run.environment_id, "environment_name": run.environment_name,
                "goal": run.goal.model_dump(), "assessment": a.model_dump(mode="json"),
                "current_state": {oid: state.objects[oid].state for oid in affected if oid in state.objects},
                "evidence": {oid: state.objects[oid].evidence.value for oid in affected if oid in state.objects},
                "environment_version_now": rt.store.version, "stale": stale,
                "execution_supported": bool(rt.adapter.capabilities.get("execute")),
                "decisions": [d.model_dump() for d in run.decisions if d.plan_id == plan_id], "run_status": run.status}

    def decide(self, run_id: str, plan_id: str, decision: str, plan_hash: str, environment_version: int,
               reviewer: str = "local human", note: str = "", criteria_agreed: bool = False) -> Decision:
        run = self.get_run(run_id)
        rt = self.env(run.environment_id)
        with rt.store.lock:
            run = self.get_run(run_id)
            a = self._assessment(run, plan_id)
            if run.executed_plan_id:
                raise Conflict("duplicate_execution", "This run has already been executed. Start a new assessment.")
            if run.status in ("unsupported_goal", "no_viable_plan") and decision == "approve":
                raise Forbidden("not_approvable", "There is no approvable plan in this run.")
            if any(d.plan_id == plan_id and d.status in ("active", "rejected") for d in run.decisions):
                raise Conflict("already_decided", f"{plan_id} already has a decision in this run (R28).")
            if decision == "approve" and any(d.status == "active" for d in run.decisions):
                raise Conflict("already_approved", "Another plan in this run is already approved. Only one plan per run can be approved.")
            if plan_hash != a.plan_hash:
                raise Conflict("plan_mismatch", "The plan you reviewed differs from the plan on record. Review it again (R23).")
            if environment_version != run.environment_version or rt.store.version != run.environment_version \
                    or rt.store.fingerprint() != run.environment_fingerprint:
                run.status = "stale"
                run.log("stale", "Environment changed since the prediction; decision refused (R13).")
                self._save(run)
                raise Conflict("stale_environment", "The environment changed since this prediction. Run a new assessment and review again (R13).")
            if decision == "approve" and not a.approvable:
                raise Forbidden("not_approvable", a.approvable_reason)
            d = Decision(decision=decision, plan_id=plan_id, plan_hash=a.plan_hash,
                         environment_version=run.environment_version, environment_fingerprint=run.environment_fingerprint,
                         reviewer=reviewer or "local human", note=note, decided_at=now_iso(),
                         approval_id="ap-" + uuid.uuid4().hex[:10], status="active" if decision == "approve" else "rejected",
                         policy_version=run.policy_version or self.policy_version(rt, run.blocked_tools),
                         criteria_agreed=bool(criteria_agreed and decision == "approve"))
            run.decisions.append(d)
            if decision == "approve":
                run.status = "approved"
                run.log("approve", f"{plan_id} approved by {d.reviewer} for env v{d.environment_version} (hash {d.plan_hash}, {d.policy_version}); "
                                   f"success criteria {'agreed' if d.criteria_agreed else 'NOT agreed'} by the human.")
            else:
                run.log("reject", f"{plan_id} rejected by {d.reviewer}. It will not be executed (R28).")
                approvable = {x.plan.plan_id for x in run.assessments if x.approvable}
                rejected = {x.plan_id for x in run.decisions if x.status == "rejected"}
                if approvable and approvable <= rejected:
                    run.status, run.execution_status = "rejected", "rejected"
            self._save(run)
            return d

    # ------------------------------------------------------------------ execution
    def execute(self, run_id: str, plan_id: str, approval_id: str | None, plan: dict[str, Any] | None = None) -> Run:
        run = self.get_run(run_id)
        rt = self.env(run.environment_id)
        with rt.store.lock:
            run = self.get_run(run_id)
            if run.executed_plan_id:
                raise Conflict("duplicate_execution", "This approved run was already executed once. It cannot run again.")
            a = self._assessment(run, plan_id)
            d = next((x for x in run.decisions if x.approval_id == approval_id), None) if approval_id else None
            if d is None or d.decision != "approve":
                raise Forbidden("missing_approval", "No approval was found for this plan. Every state-changing action needs explicit human approval (R08).")
            if d.status != "active":
                raise Forbidden("approval_not_active", f"This approval is {d.status}{': ' + d.invalidated_reason if d.invalidated_reason else ''}.")
            if d.plan_id != plan_id:
                raise Forbidden("approval_mismatch", f"Approval {approval_id} is for {d.plan_id}, not {plan_id} (R23).")
            if not rt.adapter.capabilities.get("execute"):
                run.execution_status = "unsupported"
                self._save(run)
                raise Forbidden("execution_unsupported", f"{rt.adapter.name} cannot execute actions. The approval is recorded, but nothing was changed (R19).")
            if plan is not None:
                try:
                    submitted = Plan.model_validate(plan)
                except Exception:
                    raise Conflict("plan_mismatch", "The submitted plan is malformed and does not match the approval.")
                if checks.plan_hash(submitted) != d.plan_hash:
                    raise Conflict("plan_mismatch", "The submitted plan or its parameters differ from what was approved (R23).")
            if checks.plan_hash(a.plan) != d.plan_hash:
                raise Conflict("plan_mismatch", "The stored plan no longer matches the approval.")

            def invalidate(code: str, why: str):
                d.status, d.invalidated_reason = "invalidated", why
                run.status = "stale" if code == "stale_environment" else "execution_blocked"
                run.execution_status = "failed"
                run.log("invalidate", why)
                self._save(run)
                raise Conflict(code, why + " Approval invalidated: run a new assessment and review again (R13).")

            state = rt.store.snapshot()
            if rt.store.version != d.environment_version or state.fingerprint() != d.environment_fingerprint:
                invalidate("stale_environment", f"The environment changed (v{d.environment_version} → v{rt.store.version}) since the prediction.")
            current_policy = self.policy_version(rt, run.blocked_tools)
            if d.policy_version and current_policy != d.policy_version:
                invalidate("policy_changed", f"The applicable policy changed ({d.policy_version} → {current_policy}) since the approval.")
            blocked = frozenset(run.blocked_tools)
            re_a = self._assess_plan(rt, a.plan, run.goal, state, rt.store.version, state.fingerprint(), blocked)
            if not re_a.approvable:
                invalidate("recheck_failed", f"Recheck failed: {re_a.approvable_reason}")
            if re_a.simulation.predicted_objects != a.simulation.predicted_objects:
                invalidate("prediction_changed", "Re-simulation no longer matches the reviewed prediction.")
            before = state
            _, new_state = simulate(rt.adapter, state, a.plan, rt.store.version, state.fingerprint(), blocked)
            ts = now_iso()
            for oid in a.simulation.predicted_objects:
                if oid in new_state.objects:
                    new_state.objects[oid].last_observed = ts
                    new_state.objects[oid].evidence = Evidence.observed
            new_version = rt.store.commit(new_state)
            d.status = "used"
            run.executed_plan_id = plan_id
            run.status, run.execution_status = "executed", "executed"
            run.log("execute", f"{plan_id} executed once in the simulated {rt.adapter.name} (v{d.environment_version} → v{new_version}).")
            run.observation = self._observe(rt, a, before, new_version)
            run.log("observe", f"Observed test results by {run.observation.method.lower()} at {run.observation.observed_at} (simulated: {run.observation.simulated}).")
            n = {r: sum(1 for i in run.observation.items if i.result == r) for r in ("MATCH", "MISMATCH", "NOT VERIFIED")}
            run.log("compare", f"Prediction vs test results: {n['MATCH']} match, {n['MISMATCH']} mismatch, {n['NOT VERIFIED']} not verified (R15).")
            run.win = win.evaluate(rt.adapter, run, a, EnvState.from_dict(run.observation.snapshot))
            run.log("win", f"AFM result: {run.win.overall}. {run.win.explanation}")
            return self._save(run)

    def verify(self, run_id: str, kind: str, ref: str, status: str, evidence: str, reviewer: str) -> Run:
        """Record a human judgment for a manual success criterion or a broad rule, then recompute the Win (step 16)."""
        run = self.get_run(run_id)
        rt = self.env(run.environment_id)
        if run.observation is None or not run.executed_plan_id:
            raise Conflict("not_executed", "Nothing was executed, so there is no observed result to verify and no execution-based Win.")
        if kind == "criterion" and not any(c.id == ref and c.kind == "manual" for c in run.goal.success_criteria):
            raise AFMError("invalid_input", f"'{ref}' is not a human-written success criterion of this run.", 422)
        known_rules = {r.id for r in load_conduct().rules} | {r.id for r in rt.adapter.rules()}
        if kind == "rule" and ref not in known_rules:
            raise AFMError("invalid_input", f"'{ref}' is not an applicable rule.", 422)
        if not evidence.strip():
            raise AFMError("invalid_input", "Describe the evidence you reviewed.", 422)
        run.verifications.append(HumanVerification(kind=kind, ref=ref, status=status, evidence=evidence.strip()[:500],
                                                   reviewer=reviewer.strip()[:80] or "local human", at=now_iso()))
        a = self._assessment(run, run.executed_plan_id)
        run.win = win.evaluate(rt.adapter, run, a, EnvState.from_dict(run.observation.snapshot))
        run.log("verify", f"{reviewer or 'local human'} recorded {status} for {kind} {ref}. AFM result now: {run.win.overall}.")
        return self._save(run)

    def _observe(self, rt: Runtime, a: PlanAssessment, before: EnvState, new_version: int) -> Observation:
        after = rt.store.snapshot()  # fresh read-only inspection of the live simulated environment
        items: list[ComparisonItem] = []
        for oid, pred_state in a.simulation.predicted_objects.items():
            obs, prev = after.objects.get(oid), before.objects.get(oid)
            for k, v in pred_state.items():
                if prev is not None and prev.state.get(k) == v:
                    continue
                if obs is None:
                    items.append(ComparisonItem(object_id=oid, field=k, predicted=v, observed=None, result="MISMATCH", note="Object not found after execution."))
                    continue
                o = obs.state.get(k)
                items.append(ComparisonItem(object_id=oid, field=k, predicted=v, observed=o, result="MATCH" if o == v else "MISMATCH"))
        seen = {(i.object_id, i.field) for i in items}
        for c in a.simulation.consequences:
            if c.status == "conditional":
                for k, p in c.observable.items():
                    if (c.affected_object_id, k) in seen:
                        continue
                    try:
                        o = rt.adapter.measure(after, c.affected_object_id, k)
                        items.append(ComparisonItem(object_id=c.affected_object_id, field=k, predicted=p, observed=o,
                                                    result="MATCH" if o == p else "MISMATCH", note="Measured in the simulation (test)."))
                    except KeyError:
                        items.append(ComparisonItem(object_id=c.affected_object_id, field=k, predicted=p, observed=None, result="NOT VERIFIED",
                                                    note="The adapter cannot measure this value; the test could not be run."))
                items.append(ComparisonItem(object_id=c.affected_object_id, field="real-world outcome", predicted=c.description, observed=None,
                                            result="NOT VERIFIED", required=False,
                                            note="Informational: depends on assumptions or later events outside the simulation."))
            elif c.status == "unknown":
                items.append(ComparisonItem(object_id=c.affected_object_id, field="effect", predicted="unknown", observed=None,
                                            result="NOT VERIFIED", required=False, note="Informational: unknown dependency, not inspectable here."))
        unchanged = sorted(oid for oid, o in after.objects.items() if oid in before.objects and before.objects[oid].state == o.state)
        return Observation(observed_at=now_iso(), environment_version_after=new_version, items=items, unchanged_objects=unchanged,
                           snapshot=after.to_dict(), method=f"Fresh read-only inspection of {rt.adapter.name} v{new_version} after execution",
                           source="simulation" if rt.adapter.kind == "simulated" else "connected", simulated=rt.adapter.kind == "simulated")
