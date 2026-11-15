"""Use-case builder: structured fields + chat with the LLM tool.

- Global rules of conduct load automatically (pinned version recorded per use case).
- Use-case rules may only NARROW: a rule naming a state-changing tool (or its target object type with a change verb)
  blocks that tool for this use case's assessments. Free-text rules are recorded and shown as "not automatically checked".
  A rule that tries to weaken global rules is a CONFLICT and blocks "Prepare assessment" until the human removes it.
- The chat may PROPOSE field updates; they stay pending until the human accepts (or edits) them.
- Describing an environment in chat never makes it connected. Only registered adapters can be inspected or simulated.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from ..adapters.llm import INPUT_FIELDS, USECASE_FIELDS
from ..adapters.registry import FUTURE_ADAPTERS, simulation_templates
from ..domain.conduct import load_conduct, rules_version
from ..domain.errors import AFMError, Conflict, NotFound
from ..domain.models import ChatMessage, UseCase, UseCaseFields, UseCaseRule, now_iso
from .simulator import tool_index

_NEG = r"^\s*(do not|don't|dont|never|no|must not|avoid)\b"
_WEAKEN = [r"\b(ignore|bypass|disable|override|remove|weaken|turn off)\b.*\b(rule|rules|approval|review|permission|permissions|check|checks)\b",
           r"\bskip\b.*\b(review|approval|check)", r"\bauto-?approve\b", r"\bno (need for )?(review|approval)\b",
           r"\bwithout (asking|approval|review|permission)\b", r"^\s*(you may|allow|feel free to|it'?s ok to)\b"]
_CHANGE = r"\b(change|modify|update|edit|set|configure|delete|remove|stop|reserve|restart)\b"
CONNECTION_LABELS = {
    "simulated": "Simulated (local AFM playground)",
    "not_implemented": "Not implemented: no adapter exists",
    "not_connected": "Not connected: described by the human only",
}


class UseCaseService:
    def __init__(self, afm):
        self.afm = afm
        self.db = afm.db

    # ------------------------------------------------------------------ storage
    def _save(self, uc: UseCase) -> UseCase:
        uc.updated_at = now_iso()
        self.db.save_usecase(uc.usecase_id, uc.updated_at, uc.model_dump(mode="json"))
        return uc

    def get(self, uc_id: str) -> UseCase:
        raw = self.db.get_usecase(uc_id)
        if raw is None:
            raise NotFound("unknown_usecase", f"Use case '{uc_id}' does not exist.")
        return self._migrate(UseCase.model_validate(raw))

    def _migrate(self, uc: UseCase) -> UseCase:
        """Bring saved simulations to the 16-step workflow without losing the human's edited notes.
        v1: goal at step 7 (15 steps) → v2: goal at step 1 (15 steps) → v4: 16 steps with Win evaluation."""
        if uc.kind != "simulation" or uc.steps_version >= 4:
            return uc
        n = list(uc.step_notes)
        if uc.steps_version < 2 and len(n) == 15:
            n = [n[6]] + n[:6] + n[7:]
        if len(n) == 15:
            t = next((x["thinking"] for x in self.templates() if x["template_id"] == uc.template_id), None) or [""] * 16
            # v2 order: 0 goal,1 identity,2 rules,3 env,4 objects,5 llm,6 inspect,7 tools,8 plans,9 predict,10 checks,11 present,12 review,13 execute,14 observe
            n = [n[0], f"{n[1]} {n[2]}", n[3], t[3], n[4], f"{n[5]} {n[6]}", n[7], n[8], t[8], n[9], n[10], f"{n[11]} {n[12]}", n[13], n[14], t[14], t[15]]
        uc.step_notes, uc.steps_version = n, 4
        self.db.save_usecase(uc.usecase_id, uc.updated_at, uc.model_dump(mode="json"))
        return uc

    def list(self) -> list[UseCase]:
        return [self._migrate(UseCase.model_validate(r)) for r in self.db.list_usecases()]

    def delete(self, uc_id: str) -> None:
        if not self.db.delete_usecase(uc_id):
            raise NotFound("unknown_usecase", f"Use case '{uc_id}' does not exist.")

    def create(self, fields: dict[str, Any] | None = None, title: str = "") -> UseCase:
        f = UseCaseFields.model_validate(fields or {})
        ts = now_iso()
        uc = UseCase(usecase_id="uc-" + uuid.uuid4().hex[:8], title=title or f.goal_outcome[:60] or "New use case",
                     created_at=ts, updated_at=ts, rules_version=rules_version(), fields=f)
        return self._save(uc)

    def templates(self) -> list[dict[str, Any]]:
        return simulation_templates([rt.adapter for rt in self.afm.envs.values()])

    def create_simulation(self, template_id: str) -> UseCase:
        t = next((x for x in self.templates() if x["template_id"] == template_id), None)
        if t is None:
            raise NotFound("unknown_template", f"Simulation template '{template_id}' does not exist.")
        fields = {"role": t["role"], "purpose": t["agent_purpose"], "environment_type": t["environment_type"],
                  "environment_name": t["environment_name"], "adapter_id": t["adapter_id"], "target_name": t["target_name"],
                  "target_type": t["target_type"], "target_identifier": t.get("target_identifier", ""), "proposed_action": t["proposed_action"],
                  "goal_outcome": t["goal"], "constraints": t["constraints"], "mode": t.get("mode", "plan"), "evidence": t.get("evidence", "")}
        uc = self.create(fields, f"Simulation · {t['title']}")
        uc.kind, uc.template_id, uc.step_notes, uc.steps_version = "simulation", template_id, list(t["thinking"]), 4
        uc.template_info = {k: t.get(k, "") for k in ("title", "purpose", "benefit", "negative", "unknown", "source_note")}
        return self._save(uc)

    def update(self, uc_id: str, fields: dict[str, Any] | None, extra_rules: list[str] | None, title: str | None,
               step_notes: list[str] | None = None) -> UseCase:
        uc = self.get(uc_id)
        if step_notes is not None:
            if len(step_notes) != 16:
                raise AFMError("invalid_input", "A simulation has exactly 16 steps.", 422)
            uc.step_notes = [s.strip()[:600] for s in step_notes]
        if fields is not None:
            uc.fields = UseCaseFields.model_validate({**uc.fields.model_dump(), **fields})
        if extra_rules is not None:
            uc.extra_rules = [self.evaluate_rule(t, uc.fields.adapter_id) for t in extra_rules if t.strip()]
        elif fields is not None:  # adapter may have changed: re-evaluate rule enforcement
            uc.extra_rules = [self.evaluate_rule(r.text, uc.fields.adapter_id) for r in uc.extra_rules]
        if title is not None:
            uc.title = title.strip()[:80] or uc.title
        return self._save(uc)

    # ------------------------------------------------------------------ rules
    def evaluate_rule(self, text: str, adapter_id: str) -> UseCaseRule:
        t = text.strip()[:300]
        low = t.lower()
        negated = bool(re.search(_NEG, low))
        if not negated and any(re.search(p, low) for p in _WEAKEN):
            return UseCaseRule(text=t, status="conflict", explanation=(
                "This would weaken or override AFM's permanent rules (R08 human review, R10 rule integrity). Use-case rules can only narrow "
                "permissions. Remove it, or ask an administrator to change global rules as a separate operation."))
        rt = self.afm.envs.get(adapter_id)
        if negated and rt:
            for tool in tool_index(rt.adapter).values():
                if tool.scope != "environment" or not tool.modifies_state:
                    continue
                names_type = any(tt.replace("_", " ") in low for tt in tool.target_types)
                if tool.name in low or (names_type and re.search(_CHANGE, low) and tool.operation in ("configure", "set", "reserve", "delete", "stop")
                                        and (tool.operation != "delete" or "delet" in low) and (tool.operation != "stop" or "stop" in low)):
                    if tool.permission.value == "prohibited":
                        return UseCaseRule(text=t, status="enforced", blocks_tool=tool.name,
                                           explanation=f"Already enforced: '{tool.name}' is prohibited in {rt.adapter.name}.")
                    return UseCaseRule(text=t, status="enforced", blocks_tool=tool.name,
                                       explanation=f"Enforced: '{tool.name}' is blocked for this use case's assessments.")
        where = f"in {rt.adapter.name}" if rt else "because no adapter is connected"
        return UseCaseRule(text=t, status="recorded", explanation=f"Recorded and shown in assessments, but not automatically checked {where}.")

    # ------------------------------------------------------------------ environment status
    def environment_status(self, uc: UseCase) -> dict[str, Any]:
        f = uc.fields
        rt = self.afm.envs.get(f.adapter_id)
        if rt:
            d = self.afm.describe(f.adapter_id)
            return {"status": "simulated", "label": CONNECTION_LABELS["simulated"], "adapter": rt.adapter.adapter_name,
                    "environment_id": f.adapter_id, "capabilities": d.capabilities, "name": rt.adapter.name}
        typ = (f.environment_type or "").lower()
        both = f"{typ} {(f.environment_name or '').lower()}"
        fut = next((x for x in FUTURE_ADAPTERS if x.name.lower() in both), None) or \
            next((x for x in FUTURE_ADAPTERS if x.name.lower().split()[0] in typ or (typ and typ.split()[0] in x.name.lower())), None)
        if fut and fut.status == "not_connected":
            return {"status": "not_connected", "label": "Not connected: no AFM adapter for this project", "adapter": None, "environment_id": None,
                    "capabilities": {"inspect": False, "simulate": False, "execute": False}, "name": fut.name, "note": fut.note}
        if fut and typ:
            return {"status": "not_implemented", "label": CONNECTION_LABELS["not_implemented"], "adapter": None, "environment_id": None,
                    "capabilities": {"inspect": False, "simulate": False, "execute": False}, "name": fut.name, "note": fut.note}
        return {"status": "not_connected", "label": CONNECTION_LABELS["not_connected"], "adapter": None, "environment_id": None,
                "capabilities": {"inspect": False, "simulate": False, "execute": False}, "name": f.environment_name or f.environment_type or "—"}

    def summary(self, uc_id: str) -> dict[str, Any]:
        uc = self.get(uc_id)
        f = uc.fields
        env = self.environment_status(uc)
        missing = [label for key, label in (("role", "AI agent role"), ("environment_type", "environment"), ("target_name", "target object or system"),
                                            ("goal_outcome", "desired outcome")) if not getattr(f, key).strip()]
        if env["status"] != "simulated":
            missing.append("a connected adapter: AFM cannot inspect, simulate or execute in this environment")
        tools, objects, rels = [], [], 0
        if env["status"] == "simulated":
            rt = self.afm.envs[f.adapter_id]
            blocked = {r.blocks_tool for r in uc.extra_rules if r.blocks_tool}
            tools = [t.model_dump() for t in tool_index(rt.adapter, frozenset(blocked)).values()]
            v = rt.store.view()
            objects = [{"id": o.id, "name": o.name, "type": o.type, "evidence": o.evidence.value} for o in v.objects]
            rels = len(v.relationships)
            if f.target_name and not any(f.target_name.lower() in (o["name"].lower(), o["id"]) or o["name"].lower() in f.target_name.lower() for o in objects):
                missing.append(f"target “{f.target_name}” is not a known object in {rt.adapter.name} (not verified)")
        conflicts = [r.text for r in uc.extra_rules if r.status == "conflict"]
        return {"usecase": uc.model_dump(mode="json"), "rules_version": uc.rules_version, "current_rules_version": rules_version(),
                "global_rules": [r.model_dump() for r in load_conduct().rules], "environment": env, "tools": tools,
                "objects": objects, "relationship_count": rels, "missing": missing, "conflicts": conflicts,
                "can_prepare": not conflicts and env["status"] == "simulated" and bool(f.goal_outcome.strip())}

    # ------------------------------------------------------------------ chat
    def chat(self, uc_id: str, message: str) -> UseCase:
        uc = self.get(uc_id)
        msg = message.strip()[:2000]
        if not msg:
            raise AFMError("invalid_input", "The message is empty.", 422)
        rt = self.afm.envs.get(uc.fields.adapter_id)
        adapter_ctx = None
        if rt:
            adapter_ctx = {"name": rt.adapter.name, "kind": rt.adapter.kind,
                           "objects": [{"name": o.name, "type": o.type} for o in rt.store.snapshot().objects.values()],
                           "tools": [t.name for t in rt.adapter.tools()]}
        context = {"fields": {k: v for k, v in uc.fields.model_dump().items() if k != "evidence" and v},
                   "role": uc.fields.role, "environment_type": uc.fields.environment_type, "target_name": uc.fields.target_name,
                   "goal_outcome": uc.fields.goal_outcome, "adapter": adapter_ctx, "evidence": uc.fields.evidence[:1500],
                   "step_notes": {f"step_{i + 1}": s for i, s in enumerate(uc.step_notes)} if uc.step_notes else None}
        history = [{"role": m.role, "content": m.content} for m in uc.messages[-10:]]
        uc.messages.append(ChatMessage(role="user", content=msg, at=now_iso()))
        try:
            out = self.afm.llm.chat(context, history, msg)
            proposed = {k: str(v)[:300] for k, v in (out.get("proposed_fields") or {}).items() if k in USECASE_FIELDS and str(v).strip()}
            if "adapter_id" in proposed and proposed["adapter_id"] not in self.afm.envs:
                proposed.pop("adapter_id")  # the LLM cannot invent a connected adapter
            uc.messages.append(ChatMessage(
                role="assistant", content=str(out.get("reply", ""))[:4000], at=now_iso(), provider=self.afm.llm.name,
                labels=[x for x in out.get("labels", []) if x in ("llm_general", "simulated", "observed", "prediction", "unknown")] or ["llm_general"],
                proposed_fields=proposed, suggested_questions=[str(q)[:200] for q in out.get("suggested_questions", [])][:5],
                proposal_status="pending" if proposed else "none"))
        except AFMError as e:
            uc.messages.append(ChatMessage(role="assistant", content=f"The LLM tool is unavailable: {e.message} The form still works without it.",
                                           at=now_iso(), provider=self.afm.llm.name, labels=["unknown"]))
        return self._save(uc)

    def resolve_proposal(self, uc_id: str, index: int, decision: str, edited: dict[str, str] | None) -> UseCase:
        uc = self.get(uc_id)
        if not 0 <= index < len(uc.messages) or uc.messages[index].proposal_status != "pending":
            raise Conflict("no_pending_proposal", "There is no pending proposal at that position.")
        m = uc.messages[index]
        if decision == "accept":
            vals = {k: str(v) for k, v in (edited if edited is not None else m.proposed_fields).items() if k in USECASE_FIELDS}
            if "adapter_id" in vals and vals["adapter_id"] and vals["adapter_id"] not in self.afm.envs:
                raise AFMError("invalid_input", f"'{vals['adapter_id']}' is not a registered adapter.", 422)
            inputs = {k: v for k, v in vals.items() if k in INPUT_FIELDS}
            uc.fields = UseCaseFields.model_validate({**uc.fields.model_dump(), **inputs})
            steps = {int(k.split("_")[1]): v.strip()[:600] for k, v in vals.items() if k.startswith("step_") and v.strip()}
            if steps:
                if len(uc.step_notes) != 16:
                    raise AFMError("invalid_input", "This use case has no 16-step workflow to override.", 422)
                for n, text in steps.items():
                    uc.step_notes[n - 1] = text
            new_rules = [r.strip() for r in vals.get("extra_rules", "").split("\n") if r.strip()]
            texts = [r.text for r in uc.extra_rules] + [r for r in new_rules if r not in {x.text for x in uc.extra_rules}]
            uc.extra_rules = [self.evaluate_rule(t, uc.fields.adapter_id) for t in texts]  # conflicts still flagged
            m.proposal_status = "accepted"
        else:
            m.proposal_status = "dismissed"
        return self._save(uc)

    # ------------------------------------------------------------------ prepare assessment
    def prepare(self, uc_id: str) -> dict[str, Any]:
        s = self.summary(uc_id)
        uc = self.get(uc_id)
        if s["conflicts"]:
            raise Conflict("rule_conflict", "A use-case rule conflicts with AFM's permanent rules. Remove it before preparing an assessment: " + "; ".join(s["conflicts"]))
        env = s["environment"]
        if env["status"] != "simulated":
            explanation = None
            if uc.fields.target_type:
                try:
                    explanation = self.afm.llm.explain_object_type(uc.fields.environment_type or "unknown", uc.fields.target_type, None,
                                                                   "What could matter when assessing a change to this?").model_dump()
                except AFMError:
                    explanation = None
            return {"status": env["status"], "run": None, "environment": env, "missing": s["missing"], "llm_explanation": explanation,
                    "message": ("No adapter is connected for this environment. AFM has NOT inspected it, has NOT simulated anything and "
                                "cannot execute anything there. It can only list what is missing and, optionally, general LLM knowledge.")}
        if not uc.fields.goal_outcome.strip():
            raise AFMError("invalid_input", "Enter the desired outcome before preparing an assessment.", 422)
        goal_text = " ".join(x for x in (uc.fields.goal_outcome.strip(), uc.fields.constraints.strip()) if x)
        blocked = sorted({r.blocks_tool for r in uc.extra_rules if r.blocks_tool})
        run = self.afm.assess(env["environment_id"], goal_text, usecase_id=uc.usecase_id, task_role=uc.fields.role or None,
                              usecase_rules=[r.text for r in uc.extra_rules], blocked_tools=blocked,
                              human_criteria=[x for x in uc.fields.success_criteria.split("\n") if x.strip()],
                              desired_input=uc.fields.desired_input, desired_output=uc.fields.desired_output)
        uc.run_ids.append(run.run_id)
        self._save(uc)
        return {"status": "assessed", "run": run.model_dump(mode="json"), "environment": env, "missing": s["missing"], "llm_explanation": None,
                "message": "Assessment prepared in the simulated environment." + (" Analysis only: nothing will be executed unless you approve a plan." if uc.fields.mode == "analysis" else "")}
