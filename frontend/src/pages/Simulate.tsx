import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ChatPanel } from "../components/ChatPanel";
import { EnvStage, type StagePhase } from "../components/EnvStage";
import { Icon } from "../components/icons";
import { ChecksList, ConsequenceList, nameOf, predictedDeltas } from "../components/PlanParts";
import { RelationshipGraph } from "../components/RelationshipGraph";
import { Capabilities, ConnectionBadge, EffectBadge, EnforcementBadge, ErrorBox, EvidenceBadge, Loading, PermissionBadge, Plain, ResultBadge, StatusBadge, fmtTime, fmtVal } from "../components/ui";
import { WinPanel } from "../components/WinPanel";
import { api } from "../services/api";
import { go, useAFM } from "../state";
import type { EnvironmentView, ObjectTypeExplanation, PlanAssessment, PrepareResult, Run, UseCase, UseCaseSummary } from "../types/afm";

type StepStatus = "completed" | "in_progress" | "optional" | "not_started" | "ready" | "waiting_info" | "waiting_review" | "approved" | "rejected" | "failed" | "unsupported" | "not_verified";
const STATUS: Record<StepStatus, [string, string, string]> = {
  completed: ["st-pass", "✓", "Completed"], approved: ["st-pass", "✓", "Approved"], in_progress: ["st-review", "…", "In progress"],
  optional: ["st-unknown", "·", "Optional"], not_started: ["st-unknown", "○", "Not started"], ready: ["st-review", "▸", "Ready to run"],
  waiting_info: ["st-review", "!", "Waiting for information"], waiting_review: ["st-review", "!", "Waiting for review"],
  rejected: ["st-fail", "✕", "Rejected"], failed: ["st-fail", "✕", "Failed"], unsupported: ["st-unknown", "–", "Unsupported"], not_verified: ["st-unknown", "?", "Not verified"],
};
const EV: Record<string, string> = { configured: "ev-configured", observed: "ev-observed", llm: "ev-inferred", predicted: "ev-inferred", conditional: "ev-inferred", unknown: "ev-unknown", human: "ev-configured", illustrative: "ev-unknown", simulated: "ev-configured" };
const EV_LABEL: Record<string, string> = { configured: "configured", observed: "observed", llm: "LLM-generated", predicted: "predicted", conditional: "conditional", unknown: "unknown", human: "human input", illustrative: "illustrative", simulated: "simulated" };

function StepBadge({ s }: { s: StepStatus }) {
  const [cls, ico, label] = STATUS[s];
  return <span className={`badge ${cls}`}><span className="ico" aria-hidden="true">{ico}</span>{label}</span>;
}

function Step({ n, title, status, evidence, note, onNote, children, open }: {
  n: number; title: string; status: StepStatus; evidence: string[]; note: string; onNote: (v: string) => void; children: ReactNode; open?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(note);
  useEffect(() => setDraft(note), [note]);
  return (
    <li className={`step step-${status}`}>
      <details open={open}>
        <summary>
          <span className="step-n mono">{n}</span>
          <span className="step-title">{title}</span>
          <span className="row" style={{ gap: 6, marginLeft: "auto" }}>{evidence.map((e) => <span key={e} className={`ev ${EV[e]}`}>{EV_LABEL[e]}</span>)}<StepBadge s={status} /></span>
        </summary>
        <div className="step-body">
          <div className="step-note">
            <span className="hud-label">How AFM thinks</span>
            {editing ? (
              <div className="stack mt-s"><textarea className="field" rows={2} value={draft} onChange={(e) => setDraft(e.target.value)} aria-label={`Edit note for step ${n}`} />
                <div className="row"><button className="btn-primary" onClick={() => { onNote(draft); setEditing(false); }}>Save note</button><button className="btn-ghost" onClick={() => setEditing(false)}>Cancel</button></div></div>
            ) : <p className="small mt-s">{note} <button className="btn-ghost tiny" onClick={() => setEditing(true)} aria-label={`Edit note for step ${n}`}>edit</button></p>}
          </div>
          <div className="mt">{children}</div>
        </div>
      </details>
    </li>
  );
}

/** Step 10: predicted impact of one plan on EVERY object and on the whole environment. */
function EnvImpact({ a, view, names }: { a: PlanAssessment; view: EnvironmentView; names: Record<string, string> }) {
  const deltas = predictedDeltas(a);
  const ids = [...view.objects.map((o) => o.id), ...Object.keys(a.simulation.predicted_objects).filter((id) => !view.objects.some((o) => o.id === id))];
  const rows = ids.map((id) => {
    const cs = a.simulation.consequences.filter((c) => c.affected_object_id === id);
    const unknown = cs.some((c) => c.status === "unknown");
    const effect = cs.some((c) => c.effect === "warning") ? "warning" : cs.some((c) => c.effect === "benefit") ? "benefit" : "neutral";
    const obj = view.objects.find((o) => o.id === id);
    const scalar = obj ? Object.entries(obj.state).find(([, v]) => typeof v !== "object") : undefined;
    return { id, cs, unknown, effect, direct: cs.some((c) => c.type === "direct"), now: scalar ? `${scalar[0]}: ${fmtVal(scalar[1])}` : "new",
      change: unknown ? "unknown: not simulated" : deltas[id] ?? (cs.length ? "no measurable change" : "unchanged"), status: cs[0]?.status };
  });
  const changed = rows.filter((r) => !r.unknown && r.change !== "unchanged" && r.change !== "no measurable change").length;
  const warnings = rows.filter((r) => r.effect === "warning").length, benefits = rows.filter((r) => r.effect === "benefit").length, unknowns = rows.filter((r) => r.unknown).length;
  return (
    <div className="stack">
      <p className="small"><strong>Whole environment · {a.plan.plan_id}:</strong> {rows.length} known objects: {changed} changed · {rows.length - changed - unknowns} unchanged · <span style={{ color: "var(--pass)" }}>+{benefits} benefit</span> · <span style={{ color: "var(--review)" }}>⚠{warnings} warning</span> · {unknowns} unknown. <span className="faint tiny">Known objects only (R19). Predictions, not observations.</span></p>
      <div className="table-wrap"><table className="tbl">
        <thead><tr><th scope="col">Object</th><th scope="col">Now (observed)</th><th scope="col">Predicted</th><th scope="col">Effect</th><th scope="col">How sure</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.id}>
            <td className="strong">{nameOf(names, r.id)}<div className="faint tiny">{r.direct ? "direct (target)" : r.cs.length ? "connected" : "not affected"}</div></td>
            <td className="mono small">{r.now}</td>
            <td className="mono small" style={{ color: r.effect === "warning" ? "var(--review)" : undefined }}>{r.change}</td>
            <td>{r.unknown ? <span className="ev ev-unknown">unknown</span> : <EffectBadge e={r.effect as "benefit" | "neutral" | "warning"} />}</td>
            <td className="tiny">{r.status ? r.status.replace(/_/g, " ") : "—"}</td>
          </tr>
        ))}</tbody>
      </table></div>
      <details><summary className="small dim" style={{ cursor: "pointer" }}>Every consequence with its rule, assumptions and evidence</summary><div className="mt-s"><ConsequenceList items={a.simulation.consequences} names={names} /></div></details>
    </div>
  );
}

