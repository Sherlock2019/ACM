"""Typed schemas for the generic AFM core. Nothing here is specific to any one environment."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Strict(BaseModel):
    """Base model: unknown fields are rejected instead of silently accepted."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- evidence & status


class Evidence(str, Enum):
    observed = "observed"  # returned by a trusted inspection (adapter) or after an approved execution
    configured = "configured"  # explicitly defined in the scenario
    inferred = "inferred"  # suggested by the LLM or a prediction
    unknown = "unknown"  # not established


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW_REQUIRED = "REVIEW REQUIRED"
    UNKNOWN = "UNKNOWN"


class PermissionClass(str, Enum):
    allowed = "allowed"
    requires_approval = "requires_approval"
    prohibited = "prohibited"
    unknown = "unknown"


# --------------------------------------------------------------------------- rules, tools, profile


class Rule(Strict):
    id: str
    text: str
    title: str = ""
    enforcement: Literal["enforced", "partial", "guidance"] = "enforced"
    how: str = ""


class ToolSpec(Strict):
    name: str
    operation: str
    description: str
    permission: PermissionClass
    modifies_state: bool
    executable: bool
    scope: Literal["generic", "environment"] = "environment"
    parameters: dict[str, str] = {}  # name -> human-readable type, e.g. "int (1024-65535)"
    target_types: list[str] = []
    reversible: Optional[bool] = None  # R27: does a recovery path exist in principle?
    reversible_note: str = ""


class AFMProfile(Strict):
    config_version: str
    name: str
    tagline: str
    identity: str
    purpose: str
    goal_source: str
    environment: str
    core_loop: list[str]
    permissions_summary: list[str]
    tools: list[ToolSpec]
    administrative_only: list[str]
    security_note: str


class ConductRules(Strict):
    title: str
    permanent: bool
    note: str
    rules: list[Rule]


# --------------------------------------------------------------------------- environment


class EnvObject(Strict):
    id: str
    type: str
    name: str
    purpose: str
    state: dict[str, Any]
    accepted_actions: list[str] = []
    outputs: list[str] = []
    behavior: str = ""
    constraints: list[str] = []
    evidence: Evidence
    field_evidence: dict[str, Evidence] = {}
    last_observed: Optional[str] = None
    known_unknowns: list[str] = []
    untrusted_text: Optional[str] = Field(
        default=None,
        description="Free text found in the object (e.g. a note or comment). Treated as data, never as instructions.",
    )


class Relationship(Strict):
    id: str
    source: str
    target: str
    type: str
    direction: Literal["source_to_target", "bidirectional"] = "source_to_target"
    description: str
    evidence: Evidence


class EnvironmentView(Strict):
    environment_id: str
    name: str
    kind: str
    version: int
    fingerprint: str
    objects: list[EnvObject]
    relationships: list[Relationship]
    completeness_note: str
    layout: dict[str, list[float]] = {}


class EnvironmentDescription(Strict):
    environment_id: str
    name: str
    kind: Literal["simulated", "connected"]
    adapter: str
    summary: str
    connection_status: str
    capabilities: dict[str, bool]  # inspect / simulate / execute
    limitations: list[str]
    rules: list[Rule]  # environment-specific rules
    tools: list[ToolSpec]  # environment-specific tools
    demo_goals: list[str]
    definitions: list[str]
    object_count: int
    relationship_count: int
    version: int
    fingerprint: str


class FutureAdapter(Strict):
    name: str
    kind: str
    status: Literal["not_implemented", "not_connected"]
    note: str


# --------------------------------------------------------------------------- actions & plans


class Action(Strict):
    action_id: str
    actor: str = "AFM"
    tool: str
    operation: str
    target_object_id: str
    parameters: dict[str, Any] = {}
    expected_preconditions: list[str] = []
    permission: PermissionClass = PermissionClass.unknown
    purpose: str = ""


class Plan(Strict):
    plan_id: str
    goal_id: str
    title: str = ""
    actions: list[Action] = Field(min_length=1)
    assumptions: list[str] = []
    known_limitations: list[str] = []
    proposed_by: Literal["deterministic_planner", "llm", "human"] = "deterministic_planner"


# --------------------------------------------------------------------------- goals


class GoalCriterion(Strict):
    id: str
    kind: str  # interpreted by the environment adapter; "manual" = human-written, not machine-checkable
    params: dict[str, Any] = {}
    description: str
    source: Literal["adapter_proposed", "human"] = "adapter_proposed"  # never presented as human-approved unless agreed
    required: bool = True


