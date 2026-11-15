// Mirrors backend/app/domain/models.py (generic AFM)

export type Evidence = "observed" | "configured" | "inferred" | "unknown";
export type CheckStatus = "PASS" | "FAIL" | "REVIEW REQUIRED" | "UNKNOWN";
export type PermissionClass = "allowed" | "requires_approval" | "prohibited" | "unknown";

export interface Rule { id: string; text: string; title: string; enforcement: "enforced" | "partial" | "guidance"; how: string }
export interface ToolSpec {
  name: string; operation: string; description: string; permission: PermissionClass; modifies_state: boolean; executable: boolean;
  scope: "generic" | "environment"; parameters: Record<string, string>; target_types: string[]; reversible: boolean | null; reversible_note: string;
}
export interface Profile {
  config_version: string; name: string; tagline: string; identity: string; purpose: string; goal_source: string; environment: string;
  core_loop: string[]; permissions_summary: string[]; tools: ToolSpec[]; administrative_only: string[]; security_note: string;
}
export interface Conduct { title: string; permanent: boolean; note: string; rules: Rule[] }
export interface ProfileResponse { profile: Profile; conduct: Conduct; rules_version: string }

export interface EnvObject {
  id: string; type: string; name: string; purpose: string; state: Record<string, unknown>; accepted_actions: string[]; outputs: string[];
  behavior: string; constraints: string[]; evidence: Evidence; last_observed: string | null; known_unknowns: string[]; untrusted_text: string | null;
}
export interface Relationship { id: string; source: string; target: string; type: string; direction: string; description: string; evidence: Evidence }
export interface EnvironmentView {
  environment_id: string; name: string; kind: string; version: number; fingerprint: string; objects: EnvObject[]; relationships: Relationship[];
  completeness_note: string; layout: Record<string, [number, number]>;
}
export interface EnvironmentDescription {
  environment_id: string; name: string; kind: "simulated" | "connected"; adapter: string; summary: string; connection_status: string;
  capabilities: { inspect: boolean; simulate: boolean; execute: boolean }; limitations: string[]; rules: Rule[]; tools: ToolSpec[];
  demo_goals: string[]; definitions: string[]; object_count: number; relationship_count: number; version: number; fingerprint: string;
}
export interface FutureAdapter { name: string; kind: string; status: "not_implemented" | "not_connected"; note: string }