export function Simulate({ usecaseId }: { usecaseId?: string }) {
  const { profile, envs, views, refresh, select } = useAFM();
  const [uc, setUc] = useState<UseCase | null>(null);
  const [sum, setSum] = useState<UseCaseSummary | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [draft, setDraft] = useState({ role: "", purpose: "", goal_outcome: "", constraints: "", rules: "", desired_input: "", desired_output: "", success_criteria: "" });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [prep, setPrep] = useState<PrepareResult | null>(null);
  const [llmTypes, setLlmTypes] = useState<Record<string, ObjectTypeExplanation | string>>({});
  const [planSel, setPlanSel] = useState<string | null>(null);
  const [ack, setAck] = useState(false);
  const [agree, setAgree] = useState(false);
  const dlg = useRef<HTMLDialogElement>(null);

  const adopt = useCallback(async (u: UseCase) => {
    setUc(u);
    const f = u.fields;
    setDraft({ role: f.role, purpose: f.purpose, goal_outcome: f.goal_outcome, constraints: f.constraints, rules: u.extra_rules.map((r) => r.text).join("\n"),
      desired_input: f.desired_input ?? "", desired_output: f.desired_output ?? "", success_criteria: f.success_criteria ?? "" });
    setSum(await api.usecaseSummary(u.usecase_id).catch(() => null));
    const last = u.run_ids[u.run_ids.length - 1];
    const r = last ? await api.run(last).catch(() => null) : null;
    setRun(r);
    setPlanSel(r?.executed_plan_id ?? r?.recommendation?.plan_id ?? r?.assessments.find((a) => a.approvable)?.plan.plan_id ?? r?.assessments[0]?.plan.plan_id ?? null);
    if (f.adapter_id) select(f.adapter_id);
  }, [select]);
  useEffect(() => { if (usecaseId) api.usecase(usecaseId).then(adopt).catch((e) => setErr(e.message)); }, [usecaseId, adopt]);

  const act = async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setErr(null);
    try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  const saveInputs = async () => {
    if (!uc) return;
    const { rules, ...fields } = draft;
    await adopt(await api.updateUseCase(uc.usecase_id, { fields, extra_rules: rules.split("\n").map((s) => s.trim()).filter(Boolean) }));
  };
  const saveNote = (i: number) => (v: string) => act("note", async () => {
    if (!uc) return;
    const notes = [...uc.step_notes]; notes[i] = v;
    await adopt(await api.updateUseCase(uc.usecase_id, { step_notes: notes }));
  });
  const runSim = () => act("run", async () => {
    if (!uc) return;
    await saveInputs();
    setPrep(await api.prepare(uc.usecase_id));
    await adopt(await api.usecase(uc.usecase_id)); await refresh();
  });
  const send = async (text: string) => {
    let ok = false;
    await act("chat", async () => { if (!uc) return; await saveInputs(); await adopt(await api.chat(uc.usecase_id, text)); ok = true; });
    return ok;
  };
  const resolve = (i: number, d: "accept" | "dismiss", f?: Record<string, string>) => act("proposal", async () => {
    if (!uc) return; await saveInputs(); await adopt(await api.proposal(uc.usecase_id, i, d, f));
  });
  const decide = (decision: "approve" | "reject") => act("decide", async () => {
    if (!run || !planSel) return;
    const a = run.assessments.find((x) => x.plan.plan_id === planSel)!;
    await api.decide(run.run_id, { plan_id: planSel, decision, plan_hash: a.plan_hash, environment_version: run.environment_version, reviewer: "local human", criteria_agreed: decision === "approve" && agree });
    dlg.current?.close(); setRun(await api.run(run.run_id)); await refresh();
  });
  const execute = () => act("execute", async () => {
    if (!run) return;
    const d = run.decisions.find((x) => x.status === "active");
    if (!d) return;
    setRun(await api.execute(run.run_id, d.plan_id, d.approval_id)); setPlanSel(d.plan_id); await refresh();
  });
  const resetEnv = () => act("reset", async () => { if (uc?.fields.adapter_id) { await api.reset(uc.fields.adapter_id); await refresh(); } });
  const askType = (type: string, objectId?: string) => act("llm", async () => {
    try {
      const out = objectId && uc?.fields.adapter_id ? await api.askLLM(uc.fields.adapter_id, objectId) : await api.explainType(type);
      setLlmTypes((m) => ({ ...m, [type]: out }));
    } catch (e) { setLlmTypes((m) => ({ ...m, [type]: (e as Error).message })); }
  });

  if (err && !uc) return <ErrorBox error={err} />;
  if (!uc || !sum || !profile) return <Loading what="simulation" />;

  const connected = sum.environment.status === "simulated";
  const env = envs.find((e) => e.environment_id === uc.fields.adapter_id);
  const view = connected ? views[uc.fields.adapter_id] : undefined;
  const names: Record<string, string> = Object.fromEntries((view?.objects ?? []).map((o) => [o.id, o.name]));
  const loop = profile.profile.core_loop;
  const note = (i: number) => (uc.step_notes[i] ?? "").replace("{goal}", uc.fields.goal_outcome || "(not set yet)");
  const stale = !!run && run.goal.text !== [uc.fields.goal_outcome.trim(), uc.fields.constraints.trim()].filter(Boolean).join(" ");
  const f = uc.fields;
  const dirty = draft.role !== f.role || draft.purpose !== f.purpose || draft.goal_outcome !== f.goal_outcome || draft.constraints !== f.constraints
    || draft.desired_input !== (f.desired_input ?? "") || draft.desired_output !== (f.desired_output ?? "") || draft.success_criteria !== (f.success_criteria ?? "")
    || draft.rules !== uc.extra_rules.map((r) => r.text).join("\n");
  const sel = run?.assessments.find((a) => a.plan.plan_id === planSel);
  const active = run?.decisions.find((d) => d.status === "active");
  const used = run?.decisions.find((d) => d.status === "used");
  const decided = run?.decisions.find((d) => d.plan_id === planSel && d.status !== "active");
  const types = Array.from(new Map((view?.objects ?? []).filter((o) => o.evidence !== "unknown").map((o) => [o.type, o.id])).entries());
  const ti = uc.template_info;
  const planned = !!run && !stale && run.goal.supported;
  const remaining = planned ? run!.assessments.filter((a) => !a.rejected_before_prediction) : [];
  const targetObj = view?.objects.find((o) => f.target_name && (o.name.toLowerCase() === f.target_name.toLowerCase() || o.name.toLowerCase().includes(f.target_name.toLowerCase()) || f.target_name.toLowerCase().includes(o.name.toLowerCase())));
  const needsInfo = !!run && !stale && !run.goal.supported && (run.goal.missing_information.length > 0 || !!run.goal.clarification_needed);
  const winMap: Record<string, StepStatus> = { WIN: "completed", "NOT A WIN": "failed", "NOT VERIFIED": "not_verified" };

  // ---- statuses (a future step is never shown as completed)
  const s: Record<number, StepStatus> = {
    1: !f.goal_outcome.trim() ? "waiting_info" : !run || stale ? (connected ? "ready" : "unsupported") : run.goal.supported ? "completed" : needsInfo ? "waiting_info" : "failed",
    2: sum.conflicts.length ? "waiting_info" : "completed",
    3: connected ? "completed" : "unsupported",
    4: !connected ? "unsupported" : needsInfo || !f.target_name.trim() ? "waiting_info" : "completed",
    5: connected ? "completed" : "unsupported",
    6: connected ? "completed" : "unsupported",
    7: connected ? "completed" : "unsupported",
    8: !connected ? "unsupported" : planned ? (run!.assessments.length ? "completed" : "failed") : run && !stale ? "failed" : "not_started",
    9: !connected ? "unsupported" : planned && run!.assessments.length ? "completed" : "not_started",
    10: !connected ? "unsupported" : planned ? (remaining.length ? "completed" : "failed") : "not_started",
    11: !connected ? "unsupported" : planned ? (run!.recommendation?.plan_id ? "completed" : "failed") : "not_started",
    12: !connected ? "unsupported" : !planned ? "not_started" : run!.status === "stale" ? "failed" : run!.executed_plan_id || active ? "approved" : run!.status === "rejected" ? "rejected" : run!.recommendation?.plan_id ? "waiting_review" : "not_started",
    13: !connected || !env?.capabilities.execute ? "unsupported" : run?.execution_status === "executed" ? "completed" : run?.execution_status === "failed" ? "failed" : run?.execution_status === "rejected" ? "rejected" : active ? "ready" : "not_started",
    14: !connected ? "unsupported" : run?.observation ? "completed" : "not_started",
    15: !connected ? "unsupported" : run?.observation ? "completed" : "not_started",
    16: run?.win ? winMap[run.win.overall] : !connected ? "unsupported" : run?.execution_status === "rejected" ? "rejected" : run?.execution_status === "failed" ? "failed" : "not_started",
  };
  const phase: StagePhase = !connected ? "unsupported" : !planned ? "idle" : run!.executed_plan_id ? "executed" : active ? "approved" : "predicted";
  const stagePlan = run?.executed_plan_id ? run.assessments.find((a) => a.plan.plan_id === run.executed_plan_id) ?? null : sel?.rejected_before_prediction ? null : sel ?? null;
  const planChips = remaining.map((a) => (
    <button key={a.plan.plan_id} className="chip" style={{ cursor: "pointer", ...(a.plan.plan_id === planSel ? { borderColor: "var(--accent)", color: "var(--accent)" } : {}) }} aria-pressed={a.plan.plan_id === planSel} onClick={() => setPlanSel(a.plan.plan_id)}>{a.plan.plan_id}{run!.recommendation?.plan_id === a.plan.plan_id ? " ★" : ""}</button>
  ));
  const allRules = [...profile.conduct.rules, ...(env?.rules ?? [])];

  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head">
        <div>
          <p className="hud-label accent">Simulation · 16 steps · How AFM thinks before acting</p>
          <h1 className="mt-s">{ti.title || uc.title}</h1>
          <p className="lede">{ti.purpose}</p>
        </div>
        <div className="stack" style={{ alignItems: "flex-end" }}>
          <ConnectionBadge status={sum.environment.status} />
          <span className="faint tiny mono">{uc.rules_version}{run?.policy_version ? ` · ${run.policy_version}` : ""} · {uc.usecase_id}</span>
        </div>
      </div>
      {ti.source_note && <div className="warn small"><strong>Illustrative scenario.</strong> {ti.source_note}</div>}
      {err && <ErrorBox error={err} />}

      <section className="glass panel row between" aria-label="Run controls">
        <span className="small">{connected ? (run ? (stale ? "Task goal changed since the last run. Re-run to update steps 8–16." : `Last run ${run.run_id}: ${run.status.replace(/_/g, " ")} · execution ${run.execution_status.replace(/_/g, " ")}${run.win ? ` · AFM result ${run.win.overall}` : ""}.`) : "Steps 1–7 are prefilled. Run the simulation to compute steps 8–11, then review.") : "No adapter is connected: AFM can only describe what is missing and general knowledge."}{dirty && " You have unsaved input edits."}</span>
        <span className="row">
          {dirty && <button className="btn" onClick={() => act("save", saveInputs)} disabled={!!busy}>Save inputs</button>}
          <button className="btn-primary btn-lg" onClick={runSim} disabled={!!busy}><Icon name="play" size={15} /> {busy === "run" ? "Running…" : run ? "Re-run simulation" : "Run simulation"}</button>
        </span>
      </section>

      <div className="split">
        <ol className="timeline" aria-label="The 16 steps">
          <Step n={1} title={loop[0]} status={s[1]} evidence={["human"]} note={note(0)} onNote={saveNote(0)} open>
            <label className="lbl" htmlFor="s-goal">Task goal</label>
            <textarea id="s-goal" className="field" rows={2} value={draft.goal_outcome} onChange={(e) => setDraft({ ...draft, goal_outcome: e.target.value })} />
            <div className="grid g2 mt">
              <div><label className="lbl" htmlFor="s-in">Desired input (what goes in / starting state)</label><input id="s-in" className="field" value={draft.desired_input} onChange={(e) => setDraft({ ...draft, desired_input: e.target.value })} placeholder="e.g. app on port 8000, users connected" /></div>
              <div><label className="lbl" htmlFor="s-out">Desired output (observable result)</label><input id="s-out" className="field" value={draft.desired_output} onChange={(e) => setDraft({ ...draft, desired_output: e.target.value })} placeholder="e.g. app answers on 9000 through the web server" /></div>
            </div>
            <label className="lbl mt" htmlFor="s-crit">Your success criteria (observable, one per line)</label>
            <textarea id="s-crit" className="field" rows={2} value={draft.success_criteria} onChange={(e) => setDraft({ ...draft, success_criteria: e.target.value })} placeholder="e.g. A test request through the web server succeeds" />
            <label className="lbl mt" htmlFor="s-cons">Constraints</label>
            <input id="s-cons" className="field" value={draft.constraints} onChange={(e) => setDraft({ ...draft, constraints: e.target.value })} />
            <p className="faint tiny mt-s">Target: {f.target_name || "—"} · environment: {sum.environment.name} · proposed action: {f.proposed_action || "—"}</p>
            {planned ? (
              <div className="grid g2 mt">
                <div><p className="hud-label">Success criteria for this run</p><ul className="list mt-s">{run!.goal.success_criteria.map((c) => (
                  <li key={c.id} className="small" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}><span className={`ev ${c.source === "human" ? "ev-configured" : "ev-inferred"}`}>{c.source === "human" ? "human" : "proposed by adapter"}</span><span>{c.description}{c.kind === "manual" ? " (verified by a human after execution)" : ""}</span></li>
                ))}</ul><p className="faint tiny mt-s">Proposed criteria are not human-approved until you agree to them at review (step 12).</p></div>
                <div><p className="hud-label">Pre-check (R30)</p><ul className="bullets tiny">{run!.goal.intended_benefits.map((x) => <li key={x}>Benefit: {x}</li>)}{run!.goal.potential_negative_effects.map((x) => <li key={x}>Possible harm: {x}</li>)}</ul></div>
              </div>
            ) : run && !stale ? <div className="warn small mt"><strong>Not understood in this environment:</strong> {run.goal.explanation} {run.goal.clarification_needed}</div> : null}
            <p className="faint tiny mt-s">Change these here or ask the chat (it can propose criteria, input and output). Then re-run.</p>
          </Step>

          <Step n={2} title={loop[1]} status={s[2]} evidence={["configured", "human"]} note={note(1)} onNote={saveNote(1)}>
            <p className="small"><strong>{profile.profile.name}</strong>: {profile.profile.purpose}</p>
            <div className="grid g2 mt">
              <div><label className="lbl" htmlFor="s-role">Task role (context only)</label><input id="s-role" className="field" value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value })} /></div>
              <div><label className="lbl" htmlFor="s-purpose">Agent purpose</label><input id="s-purpose" className="field" value={draft.purpose} onChange={(e) => setDraft({ ...draft, purpose: e.target.value })} /></div>
            </div>
            <p className="small mt">{profile.conduct.rules.length} permanent rules of conduct (<span className="mono">{uc.rules_version}</span>) <a href="#/identity">view</a>{env ? `, plus ${env.rules.length} ${env.name} rules:` : "."}</p>
            {env && <ul className="list mt-s">{env.rules.map((r) => <li key={r.id} className="small" style={{ flexWrap: "nowrap" }}><span className="mono accent">{r.id}</span><span style={{ flex: 1 }}>{r.text}</span><EnforcementBadge e={r.enforcement} /></li>)}</ul>}
            <label className="lbl mt" htmlFor="s-rules">Use-case rules (narrow only, one per line)</label>
            <textarea id="s-rules" className="field" rows={2} value={draft.rules} onChange={(e) => setDraft({ ...draft, rules: e.target.value })} placeholder="Do not change the health monitor" />
            {uc.extra_rules.map((r) => <p key={r.text} className="tiny mt-s"><span className={`badge ${r.status === "enforced" ? "st-pass" : r.status === "conflict" ? "st-fail" : "st-unknown"}`}>{r.status}</span> {r.text}: <span className="faint">{r.explanation}</span></p>)}
            {env && <p className="faint tiny mt-s">Prohibited: {env.tools.filter((t) => t.permission === "prohibited").map((t) => t.name).join(", ") || "none"} · needs approval: {env.tools.filter((t) => t.permission === "requires_approval").map((t) => t.name).join(", ") || "none"}. Standing context: enforced from discovery to reporting; a goal or approval never overrides a prohibition.</p>}
          </Step>

          <Step n={3} title={loop[2]} status={s[3]} evidence={connected ? ["simulated"] : ["unknown"]} note={note(2)} onNote={saveNote(2)}>
            <p className="small"><strong>{sum.environment.name}</strong> · {sum.environment.label}{sum.environment.adapter ? ` · ${sum.environment.adapter}` : ""}</p>
            <div className="mt-s"><Capabilities c={sum.environment.capabilities} /></div>
            {env && <ul className="bullets tiny mt-s">{env.limitations.map((l) => <li key={l}>{l}</li>)}</ul>}
            {sum.environment.note && <p className="faint tiny mt-s">{sum.environment.note}</p>}
            {connected && <button className="btn mt" onClick={resetEnv} disabled={!!busy}><Icon name="reset" size={14} /> Reset this playground</button>}
          </Step>

          <Step n={4} title={loop[3]} status={s[4]} evidence={connected ? ["observed", "human"] : ["illustrative"]} note={note(3)} onNote={saveNote(3)}>
            <dl className="kv">
              <dt>target</dt><dd className="small">{f.target_name || "—"} {targetObj ? <EvidenceBadge e={targetObj.evidence} /> : connected && f.target_name ? <span className="ev ev-unknown">not found in the catalog</span> : null}</dd>
              <dt>identifier</dt><dd className="small mono">{f.target_identifier || targetObj?.id || "—"}</dd>
              <dt>requested change</dt><dd className="small">{f.proposed_action || "—"}</dd>
            </dl>
            <p className="hud-label mt">Missing information</p>
            <ul className="bullets mt-s">{[...sum.missing, ...(run && !stale ? run.goal.missing_information : [])].map((m) => <li key={m}>{m}</li>)}{!sum.missing.length && !(run && !stale && run.goal.missing_information.length) && <li className="faint">Nothing blocking is known.</li>}</ul>
            {needsInfo && <div className="warn small mt"><strong>Waiting for information:</strong> {run!.goal.clarification_needed}</div>}
          </Step>

          <Step n={5} title={loop[4]} status={s[5]} evidence={connected ? ["simulated", "unknown"] : ["illustrative"]} note={note(4)} onNote={saveNote(4)}>
            {view ? <RelationshipGraph objects={view.objects} relationships={view.relationships} layout={view.layout} />
              : <><p className="small">No adapter, so AFM discovered nothing. Notes provided (unverified):</p><pre className="mini mt-s" style={{ whiteSpace: "pre-wrap" }}>{f.evidence || "—"}</pre></>}
          </Step>

          <Step n={6} title={loop[5]} status={s[6]} evidence={connected ? ["observed", "llm"] : ["illustrative", "llm"]} note={note(5)} onNote={saveNote(5)}>
            {view ? (
              <ul className="list">{view.objects.filter((o) => o.evidence !== "unknown").map((o) => (
                <li key={o.id} className="small" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}><EvidenceBadge e={o.evidence} /><span><strong>{o.name}</strong> <span className="mono faint">{Object.entries(o.state).filter(([, v]) => typeof v !== "object").map(([k, v]) => `${k}=${fmtVal(v)}`).join(" · ")}</span></span></li>
              ))}</ul>
            ) : <p className="small">Unsupported: AFM has no authorized tool to inspect this environment.</p>}
            <div className="row mt">{(connected ? types : [[f.target_type || "unknown", ""] as [string, string]]).map(([t, oid]) => (
              <button key={t} className="btn" onClick={() => askType(t, oid || undefined)} disabled={!!busy}><Icon name="brain" size={14} /> Ask LLM: {t.replace(/_/g, " ")}</button>
            ))}</div>
            {Object.entries(llmTypes).map(([t, out]) => (
              <div key={t} className="glass-flat mt-s" style={{ padding: 10 }}>
                <span className="ev ev-inferred">LLM-generated · {t.replace(/_/g, " ")}</span>
                <p className="small mt-s">{typeof out === "string" ? out : out.explanation}</p>
                {typeof out !== "string" && <p className="faint tiny mt-s">Inspect to verify: {out.suggested_read_only_inspections.join("; ")}</p>}
              </div>
            ))}
            <p className="faint tiny mt-s">Observed states decide; LLM knowledge is general and unverified.</p>
          </Step>

          <Step n={7} title={loop[6]} status={s[7]} evidence={connected ? ["configured"] : ["unknown"]} note={note(6)} onNote={saveNote(6)}>
            {connected ? <ul className="list">{sum.tools.filter((t) => t.scope === "environment").map((t) => <li key={t.name} className="between small"><span><span className="mono">{t.name}</span> <span className="faint">· {t.description}</span></span><PermissionBadge p={t.permission} /></li>)}</ul>
              : <p className="small">Unsupported: no registered tools exist for this environment.</p>}
            {env && <p className="faint tiny mt-s">Safe simulation available: {env.capabilities.simulate ? "yes (isolated copy)" : "no"}.</p>}
          </Step>

          <Step n={8} title={loop[7]} status={s[8]} evidence={planned ? ["predicted"] : []} note={note(7)} onNote={saveNote(7)}>
            {planned ? <ul className="list">{run!.assessments.map((a) => (
              <li key={a.plan.plan_id} className="small" style={{ flexDirection: "column", alignItems: "stretch" }}>
                <span><strong>{a.plan.plan_id}</strong> {a.plan.title} {run!.recommendation?.plan_id === a.plan.plan_id && <span className="ribbon">Recommended</span>}</span>
                <span className="faint tiny mono">{a.plan.actions.map((x, i) => `${i + 1}. ${x.tool}(${Object.entries(x.parameters).map(([k, v]) => `${k}=${v}`).join(", ")}) → ${nameOf(names, x.target_object_id)}`).join("  ")}</span>
                <span className="faint tiny">Assumptions: {a.plan.assumptions.join(" ")}</span>
              </li>))}</ul> : <p className="faint small">{connected ? "Not started: run the simulation." : "Unsupported without an adapter."}</p>}
          </Step>

          <Step n={9} title={loop[8]} status={s[9]} evidence={planned ? ["configured"] : []} note={note(8)} onNote={saveNote(8)}>
            {planned ? <ul className="list">{run!.assessments.map((a) => {
              const cap = a.checks.find((c) => c.check === "capability")!, perm = a.checks.find((c) => c.check === "permission")!, rev = a.checks.find((c) => c.check === "human_review")!;
              return (
                <li key={a.plan.plan_id} className="small" style={{ flexDirection: "column", alignItems: "stretch" }}>
                  <span className="row between"><strong>{a.plan.plan_id}</strong><span className="row" style={{ gap: 6 }}><StatusBadge s={cap.status} /><StatusBadge s={perm.status} /><StatusBadge s={rev.status} /></span></span>
                  <span className="faint tiny">{a.rejected_before_prediction ? `Rejected before prediction: ${a.summary.replace("Rejected before prediction: ", "")}` : "Passed the pre-check: supported, registered and permitted; review needed for state changes. It may be simulated."}</span>
                </li>);
            })}</ul> : <p className="faint small">{connected ? "Not started." : "Unsupported."}</p>}
          </Step>

          <Step n={10} title={loop[9]} status={s[10]} evidence={planned ? ["predicted", "conditional", "unknown"] : ["illustrative"]} note={note(9)} onNote={saveNote(9)} open={s[10] === "completed" && s[12] === "waiting_review"}>
            <ul className="bullets small"><li>Benefit: {ti.benefit}</li><li>Possible negative effect: {ti.negative}</li><li>Unknown: {ti.unknown}</li></ul>
            {planned && view && (sel && !sel.rejected_before_prediction ? (<>
              <div className="row mt" role="group" aria-label="Plan">{planChips}</div>
              <div className="mt-s"><EnvImpact a={sel} view={view} names={names} /></div>
            </>) : <div className="row mt">{planChips}</div>)}
          </Step>

          <Step n={11} title={loop[10]} status={s[11]} evidence={planned ? ["predicted"] : []} note={note(10)} onNote={saveNote(10)}>
            {planned ? (<>
              <div className="table-wrap"><table className="tbl">
                <thead><tr><th scope="col">Plan</th><th scope="col">Rules (outcome)</th><th scope="col">Goal</th><th scope="col">Benefits / warnings</th><th scope="col">Objects changed · reversible</th></tr></thead>
                <tbody>{run!.assessments.map((a) => (
                  <tr key={a.plan.plan_id}><td className="strong">{a.plan.plan_id}{run!.recommendation?.plan_id === a.plan.plan_id ? " ★" : ""}</td>
                    <td><StatusBadge s={a.checks.find((c) => c.check === "rules")!.status} /></td><td><StatusBadge s={a.checks.find((c) => c.check === "goal")!.status} /></td>
                    <td className="small">{a.rejected_before_prediction ? "not predicted" : `+${a.benefits} / ⚠${a.warnings}`}</td><td className="small">{a.changed_objects} · {a.reversible == null ? "unknown" : a.reversible ? "yes" : "no"}</td></tr>
                ))}</tbody>
              </table></div>
              <p className="small mt"><strong>{run!.recommendation?.plan_id ? `Recommend ${run!.recommendation.plan_id}. ` : "No plan recommended. "}</strong>{run!.recommendation?.reason}</p>
              {sel && <details className="mt-s"><summary className="small dim" style={{ cursor: "pointer" }}>Checks for {sel.plan.plan_id}</summary><div className="mt-s"><ChecksList checks={sel.checks} /></div></details>}
            </>) : prep && !prep.run ? (<div className="warn small"><p>{prep.message}</p>{prep.missing.length > 0 && <ul className="bullets mt-s">{prep.missing.map((m) => <li key={m}>{m}</li>)}</ul>}
              {prep.llm_explanation && <p className="mt-s"><span className="ev ev-inferred">LLM-generated</span> {prep.llm_explanation.explanation}</p>}</div>)
              : <p className="faint small">{connected ? "Not started." : "Run the simulation to see what AFM can and cannot say without an adapter."}</p>}
          </Step>

          <Step n={12} title={loop[11]} status={s[12]} evidence={["human"]} note={note(11)} onNote={saveNote(11)} open={s[12] === "waiting_review"}>
            {s[12] === "waiting_review" && run ? (
              <div className="stack">
                <p className="small">Task goal: “{run.goal.text}” · environment {run.environment_name} (simulated) · simulation {env?.capabilities.simulate ? "supported" : "unsupported"} · execution {env?.capabilities.execute ? "supported (simulation only)" : "unsupported"}.</p>
                <div className="row" role="radiogroup" aria-label="Plan to review">{run.assessments.filter((a) => a.approvable).map((a) => (
                  <label key={a.plan.plan_id} className="row small" style={{ gap: 6 }}><input type="radio" name="plan" checked={planSel === a.plan.plan_id} onChange={() => setPlanSel(a.plan.plan_id)} />{a.plan.plan_id}{run.recommendation?.plan_id === a.plan.plan_id ? " (recommended)" : ""}</label>
                ))}</div>
                {sel && !sel.meets_goal_and_rules && sel.approvable && <div className="warn small">This plan is not predicted to meet the task goal.</div>}
                {decided ? <p className="small">{planSel} was {decided.decision === "approve" ? "approved" : "rejected"}.</p> : (
                  <div className="row">
                    <button className="btn-primary" disabled={!!busy || !sel?.approvable} onClick={() => { setAck(false); setAgree(false); dlg.current?.showModal(); }}><Icon name="check" size={14} /> Approve simulated execution</button>
                    <button className="btn-danger" disabled={!!busy || !sel} onClick={() => decide("reject")}><Icon name="x" size={14} /> Reject plan</button>
                    <a className="btn-ghost" href={`#/review/${run.run_id}/${planSel}`}>Detailed review page</a>
                  </div>
                )}
                <p className="faint tiny">To request revisions or ask questions, use the chat; a revised plan needs a new run and a new review.</p>
              </div>
            ) : <p className="small">{{ approved: `Approved: ${active?.plan_id ?? run?.executed_plan_id}; success criteria ${(active ?? used)?.criteria_agreed ? "agreed" : "NOT agreed"} by you.`, rejected: "Rejected: nothing will be executed (R28).", failed: "The environment changed since the prediction (R13). Re-run.", unsupported: "Unsupported: nothing can be reviewed for execution without an adapter.", not_started: "Not started: run the simulation first." }[s[12] as string] ?? ""}</p>}
          </Step>

          <Step n={13} title={loop[12]} status={s[13]} evidence={run?.executed_plan_id ? ["simulated"] : []} note={note(12)} onNote={saveNote(12)} open={!!active && s[13] === "ready"}>
            {run?.execution_status === "executed" ? <p className="small">Recheck passed (approval, plan hash, policy {run.policy_version}, environment v{run.environment_version}, preconditions). Executed {run.executed_plan_id} once in the simulation (v{run.environment_version} → v{run.observation?.environment_version_after}).</p>
              : active && s[13] === "ready" ? <button className="btn-primary" onClick={execute} disabled={!!busy}><Icon name="play" size={14} /> {busy === "execute" ? "Rechecking & executing…" : "Recheck and execute approved plan (simulation)"}</button>
              : <p className="small">Execution status: <strong>{run?.execution_status.replace(/_/g, " ") ?? "not attempted"}</strong>. {s[13] === "unsupported" ? "No authorized, supported execution path exists." : s[13] === "failed" ? "The approval was invalidated (plan, policy or environment changed). Re-run." : s[13] === "rejected" ? "Nothing was executed." : "Waiting for an approved plan."}</p>}
          </Step>

          <Step n={14} title={loop[13]} status={s[14]} evidence={run?.observation ? ["observed", "simulated"] : []} note={note(13)} onNote={saveNote(13)} open={s[14] === "completed" && !run?.win}>
            {run?.observation ? (
              <dl className="kv">
                <dt>method</dt><dd className="small">{run.observation.method}</dd>
                <dt>time</dt><dd className="small">{fmtTime(run.observation.observed_at)}</dd>
                <dt>snapshot</dt><dd className="small">environment v{run.observation.environment_version_after}</dd>
                <dt>source</dt><dd className="small">{run.observation.simulated ? <span className="ev ev-configured">simulated</span> : "connected system"}</dd>
                <dt>unchanged</dt><dd className="small">{run.observation.unchanged_objects.map((id) => nameOf(names, id)).join(", ") || "none"}</dd>
              </dl>
            ) : <p className="small">{s[14] === "unsupported" ? "Unsupported: nothing can be observed without an adapter." : "Not started: nothing executed, so nothing is observed (no invented results)."}</p>}
          </Step>

          <Step n={15} title={loop[14]} status={s[15]} evidence={run?.observation ? ["observed", "predicted"] : []} note={note(14)} onNote={saveNote(14)}>
            {run?.observation ? (<>
              <div className="row">{(["MATCH", "MISMATCH", "NOT VERIFIED"] as const).map((r) => <span key={r} className="row small" style={{ gap: 6 }}><ResultBadge r={r} /> {run.observation!.items.filter((i) => i.result === r).length}</span>)}</div>
              <div className="table-wrap mt-s"><table className="tbl">
                <thead><tr><th scope="col">Object · field</th><th scope="col">Predicted</th><th scope="col">Observed (test)</th><th scope="col">Result</th></tr></thead>
                <tbody>{run.observation.items.map((i, k) => (
                  <tr key={k}><td className="small"><strong>{nameOf(names, i.object_id)}</strong> · <span className="mono">{i.field}</span>{!i.required && <div className="faint tiny">informational</div>}</td>
                    <td className="mono tiny">{typeof i.predicted === "string" && i.predicted.length > 50 ? i.predicted.slice(0, 50) + "…" : fmtVal(i.predicted)}</td><td className="mono tiny">{i.observed === null ? "—" : fmtVal(i.observed)}</td>
                    <td><ResultBadge r={i.result} /></td></tr>
                ))}</tbody>
              </table></div>
              <p className="faint tiny mt-s">A correct prediction of an undesirable result is still a MATCH; whether the task goal was achieved is judged separately in step 16.</p>
            </>) : <p className="small">{s[15] === "unsupported" ? "Unverified: no test or simulation ran." : "Not started."}</p>}
          </Step>

          <Step n={16} title={loop[15]} status={s[16]} evidence={run?.win ? ["observed", "simulated"] : []} note={note(15)} onNote={saveNote(15)} open={!!run?.win}>
            {run ? <WinPanel run={run} rules={allRules} onChange={setRun} /> : <p className="small">Not started.</p>}
          </Step>
        </ol>

        <div className="side-col">
          <EnvStage view={view} assessment={stagePlan} phase={phase} observation={run?.observation} envName={sum.environment.name}
            plans={remaining.map((a) => ({ id: a.plan.plan_id, title: a.plan.title }))} selected={planSel} onSelect={setPlanSel} />
          <ChatPanel uc={uc} busy={busy === "chat"} onSend={send} onResolve={resolve} compact
            placeholder="Override any step: “step 9: …”, refine the task goal (“success criteria: a test request succeeds”), “use port 9500 instead”, “add rule: Do not change the health monitor”. Proposals wait for your acceptance; computed results come only from AFM's engine." />
        </div>
      </div>

      <dialog ref={dlg} className="modal" aria-labelledby="sim-confirm">
        <h2 id="sim-confirm">Approve {planSel}?</h2>
        <p className="mt small dim">You approve exactly this plan in the <strong>simulated</strong> {sum.environment.name}:</p>
        <ul className="bullets mt-s">{sel?.simulation.consequences.filter((c) => c.type === "direct" && c.relationship_to_target === "target").map((c, i) => <li key={i}>{c.description}</li>)}</ul>
        <label className="row mt small" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} style={{ marginTop: 3 }} />I reviewed the consequences, checks and unknowns. My approval applies only to this plan, its parameters, environment v{run?.environment_version} and the current policy.</label>
        <div className="glass-flat mt" style={{ padding: 10 }}>
          <p className="hud-label">Success criteria (used for the Win)</p>
          <ul className="bullets tiny mt-s">{run?.goal.success_criteria.map((c) => <li key={c.id}>{c.description} <span className="faint">({c.source === "human" ? "yours" : "proposed by adapter"})</span></li>)}</ul>
          <label className="row small mt-s" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} style={{ marginTop: 3 }} />I agree these success criteria define success for this task. (Optional: without agreement, task goal achievement stays NOT VERIFIED.)</label>
        </div>
        <div className="row mt-l" style={{ justifyContent: "flex-end" }}><button className="btn" onClick={() => dlg.current?.close()}>Cancel</button><button className="btn-primary" disabled={!ack || !!busy} onClick={() => decide("approve")}>Approve</button></div>
      </dialog>
      <Plain>Steps 1–7 frame the task with AFM's standing rules active from the start; 8–11 predict and compare plans on a copy; 12 asks you; 13 rechecks and executes once; 14–15 observe and compare; 16 decides WIN only if predictions matched, the agreed goal was observed, and rules were respected. Open <a href="#/builder">Create a use case</a> or <button className="btn-ghost tiny" onClick={() => go("overview")}>pick another simulation</button>.</Plain>
    </div>
  );
}
