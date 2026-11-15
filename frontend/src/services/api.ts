import type {
  Decision, EnvironmentDescription, EnvironmentView, EnvObject, FutureAdapter, GoalSpec, LLMPreset, LLMSettingsIn, LLMSettingsView, LLMStatus, ObjectTypeExplanation, PrepareResult,
  ProfileResponse, ProjectDraft, ProjectListItem, ProjectTest, Relationship, Review, Run, RunSummary, SimTemplate, UseCase, UseCaseFields, UseCaseListItem, UseCaseSummary,
} from "../types/afm";

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) { super(message); }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new ApiError("offline", "Cannot reach the AFM backend. Is it running on port 8530?", 0);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const e = body?.error;
    throw new ApiError(e?.code ?? "http_error", e?.message ?? `Request failed (${res.status}).`, res.status);
  }
  return body as T;
}
const send = <T>(method: string, path: string, data?: unknown) => call<T>(path, { method, body: JSON.stringify(data ?? {}) });
const e = encodeURIComponent;

export const api = {
  profile: () => call<ProfileResponse>("/profile"),
  environments: () => call<{ environments: EnvironmentDescription[]; future: FutureAdapter[] }>("/environments"),
  view: (env: string) => call<EnvironmentView>(`/environments/${e(env)}/view`),
  object: (env: string, id: string) => call<{ object: EnvObject; relationships: Relationship[]; environment_version: number; note: string }>(`/environments/${e(env)}/objects/${e(id)}`),
  interpret: (env: string, goal_text: string) => send<GoalSpec>("POST", `/environments/${e(env)}/goals/interpret`, { goal_text }),
  reset: (env: string) => send<{ environment_version: number; message: string }>("POST", `/environments/${e(env)}/reset`),
  assess: (environment_id: string, task_goal: string) => send<Run>("POST", "/assessments", { environment_id, task_goal }),
  verify: (runId: string, body: { kind: "criterion" | "rule"; ref: string; status: "PASS" | "FAIL" | "NOT VERIFIED"; evidence: string; reviewer?: string }) =>
    send<Run>("POST", `/runs/${e(runId)}/verify`, body),
  runs: () => call<RunSummary[]>("/runs"),
  run: (id: string) => call<Run>(`/runs/${e(id)}`),
  review: (runId: string, planId: string) => call<Review>(`/runs/${e(runId)}/review/${e(planId)}`),
  decide: (runId: string, body: { plan_id: string; decision: "approve" | "reject"; plan_hash: string; environment_version: number; reviewer?: string; note?: string; criteria_agreed?: boolean }) =>
    send<Decision>("POST", `/runs/${e(runId)}/decision`, body),
  execute: (runId: string, plan_id: string, approval_id: string) => send<Run>("POST", `/runs/${e(runId)}/execute`, { plan_id, approval_id }),
  llmStatus: () => call<LLMStatus>("/llm/status"),
  llmPresets: () => call<{ presets: Record<string, LLMPreset>; claude_models: string[]; storage: string }>("/llm/presets"),
  llmSettings: () => call<LLMSettingsView>("/llm/settings"),
  saveLlmSettings: (s: LLMSettingsIn) => send<{ saved: boolean; settings: LLMSettingsView; provider: string }>("PUT", "/llm/settings", s),
  clearLlmSettings: () => send<{ cleared: boolean; provider: string; message: string }>("DELETE", "/llm/settings"),
  testLlm: (s?: LLMSettingsIn) => send<{ provider: string; ok: boolean; latency_ms: number; sample: string }>("POST", "/llm/test", s),
  listLlmModels: (s: LLMSettingsIn) => send<{ models: string[] }>("POST", "/llm/models", s),
  askLLM: (environment_id: string, object_id: string) => send<ObjectTypeExplanation>("POST", "/llm/object-type", { environment_id, object_id }),
  usecases: () => call<UseCaseListItem[]>("/usecases"),
  createUseCase: (fields?: Partial<UseCaseFields>, title?: string) => send<UseCase>("POST", "/usecases", { fields, title }),
  usecase: (id: string) => call<UseCase>(`/usecases/${e(id)}`),
  updateUseCase: (id: string, body: { fields?: Partial<UseCaseFields>; extra_rules?: string[]; title?: string; step_notes?: string[] }) => send<UseCase>("PUT", `/usecases/${e(id)}`, body),
  simTemplates: () => call<SimTemplate[]>("/simulations/templates"),
  createSimulation: (template_id: string) => send<UseCase>("POST", "/simulations", { template_id }),
  explainType: (object_type: string) => send<ObjectTypeExplanation>("POST", "/llm/object-type", { object_type }),
  deleteUseCase: (id: string) => send<{ deleted: string; message: string }>("DELETE", `/usecases/${e(id)}`),
  usecaseSummary: (id: string) => call<UseCaseSummary>(`/usecases/${e(id)}/summary`),
  chat: (id: string, message: string) => send<UseCase>("POST", `/usecases/${e(id)}/chat`, { message }),
  proposal: (id: string, index: number, decision: "accept" | "dismiss", fields?: Record<string, string>) =>
    send<UseCase>("POST", `/usecases/${e(id)}/proposals/${index}`, { decision, fields }),
  prepare: (id: string) => send<PrepareResult>("POST", `/usecases/${e(id)}/prepare`),
  // real-project mode
  projects: () => call<{ projects: ProjectListItem[] }>("/projects"),
  createProject: (body: { source: "local" | "github"; path?: string; url?: string; ref?: string }) => send<ProjectTest>("POST", "/projects", body),
  project: (id: string) => call<ProjectTest>(`/projects/${e(id)}`),
  saveProjectPlan: (id: string, body: unknown) => send<ProjectTest>("PUT", `/projects/${e(id)}/plan`, body),
  draftProjectPlan: (id: string, body: { files: string[]; note: string; goal: string; desired_input: string; desired_output: string }) =>
    send<ProjectDraft>("POST", `/projects/${e(id)}/draft`, body),
  describeProject: (id: string) => send<ProjectTest>("POST", `/projects/${e(id)}/overview`),
  chatProject:(id: string, message: string, files: string[]) => send<ProjectTest>("POST", `/projects/${e(id)}/chat`, { message, files }),
  decideProject:(id: string, body: { decision: "approve" | "reject"; reviewer: string; plan_hash: string; criteria_agreed: boolean; note?: string }) =>
    send<ProjectTest>("POST", `/projects/${e(id)}/decision`, body),
  executeProject: (id: string) => send<ProjectTest>("POST", `/projects/${e(id)}/execute`),
  verifyProject: (id: string, body: { kind: "prediction" | "criterion" | "rule"; ref: string; status: "PASS" | "FAIL"; evidence: string; reviewer: string }) =>
    send<ProjectTest>("POST", `/projects/${e(id)}/verify`, body),
  deleteProject: (id: string) => send<{ deleted: string; workspace_removed: boolean }>("DELETE", `/projects/${e(id)}`),
};