export interface Action {
  action_id: string; actor: string; tool: string; operation: string; target_object_id: string; parameters: Record<string, unknown>;
  expected_preconditions: string[]; permission: PermissionClass; purpose: string;
}
export interface Plan { plan_id: string; goal_id: string; title: string; actions: Action[]; assumptions: string[]; known_limitations: string[]; proposed_by: "deterministic_planner" | "llm" | "human" }
export interface GoalCriterion { id: string; kind: string; params: Record<string, unknown>; description: string; source: "adapter_proposed" | "human"; required: boolean }
/** The TASK GOAL (step 1). */
export interface GoalSpec {
  goal_id: string; environment_id: string; text: string; supported: boolean; desired_input: string; desired_output: string; intent: string | null; parameters: Record<string, unknown>;
  success_criteria: GoalCriterion[]; explanation: string; clarification_needed: string | null;
  intended_benefits: string[]; potential_negative_effects: string[]; missing_information: string[];
}
export interface Consequence {
  step: number; affected_object_id: string; relationship_to_target: string; before: Record<string, unknown>; predicted_after: Record<string, unknown>;
  description: string; type: "direct" | "connected"; evidence_rule: string; assumptions: string[];
  status: "known_in_simulation" | "conditional" | "unknown"; effect: "benefit" | "neutral" | "warning"; observable: Record<string, unknown>;
}
export interface SimulationError { step: number; action_id: string; code: string; message: string }
export interface SimulationResult {
  plan_id: string; environment_id: string; environment_version: number; environment_fingerprint: string; simulated_at: string; applies_to: string;
  feasible: boolean; consequences: Consequence[]; errors: SimulationError[]; predicted_objects: Record<string, Record<string, unknown>>; unknowns: string[];
}
export interface CheckResult { check: "capability" | "permission" | "rules" | "goal" | "human_review"; label: string; status: CheckStatus; details: string[] }
export interface PlanAssessment {
  plan: Plan; plan_hash: string; simulation: SimulationResult; checks: CheckResult[]; approvable: boolean; approvable_reason: string;
  meets_goal_and_rules: boolean; summary: string; warnings: number; benefits: number; changed_objects: number; reversible: boolean | null;
  rejected_before_prediction: boolean;
}
export interface LLMRejection { raw: Record<string, unknown>; reasons: string[] }
export interface Decision {
  decision: "approve" | "reject"; plan_id: string; plan_hash: string; environment_version: number; environment_fingerprint: string;
  reviewer: string; note: string; decided_at: string; approval_id: string; status: "active" | "used" | "invalidated" | "rejected"; invalidated_reason: string | null;
  policy_version: string; criteria_agreed: boolean;
}
export type CompareResult = "MATCH" | "MISMATCH" | "NOT VERIFIED";
export interface ComparisonItem { object_id: string; field: string; predicted: unknown; observed: unknown; result: CompareResult; note: string; required: boolean }
export interface Observation {
  observed_at: string; environment_version_after: number; items: ComparisonItem[]; unchanged_objects: string[];
  method: string; source: "simulation" | "connected"; simulated: boolean;
}
export type WinStatus = "PASS" | "FAIL" | "NOT VERIFIED";
export interface WinCheck { name: string; status: WinStatus; evidence: string; phase: string }
export interface WinCondition { condition: "prediction_accuracy" | "task_goal" | "rule_compliance"; question: string; status: WinStatus; checks: WinCheck[]; summary: string }
export interface WinEvaluation { evaluated_at: string; simulated: boolean; conditions: WinCondition[]; overall: "WIN" | "NOT A WIN" | "NOT VERIFIED"; explanation: string }
export interface HumanVerification { kind: "criterion" | "rule"; ref: string; status: WinStatus; evidence: string; reviewer: string; at: string }
export type ExecutionStatus = "not_attempted" | "executed" | "rejected" | "not_approved" | "unsupported" | "failed";
export interface TraceEvent { at: string; event: string; detail: string }
export type RunStatus = "unsupported_goal" | "no_viable_plan" | "awaiting_review" | "approved" | "rejected" | "executed" | "stale" | "execution_blocked";
export interface Run {
  run_id: string; created_at: string; environment_id: string; environment_name: string; rules_version: string; usecase_id: string | null;
  task_role: string | null; usecase_rules: string[]; blocked_tools: string[]; policy_version: string; execution_status: ExecutionStatus;
  win: WinEvaluation | null; verifications: HumanVerification[]; goal: GoalSpec; environment_version: number; environment_fingerprint: string;
  assessments: PlanAssessment[]; llm_rejections: LLMRejection[]; recommendation: { plan_id: string | null; reason: string } | null;
  status: RunStatus; decisions: Decision[]; executed_plan_id: string | null; observation: Observation | null; trace: TraceEvent[];
}
export interface RunSummary {
  run_id: string; created_at: string; environment_id: string; environment_name: string; goal: string; status: RunStatus; environment_version: number;
  usecase_id: string | null; recommended: string | null; executed_plan_id: string | null; decisions: { plan_id: string; decision: string; status: string }[];
  execution_status: ExecutionStatus; win: WinEvaluation["overall"] | null;
}
export interface Review {
  run_id: string; environment_id: string; environment_name: string; goal: GoalSpec; assessment: PlanAssessment;
  current_state: Record<string, Record<string, unknown>>; evidence: Record<string, Evidence>; environment_version_now: number; stale: boolean;
  execution_supported: boolean; decisions: Decision[]; run_status: RunStatus;
}
export interface ObjectTypeExplanation {
  source: string; provider: string; object_type: string; environment_type: string; explanation: string; common_inputs: string[]; common_outputs: string[];
  typical_behavior: string; potential_relationships: string[]; suggested_read_only_inspections: string[]; assumptions: string[]; unknowns: string[];
  data_sent_to_provider: Record<string, unknown> | null; ignored_instructions: string[];
}
export interface LLMStatus { provider: string; mock: boolean; local: boolean; source: "ui" | "environment"; external_calls: boolean; setup: string | null; privacy: string; note: string }
export interface LLMPreset { kind: "cloud" | "local"; label: string; base_url: string; model_hint: string; key_required: boolean; key_help: string }
export interface LLMSettingsView {
  source: "ui" | "environment"; provider: "mock" | "claude" | "openai_compat" | null; preset?: string | null; base_url?: string; model?: string;
  use_ant_login?: boolean; effort?: "low" | "medium" | "high"; timeout?: number; has_key?: boolean; key_hint?: string; local?: boolean;
}
export interface LLMSettingsIn {
  provider: "mock" | "claude" | "openai_compat"; preset?: string | null; base_url?: string; model?: string; api_key?: string;
  use_ant_login?: boolean; effort?: "low" | "medium" | "high"; timeout?: number;
}

// ---- use cases
export interface UseCaseRule { text: string; status: "recorded" | "enforced" | "conflict"; blocks_tool: string | null; explanation: string }
export interface ChatMessage {
  role: "user" | "assistant"; content: string; at: string; provider: string; labels: string[]; proposed_fields: Record<string, string>;
  suggested_questions: string[]; proposal_status: "none" | "pending" | "accepted" | "dismissed";
}
export interface UseCaseFields {
  role: string; purpose: string; environment_type: string; environment_name: string; environment_description: string; adapter_id: string;
  target_name: string; target_type: string; target_identifier: string; target_known_info: string; proposed_action: string;
  goal_outcome: string; desired_input: string; desired_output: string; success_criteria: string; constraints: string; mode: "analysis" | "plan"; evidence: string;
}
export interface UseCase {
  usecase_id: string; title: string; created_at: string; updated_at: string; rules_version: string; fields: UseCaseFields;
  kind: "builder" | "simulation"; template_id: string; step_notes: string[]; template_info: Record<string, string>;
  extra_rules: UseCaseRule[]; messages: ChatMessage[]; run_ids: string[];
}
export interface UseCaseListItem { usecase_id: string; title: string; updated_at: string; adapter_id: string; kind: string; environment_type: string; messages: number; runs: number }
export interface SimTemplate { template_id: string; title: string; tagline: string; status: "simulated" | "not_connected"; adapter_id: string; purpose: string }
export interface EnvStatus {
  status: "simulated" | "not_implemented" | "not_connected"; label: string; adapter: string | null; environment_id: string | null;
  capabilities: { inspect: boolean; simulate: boolean; execute: boolean }; name: string; note?: string;
}
export interface UseCaseSummary {
  usecase: UseCase; rules_version: string; current_rules_version: string; global_rules: Rule[]; environment: EnvStatus; tools: ToolSpec[];
  objects: { id: string; name: string; type: string; evidence: Evidence }[]; relationship_count: number; missing: string[]; conflicts: string[]; can_prepare: boolean;
}
export interface PrepareResult { status: string; run: Run | null; environment: EnvStatus; missing: string[]; llm_explanation: ObjectTypeExplanation | null; message: string }
