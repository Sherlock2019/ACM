"""Data model of a real-project test (stored as one JSON document per test)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..domain.models import WinEvaluation

CheckType = Literal["command_exit", "test_outcome", "no_other_changes", "manual"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Check(_M):
    """How an observation is measured. Shared by predictions (expected consequence) and success criteria."""
    type: CheckType
    command: int = Field(default=0, ge=0, le=19)  # index into the approved commands
    test: str = Field(default="", max_length=300)  # test id, e.g. tests/test_api.py::test_orders
    expect: str = Field(default="", max_length=20)  # command_exit: "0" | "nonzero"; test_outcome: "passed" | "failed"


class Prediction(_M):
    id: str
    statement: str = Field(min_length=1, max_length=400)
    check: Check
    required: bool = True


class Criterion(_M):
    id: str
    text: str = Field(min_length=1, max_length=400)
    check: Check
    source: Literal["human", "llm_proposed"] = "human"


class CommandResult(_M):
    phase: Literal["baseline", "after"]
    argv: list[str]
    exit_code: Optional[int] = None
    timed_out: bool = False
    duration_ms: int = 0
    output_tail: str = ""
    tests: dict[str, str] = {}
    error: str = ""  # why the result cannot be used as evidence (missing tool/dependency, timeout...)


class PrecheckItem(_M):
    name: str
    status: Literal["PASS", "FAIL"]
    detail: str


class Decision(_M):
    status: Literal["approved", "rejected", "used", "invalidated"]
    reviewer: str
    at: str
    plan_hash: str
    policy_version: str
    criteria_agreed: bool = False
    note: str = ""


class ComparisonRow(_M):
    prediction_id: str
    statement: str
    expected: str
    observed: str
    result: Literal["MATCH", "MISMATCH", "NOT VERIFIED"]
    required: bool = True


class Verification(_M):
    kind: Literal["prediction", "criterion", "rule"]
    ref: str
    status: Literal["PASS", "FAIL"]
    evidence: str
    reviewer: str
    at: str


class LogEntry(_M):
    at: str
    step: int
    text: str


class ChatMessage(_M):
    role: Literal["user", "assistant"]
    content: str
    at: str
    files: list[str] = []  # files sent to the LLM with this message
    provider: str = ""
    draft: Optional[dict[str, Any]] = None  # the LLM's proposed plan (never applied until the human uses + saves it)


class ProjectTest(_M):
    id: str
    created_at: str
    updated_at: str
    name: str
    source: Literal["local", "github"]
    origin: str  # absolute local path or https GitHub URL
    ref: str = ""
    workspace: str
    workspace_kind: Literal["git_clone", "folder_copy", "github_clone"]
    commit: str
    origin_fingerprint: str = ""  # local only: proves the user's folder was not changed
    inspection: dict[str, Any] = {}
    # step 1: task goal
    goal: str = ""
    desired_input: str = ""
    desired_output: str = ""
    criteria: list[Criterion] = []
    # plan (steps 6-10)
    patch: str = ""
    commands: list[list[str]] = []
    predictions: list[Prediction] = []
    plan_source: Literal["human", "llm_draft_edited"] = "human"
    plan_title: str = ""
    consequences: list[dict[str, Any]] = []  # predicted per-object consequences of the chosen plan (LLM-inferred or ACFM search)
    alternatives: list[dict[str, Any]] = []  # the other plans that were compared (title, applies, risks, files)
    assumptions: list[str] = []
    unknowns: list[str] = []
    plan_hash: str = ""
    predictions_saved_at: str = ""
    precheck: list[PrecheckItem] = []
    # review / execution / evaluation
    decision: Optional[Decision] = None
    status: Literal["inspected", "planned", "approved", "rejected", "executed", "failed"] = "inspected"
    executed_at: str = ""
    patch_applied: bool = False
    results: list[CommandResult] = []
    comparison: list[ComparisonRow] = []
    verifications: list[Verification] = []
    win: Optional[WinEvaluation] = None
    log: list[LogEntry] = []
    chat: list[ChatMessage] = []
    overview: Optional[dict[str, Any]] = None  # LLM-generated: name, goal, features, suggested changes (labelled, never authoritative)