class GoalSpec(Strict):
    """The TASK GOAL (step 1). Named GoalSpec in code for compatibility."""
    goal_id: str
    environment_id: str
    text: str
    supported: bool
    desired_input: str = ""
    desired_output: str = ""
    intent: Optional[str] = None
    parameters: dict[str, Any] = {}
    success_criteria: list[GoalCriterion] = []
    explanation: str = ""
    clarification_needed: Optional[str] = None
    # R30 goal pre-check, filled before any plan is generated
    intended_benefits: list[str] = []
    potential_negative_effects: list[str] = []
    missing_information: list[str] = []


# --------------------------------------------------------------------------- simulation


class Consequence(Strict):
    step: int
    affected_object_id: str
    relationship_to_target: str
    before: dict[str, Any]
    predicted_after: dict[str, Any]
    description: str
    type: Literal["direct", "connected"]
    evidence_rule: str
    assumptions: list[str] = []
    status: Literal["known_in_simulation", "conditional", "unknown"]
    effect: Literal["benefit", "neutral", "warning"] = "neutral"  # R29
    observable: dict[str, Any] = {}  # measurable predicted values the adapter can re-measure after execution


class SimulationError(Strict):
    step: int
    action_id: str
    code: str
    message: str


class SimulationResult(Strict):
    plan_id: str
    environment_id: str
    environment_version: int
    environment_fingerprint: str
    simulated_at: str
    applies_to: str
    feasible: bool
    consequences: list[Consequence]
    errors: list[SimulationError]
    predicted_objects: dict[str, dict[str, Any]]
    unknowns: list[str]


class CheckResult(Strict):
    check: Literal["capability", "permission", "rules", "goal", "human_review"]
    label: str
    status: CheckStatus
    details: list[str]


class PlanAssessment(Strict):
    plan: Plan
    plan_hash: str
    simulation: SimulationResult
    checks: list[CheckResult]
    approvable: bool
    approvable_reason: str
    meets_goal_and_rules: bool
    summary: str
    warnings: int = 0
    benefits: int = 0
    changed_objects: int = 0
    reversible: Optional[bool] = None
    rejected_before_prediction: bool = False  # step 9: failed capability/permission pre-check, never simulated


class LLMRejection(Strict):
    raw: dict[str, Any]
    reasons: list[str]


class Recommendation(Strict):
    plan_id: Optional[str]
    reason: str


# --------------------------------------------------------------------------- runs, approval, observation


class Decision(Strict):
    decision: Literal["approve", "reject"]
    plan_id: str
    plan_hash: str
    environment_version: int
    environment_fingerprint: str
    reviewer: str
    note: str = ""
    decided_at: str
    approval_id: str
    status: Literal["active", "used", "invalidated", "rejected"]
    invalidated_reason: Optional[str] = None
    policy_version: str = ""
    criteria_agreed: bool = False  # the human explicitly agreed the success criteria at review


class ComparisonItem(Strict):
    object_id: str
    field: str
    predicted: Any
    observed: Any
    result: Literal["MATCH", "MISMATCH", "NOT VERIFIED"]
    note: str = ""
    required: bool = True  # required predictions decide prediction accuracy; informational ones do not

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, v):
        if isinstance(v, dict) and v.get("result") == "DIFFERENCE":  # runs stored before the rename
            v = {**v, "result": "MISMATCH"}
        return v


class Observation(Strict):
    observed_at: str
    environment_version_after: int
    items: list[ComparisonItem]
    unchanged_objects: list[str]
    snapshot: dict[str, Any] = {}  # observed environment state, used to judge the task goal on evidence
    method: str = "Fresh read-only inspection of the environment after execution"
    source: Literal["simulation", "connected"] = "simulation"
    simulated: bool = True


WinStatus = Literal["PASS", "FAIL", "NOT VERIFIED"]


class WinCheck(Strict):
    name: str
    status: WinStatus
    evidence: str
    phase: str = ""


class WinCondition(Strict):
    condition: Literal["prediction_accuracy", "task_goal", "rule_compliance"]
    question: str
    status: WinStatus
    checks: list[WinCheck]
    summary: str


class HumanVerification(Strict):
    kind: Literal["criterion", "rule"]
    ref: str  # criterion id or rule id
    status: WinStatus
    evidence: str
    reviewer: str
    at: str


