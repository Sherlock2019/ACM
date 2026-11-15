"""HTTP API for generic AFM. Request bodies are typed; errors are returned as {"error": {"code", "message"}}."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ..adapters import llm_settings
from ..adapters.llm import find_instruction_like_text
from ..adapters.registry import FUTURE_ADAPTERS
from ..domain.conduct import load_conduct, rules_version
from ..domain.errors import AFMError, NotFound
from ..domain.profile import load_profile

router = APIRouter(prefix="/api")


def svc(request: Request):
    return request.app.state.afm


def ucs(request: Request):
    return request.app.state.usecases


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalIn(_In):
    goal_text: str = Field(min_length=1, max_length=500)


class AssessIn(_In):
    """`task_goal` is the current name; `goal_text` is still accepted for older clients."""
    environment_id: str = Field(min_length=1, max_length=64)
    task_goal: Optional[str] = Field(default=None, max_length=500)
    goal_text: Optional[str] = Field(default=None, max_length=500)
    desired_input: str = Field(default="", max_length=500)
    desired_output: str = Field(default="", max_length=500)
    success_criteria: list[str] = Field(default=[], max_length=10)
    include_llm_proposals: bool = True


class VerifyIn(_In):
    kind: Literal["criterion", "rule"]
    ref: str = Field(min_length=1, max_length=40)
    status: Literal["PASS", "FAIL", "NOT VERIFIED"]
    evidence: str = Field(min_length=1, max_length=500)
    reviewer: str = Field(default="local human", max_length=80)


class SimulateIn(_In):
    plan: dict[str, Any]
    goal_text: Optional[str] = Field(default=None, max_length=500)


class DecisionIn(_In):
    plan_id: str
    decision: Literal["approve", "reject"]
    plan_hash: str
    environment_version: int
    reviewer: str = Field(default="local human", max_length=80)
    note: str = Field(default="", max_length=500)
    criteria_agreed: bool = False  # the human explicitly agrees the success criteria (needed for a goal PASS)


class ExecuteIn(_In):
    plan_id: str
    approval_id: Optional[str] = None
    plan: Optional[dict[str, Any]] = None


class AskLLMIn(_In):
    environment_id: Optional[str] = None
    object_id: Optional[str] = None
    object_type: Optional[str] = Field(default=None, max_length=80)
    question: str = Field(default="What does this type of object generally do?", max_length=500)


class UseCaseIn(_In):
    title: Optional[str] = Field(default=None, max_length=80)
    fields: Optional[dict[str, Any]] = None
    extra_rules: Optional[list[str]] = Field(default=None, max_length=20)
    step_notes: Optional[list[str]] = None


class SimulationIn(_In):
    template_id: str = Field(min_length=1, max_length=64)


class ChatIn(_In):
    message: str = Field(min_length=1, max_length=2000)


class ProposalIn(_In):
    decision: Literal["accept", "dismiss"]
    fields: Optional[dict[str, str]] = None


# ---------------------------------------------------------------- identity & rules

@router.get("/profile")
def profile():
    return {"profile": load_profile(), "conduct": load_conduct(), "rules_version": rules_version()}


@router.get("/conduct")
def conduct():
    return {"conduct": load_conduct(), "rules_version": rules_version()}


# ---------------------------------------------------------------- environments (adapters)

@router.get("/environments")
def environments(request: Request):
    s = svc(request)
    return {"environments": [s.describe(e) for e in s.envs], "future": FUTURE_ADAPTERS}


@router.get("/environments/{env_id}")
def describe(env_id: str, request: Request):
    return svc(request).describe(env_id)


@router.get("/environments/{env_id}/view")
def view(env_id: str, request: Request):
    return svc(request).env(env_id).store.view()


@router.get("/environments/{env_id}/objects/{object_id}")
def inspect_object(env_id: str, object_id: str, request: Request):
    v = svc(request).env(env_id).store.view()
    obj = next((o for o in v.objects if o.id == object_id), None)
    if obj is None:
        raise NotFound("unknown_object", f"Object '{object_id}' does not exist in {v.name}.")
    return {"object": obj, "relationships": [r for r in v.relationships if object_id in (r.source, r.target)],
            "environment_version": v.version,
            "note": "Facts returned by the environment adapter's inspection of a simulated environment. Free-text fields are untrusted data."}


@router.get("/environments/{env_id}/relationships")
def relationships(env_id: str, request: Request):
    v = svc(request).env(env_id).store.view()
    return {"relationships": v.relationships, "completeness_note": v.completeness_note}


@router.post("/environments/{env_id}/reset")
def reset(env_id: str, request: Request):
    s = svc(request)
    version = s.reset(env_id)
    return {"environment_version": version,
            "message": f"{s.env(env_id).adapter.name} was restored. Only this local simulated environment changed; run history is kept. Earlier approvals for it are now stale."}


@router.post("/environments/{env_id}/goals/interpret")
def interpret(env_id: str, body: GoalIn, request: Request):
    return svc(request).interpret(env_id, body.goal_text)


@router.post("/environments/{env_id}/simulate")
def simulate_plan(env_id: str, body: SimulateIn, request: Request):
    return svc(request).simulate_adhoc(env_id, body.plan, body.goal_text)


# ---------------------------------------------------------------- assessments, review, execution, history

@router.post("/assessments")
def assess(body: AssessIn, request: Request):
    """Steps 1–11: task goal → rules → environment → plans → pre-check → predict → compare/recommend."""
    text = (body.task_goal or body.goal_text or "").strip()
    if not text:
        raise AFMError("invalid_input", "task_goal: a task goal is required.", 422)
    return svc(request).assess(body.environment_id, text, include_llm=body.include_llm_proposals, human_criteria=body.success_criteria,
                               desired_input=body.desired_input, desired_output=body.desired_output)


@router.get("/runs")
def runs(request: Request):
    return [
        {"run_id": r.run_id, "created_at": r.created_at, "environment_id": r.environment_id, "environment_name": r.environment_name,
         "goal": r.goal.text, "status": r.status, "environment_version": r.environment_version, "usecase_id": r.usecase_id,
         "recommended": r.recommendation.plan_id if r.recommendation else None, "executed_plan_id": r.executed_plan_id,
         "execution_status": r.execution_status, "win": r.win.overall if r.win else None,
         "decisions": [{"plan_id": d.plan_id, "decision": d.decision, "status": d.status} for d in r.decisions]}
        for r in svc(request).list_runs()
    ]


@router.get("/runs/{run_id}")
def run(run_id: str, request: Request):
    return svc(request).get_run(run_id)


@router.get("/runs/{run_id}/review/{plan_id}")
def review(run_id: str, plan_id: str, request: Request):
    return svc(request).review(run_id, plan_id)


@router.post("/runs/{run_id}/decision")
def decide(run_id: str, body: DecisionIn, request: Request):
    return svc(request).decide(run_id, body.plan_id, body.decision, body.plan_hash, body.environment_version, body.reviewer, body.note,
                               body.criteria_agreed)


@router.post("/runs/{run_id}/verify")
def verify(run_id: str, body: VerifyIn, request: Request):
    """Step 16: record a human judgment (manual criterion or broad rule); the Win is recomputed on the backend."""
    return svc(request).verify(run_id, body.kind, body.ref, body.status, body.evidence, body.reviewer)


@router.post("/runs/{run_id}/execute")
def execute(run_id: str, body: ExecuteIn, request: Request):
    return svc(request).execute(run_id, body.plan_id, body.approval_id, body.plan)


@router.get("/runs/{run_id}/comparison")
def comparison(run_id: str, request: Request):
    r = svc(request).get_run(run_id)
    if r.observation is None:
        raise NotFound("not_executed", "This run has not been executed, so there is nothing to compare yet.")
    return r.observation


# ---------------------------------------------------------------- LLM tool

@router.get("/llm/status")
def llm_status(request: Request):
    s = svc(request)
    mock = s.llm.name.startswith("mock")
    local = "· local" in s.llm.name
    cfg = llm_settings.public_view(llm_settings.load())
    return {"provider": s.llm.name, "mock": mock, "local": local, "external_calls": not mock and not local and "not configured" not in s.llm.name,
            "source": cfg["source"],
            "setup": None if mock else "Credentials stay on the backend (UI settings file or backend/.env). AFM never sends them back to the browser.",
            "privacy": ("Mock mode: nothing leaves this machine." if mock else
                        "Local model: chat and selected fields go to the model server on this machine." if local else
                        f"Chat messages and the selected use-case/object fields are sent to the configured external provider ({s.llm.name})."),
            "note": "The LLM is a consultable tool. Its output is labelled as general/inferred knowledge and never overrides rules, permissions or inspections."}


# ---------------------------------------------------------------- "Use your LLM model" (local requests only)

def _local_only(request: Request, what: str = "LLM settings can only be changed") -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise AFMError("forbidden", f"{what} from this machine.", 403)


# ---------------------------------------------------------------------- real-project mode (local only)
def prj(request: Request):
    _local_only(request, "Real-project tests can only be used")
    return request.app.state.projects


class ProjectIn(_In):
    source: Literal["local", "github"]
    path: str = Field(default="", max_length=1000)
    url: str = Field(default="", max_length=300)
    ref: str = Field(default="", max_length=200)


class CheckIn(_In):
    type: Literal["command_exit", "test_outcome", "no_other_changes", "manual"]
    command: int = Field(default=0, ge=0, le=19)
    test: str = Field(default="", max_length=300)
    expect: str = Field(default="", max_length=20)


class PredictionIn(_In):
    statement: str = Field(min_length=1, max_length=400)
    check: CheckIn
    required: bool = True


class CriterionIn(_In):
    text: str = Field(min_length=1, max_length=400)
    check: CheckIn
    source: Literal["human", "llm_proposed"] = "human"


class PlanIn(_In):
    goal: str = Field(min_length=1, max_length=600)
    desired_input: str = Field(default="", max_length=500)
    desired_output: str = Field(default="", max_length=500)
    criteria: list[CriterionIn] = Field(default=[], max_length=8)
    patch: str = Field(default="", max_length=60000)
    commands: list[list[str]] = Field(default=[], max_length=5)
    predictions: list[PredictionIn] = Field(default=[], max_length=12)
    assumptions: list[str] = Field(default=[], max_length=12)
    unknowns: list[str] = Field(default=[], max_length=12)
    plan_source: Literal["human", "llm_draft_edited"] = "human"


class DraftIn(_In):
    files: list[str] = Field(default=[], max_length=12)
    note: str = Field(default="", max_length=600)
    goal: str = Field(default="", max_length=600)  # the goal as currently typed (may be unsaved)
    desired_input: str = Field(default="", max_length=500)
    desired_output: str = Field(default="", max_length=500)


@router.post("/projects/{pid}/overview")
def describe_project(pid: str, request: Request):
    return prj(request).describe(pid)


class ProjectChatIn(_In):
    message: str = Field(min_length=1, max_length=2000)
    files: list[str] = Field(default=[], max_length=12)


@router.post("/projects/{pid}/chat")
def chat_project(pid: str, body: ProjectChatIn, request: Request):
    return prj(request).chat(pid, body.message, body.files)


class ProjectDecisionIn(_In):
    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1, max_length=80)
    plan_hash: str = Field(min_length=1, max_length=64)
    criteria_agreed: bool = False
    note: str = Field(default="", max_length=500)


class ProjectVerifyIn(_In):
    kind: Literal["prediction", "criterion", "rule"]
    ref: str = Field(min_length=1, max_length=64)
    status: Literal["PASS", "FAIL"]
    evidence: str = Field(min_length=1, max_length=500)
    reviewer: str = Field(min_length=1, max_length=80)


@router.get("/projects")
def list_projects(request: Request):
    return {"projects": prj(request).list()}


@router.post("/projects")
def create_project(body: ProjectIn, request: Request):
    return prj(request).create(body.source, body.path, body.url, body.ref)


@router.get("/projects/{pid}")
def get_project(pid: str, request: Request):
    return prj(request).get(pid)


@router.put("/projects/{pid}/plan")
def save_project_plan(pid: str, body: PlanIn, request: Request):
    return prj(request).save_plan(pid, body.model_dump())


@router.post("/projects/{pid}/draft")
def draft_project_plan(pid: str, body: DraftIn, request: Request):
    return prj(request).draft(pid, body.files, body.note, body.goal, body.desired_input, body.desired_output)


@router.post("/projects/{pid}/decision")
def decide_project(pid: str, body: ProjectDecisionIn, request: Request):
    return prj(request).decide(pid, body.decision, body.reviewer, body.plan_hash, body.criteria_agreed, body.note)


@router.post("/projects/{pid}/execute")
def execute_project(pid: str, request: Request):
    return prj(request).execute(pid)


@router.post("/projects/{pid}/verify")
def verify_project(pid: str, body: ProjectVerifyIn, request: Request):
    return prj(request).verify(pid, body.kind, body.ref, body.status, body.evidence, body.reviewer)


@router.delete("/projects/{pid}")
def delete_project(pid: str, request: Request):
    return prj(request).delete(pid)


class LLMSettingsIn(_In):
    provider: Literal["mock", "claude", "openai_compat"]
    preset: Optional[str] = Field(default=None, max_length=40)
    base_url: str = Field(default="", max_length=300)
    model: str = Field(default="", max_length=120)
    api_key: str = Field(default="", max_length=400)  # empty = keep the saved key for the same provider
    use_ant_login: bool = False
    effort: Literal["low", "medium", "high"] = "low"
    timeout: float = Field(default=60, ge=5, le=600)


def _resolve(body: LLMSettingsIn) -> llm_settings.LLMSettings:
    s = llm_settings.LLMSettings(**body.model_dump())
    old = llm_settings.load()
    if not s.api_key and old and old.api_key and old.provider == s.provider and (s.provider != "openai_compat" or old.base_url == s.base_url):
        s.api_key = old.api_key  # keep the stored key; the browser never had it
    llm_settings.validate(s)
    return s


@router.get("/llm/presets")
def llm_presets():
    return {"presets": llm_settings.PRESETS,
            "claude_models": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
            "storage": "backend/data/llm_settings.json (git-ignored, file mode 600). The key is never shown again or logged."}


@router.get("/llm/settings")
def get_llm_settings(request: Request):
    _local_only(request)
    return llm_settings.public_view(llm_settings.load())


@router.put("/llm/settings")
def put_llm_settings(body: LLMSettingsIn, request: Request):
    _local_only(request)
    s = _resolve(body)
    llm_settings.save(s)
    svc(request).set_llm(llm_settings.build(s))
    return {"saved": True, "settings": llm_settings.public_view(s), "provider": svc(request).llm.name}


@router.delete("/llm/settings")
def delete_llm_settings(request: Request):
    _local_only(request)
    llm_settings.clear()
    from ..adapters.llm import get_llm

    svc(request).set_llm(get_llm(use_ui_settings=False))
    return {"cleared": True, "provider": svc(request).llm.name, "message": "UI settings removed; using backend/.env (or the mock)."}


@router.post("/llm/test")
def test_llm(request: Request, body: Optional[LLMSettingsIn] = None):
    """Test the given (unsaved) settings, or the active provider when no body is sent. One tiny request."""
    _local_only(request)
    prov = llm_settings.build(_resolve(body)) if body else svc(request).llm
    if not hasattr(prov, "test"):
        raise AFMError("llm_provider_unavailable", "This provider cannot be tested.", 501)
    return {"provider": prov.name, **prov.test()}


@router.post("/llm/models")
def list_llm_models(body: LLMSettingsIn, request: Request):
    _local_only(request)
    if body.provider != "openai_compat":
        raise AFMError("invalid_input", "Model listing is available for OpenAI-compatible and local servers.", 422)
    s = llm_settings.LLMSettings(**{**body.model_dump(), "model": body.model or "list"})
    old = llm_settings.load()
    if not s.api_key and old and old.base_url == s.base_url:
        s.api_key = old.api_key
    prov = llm_settings.build(s)
    return {"models": prov.list_models()}


@router.post("/llm/object-type")
def ask_llm(body: AskLLMIn, request: Request):
    s = svc(request)
    observations, otype, env_name = None, body.object_type, "unspecified"
    if body.object_id:
        if not body.environment_id:
            raise AFMError("invalid_input", "Give environment_id together with object_id.", 422)
        rt = s.env(body.environment_id)
        env_name = rt.adapter.name
        obj = rt.store.snapshot().objects.get(body.object_id)
        if obj is None:
            raise NotFound("unknown_object", f"Object '{body.object_id}' does not exist in {env_name}.")
        otype = obj.type
        observations = {"id": obj.id, "type": obj.type, "name": obj.name, **{f"state.{k}": v for k, v in obj.state.items()}}
        if obj.untrusted_text:
            observations["untrusted_text"] = obj.untrusted_text
    if not otype:
        raise AFMError("invalid_input", "Give an object_id or an object_type.", 422)
    out = s.llm.explain_object_type(env_name, otype, observations, body.question)
    is_mock = s.llm.name.startswith("mock")
    payload = {"environment_type": env_name, "object_type": otype, "question": body.question, "observations": observations or {}}
    out.data_sent_to_provider = ({"sent": False, "would_send_if_provider_enabled": payload} if is_mock
                                 else {"sent": True, "provider": s.llm.name, "payload": payload})
    out.ignored_instructions = sorted(set(out.ignored_instructions) | set(
        find_instruction_like_text([str(v) for v in (observations or {}).values() if isinstance(v, str)])))
    return out


# ---------------------------------------------------------------- use cases (builder + chat)

@router.get("/usecases")
def list_usecases(request: Request):
    return [{"usecase_id": u.usecase_id, "title": u.title, "updated_at": u.updated_at, "adapter_id": u.fields.adapter_id, "kind": u.kind,
             "environment_type": u.fields.environment_type, "messages": len(u.messages), "runs": len(u.run_ids)} for u in ucs(request).list()]


@router.post("/usecases")
def create_usecase(body: UseCaseIn, request: Request):
    u = ucs(request).create(body.fields, body.title or "")
    if body.extra_rules:
        u = ucs(request).update(u.usecase_id, None, body.extra_rules, None)
    return u


@router.get("/usecases/{uc_id}")
def get_usecase(uc_id: str, request: Request):
    return ucs(request).get(uc_id)


@router.put("/usecases/{uc_id}")
def update_usecase(uc_id: str, body: UseCaseIn, request: Request):
    return ucs(request).update(uc_id, body.fields, body.extra_rules, body.title, body.step_notes)


@router.get("/simulations/templates")
def simulation_templates(request: Request):
    return [{k: t[k] for k in ("template_id", "title", "tagline", "status", "adapter_id", "purpose")} for t in ucs(request).templates()]


@router.post("/simulations")
def create_simulation(body: SimulationIn, request: Request):
    """Start a 15-step simulation from a use-case template (prefilled, editable by hand or via chat)."""
    return ucs(request).create_simulation(body.template_id)


@router.delete("/usecases/{uc_id}")
def delete_usecase(uc_id: str, request: Request):
    ucs(request).delete(uc_id)
    return {"deleted": uc_id, "message": "The use case and its chat history were deleted from local storage. Runs it created stay in history."}


@router.get("/usecases/{uc_id}/summary")
def usecase_summary(uc_id: str, request: Request):
    return ucs(request).summary(uc_id)


@router.post("/usecases/{uc_id}/chat")
def usecase_chat(uc_id: str, body: ChatIn, request: Request):
    return ucs(request).chat(uc_id, body.message)


@router.post("/usecases/{uc_id}/proposals/{index}")
def usecase_proposal(uc_id: str, index: int, body: ProposalIn, request: Request):
    return ucs(request).resolve_proposal(uc_id, index, body.decision, body.fields)


@router.post("/usecases/{uc_id}/prepare")
def usecase_prepare(uc_id: str, request: Request):
    return ucs(request).prepare(uc_id)