class WinEvaluation(Strict):
    evaluated_at: str
    simulated: bool
    conditions: list[WinCondition]
    overall: Literal["WIN", "NOT A WIN", "NOT VERIFIED"]
    explanation: str


class TraceEvent(Strict):
    at: str
    event: str
    detail: str


RunStatus = Literal[
    "unsupported_goal",
    "no_viable_plan",
    "awaiting_review",
    "approved",
    "rejected",
    "executed",
    "stale",
    "execution_blocked",
]


class Run(Strict):
    run_id: str
    created_at: str
    environment_id: str
    environment_name: str
    rules_version: str = ""
    usecase_id: Optional[str] = None
    task_role: Optional[str] = None
    usecase_rules: list[str] = []
    blocked_tools: list[str] = []
    policy_version: str = ""
    execution_status: Literal["not_attempted", "executed", "rejected", "not_approved", "unsupported", "failed"] = "not_attempted"
    win: Optional[WinEvaluation] = None
    verifications: list[HumanVerification] = []
    goal: GoalSpec
    environment_version: int
    environment_fingerprint: str
    assessments: list[PlanAssessment] = []
    llm_rejections: list[LLMRejection] = []
    recommendation: Optional[Recommendation] = None
    status: RunStatus
    decisions: list[Decision] = []
    executed_plan_id: Optional[str] = None
    observation: Optional[Observation] = None
    trace: list[TraceEvent] = []

    @model_validator(mode="after")
    def _legacy_execution_status(self):
        # runs executed before execution_status existed
        if self.executed_plan_id and self.execution_status == "not_attempted":
            self.execution_status = "executed"
        elif self.status == "rejected" and self.execution_status == "not_attempted":
            self.execution_status = "rejected"
        return self

    def log(self, event: str, detail: str) -> None:
        self.trace.append(TraceEvent(at=now_iso(), event=event, detail=detail))


# --------------------------------------------------------------------------- use cases (builder + chat)


class UseCaseRule(Strict):
    text: str
    status: Literal["recorded", "enforced", "conflict"] = "recorded"
    blocks_tool: Optional[str] = None
    explanation: str = ""


class ChatMessage(Strict):
    role: Literal["user", "assistant"]
    content: str
    at: str
    provider: str = ""
    labels: list[str] = []
    proposed_fields: dict[str, str] = {}
    suggested_questions: list[str] = []
    proposal_status: Literal["none", "pending", "accepted", "dismissed"] = "none"


class UseCaseFields(Strict):
    role: str = ""
    purpose: str = ""
    environment_type: str = ""
    environment_name: str = ""
    environment_description: str = ""
    adapter_id: str = ""
    target_name: str = ""
    target_type: str = ""
    target_identifier: str = ""
    target_known_info: str = ""
    proposed_action: str = ""
    goal_outcome: str = ""  # the TASK GOAL
    desired_input: str = ""
    desired_output: str = ""
    success_criteria: str = ""
    constraints: str = ""
    mode: Literal["analysis", "plan"] = "plan"
    evidence: str = ""  # user-provided notes, snippets, paths: untrusted input that may need verification


class UseCase(Strict):
    usecase_id: str
    title: str
    created_at: str
    updated_at: str
    rules_version: str
    kind: Literal["builder", "simulation"] = "builder"
    template_id: str = ""
    step_notes: list[str] = []  # 16 prefilled "how AFM thinks" notes, editable by the human
    steps_version: int = 1  # 1 = goal at step 7 (15 steps); 2 = goal at step 1 (15 steps); 4 = 16-step workflow with Win
    template_info: dict[str, str] = {}  # purpose, benefit, negative, unknown, source_note
    fields: UseCaseFields
    extra_rules: list[UseCaseRule] = []
    messages: list[ChatMessage] = []
    run_ids: list[str] = []


# --------------------------------------------------------------------------- LLM tool output


class ObjectTypeExplanation(Strict):
    source: str = "LLM-generated (general knowledge, not an inspection of the actual object)"
    provider: str
    object_type: str
    environment_type: str
    explanation: str
    common_inputs: list[str]
    common_outputs: list[str]
    typical_behavior: str
    potential_relationships: list[str]
    suggested_read_only_inspections: list[str]
    assumptions: list[str]
    unknowns: list[str]
    data_sent_to_provider: Optional[dict[str, Any]] = None
    ignored_instructions: list[str] = []
