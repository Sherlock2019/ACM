import { useEffect, useState } from "react";
import { RequireEnv } from "../components/EnvPicker";
import { Icon } from "../components/icons";
import { ActionCard } from "../components/PlanParts";
import { Definitions, ErrorBox, Loading, Panel, PermissionBadge, Plain, RunStatusBadge } from "../components/ui";
import { api } from "../services/api";
import { go, useAFM } from "../state";
import type { EnvironmentDescription, Run } from "../types/afm";

function GoalForm({ env, onRun, busy }: { env: EnvironmentDescription; onRun: (t: string) => void; busy: boolean }) {
  const [text, setText] = useState(env.demo_goals[0] ?? "");
  useEffect(() => { setText(env.demo_goals[0] ?? ""); }, [env.environment_id, env.demo_goals]);
  return (
    <Panel title={`Task goal · ${env.name}`}>
      <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) onRun(text.trim()); }}>
        <label htmlFor="goal" className="lbl">What do you want AFM to achieve in this environment?</label>
        <textarea id="goal" className="field" rows={2} value={text} onChange={(e) => setText(e.target.value)} maxLength={500} aria-describedby="goal-help" />
        <p id="goal-help" className="faint tiny mt-s">Goals this playground understands are listed below. Anything else is reported as unsupported, never guessed or swapped for another environment's goal.</p>
        <div className="row mt">
          <button type="submit" className="btn-primary" disabled={busy || !text.trim()}><Icon name="spark" size={15} /> {busy ? "Thinking before acting…" : "Assess goal & predict plans"}</button>
        </div>
        <div className="row mt" aria-label="Example goals">
          <span className="faint tiny">Examples:</span>
          {env.demo_goals.map((g) => <button type="button" key={g} className="chip" style={{ cursor: "pointer" }} onClick={() => setText(g)}>{g}</button>)}
        </div>
      </form>
    </Panel>
  );
}

export function GoalSummary({ run }: { run: Run }) {
  const g = run.goal;
  return (
    <Panel title="Task goal interpretation & pre-check (R30)" right={<span className="faint tiny mono">{run.run_id} · {run.environment_name} v{run.environment_version}</span>}>
      <p className="small">“{g.text}”</p>
      {run.task_role && <p className="faint tiny mt-s">Task role: {run.task_role} (task context only; identity, rules and approval unchanged)</p>}
      {g.supported ? (
        <>
          <p className="small dim mt-s">{g.explanation}</p>
          <div className="grid g2 mt">
            <div><p className="hud-label">Success criteria (fixed now, R26)</p><ul className="bullets mt-s">{g.success_criteria.map((c) => <li key={c.id}>{c.description} <span className="faint tiny">({c.source === "human" ? "yours" : "proposed by adapter, not yet agreed"})</span></li>)}</ul></div>
            <div><p className="hud-label">Intended benefits</p><ul className="bullets mt-s">{g.intended_benefits.map((x) => <li key={x}>{x}</li>)}</ul></div>
            <div><p className="hud-label">Possible negative effects</p><ul className="bullets mt-s">{g.potential_negative_effects.map((x) => <li key={x}>{x}</li>)}</ul></div>
            <div><p className="hud-label">Missing information (R17)</p><ul className="bullets mt-s">{g.missing_information.map((x) => <li key={x}>{x}</li>)}</ul></div>
          </div>
        </>
      ) : (
        <div className="warn mt">
          <strong>AFM cannot act on this goal in {run.environment_name}.</strong>
          <p className="mt-s">{g.explanation}</p>
          {g.missing_information.length > 0 && <ul className="bullets mt-s">{g.missing_information.map((x) => <li key={x}>Missing: {x}</li>)}</ul>}
          {g.clarification_needed && <p className="mt-s small dim">Please clarify. {g.clarification_needed}</p>}
        </div>
      )}
    </Panel>
  );
}

export function Goals({ runId }: { runId?: string }) {
  const { refresh, views, select } = useAFM();
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!runId) { setRun(null); return; }
    api.run(runId).then((r) => { setRun(r); select(r.environment_id); }).catch((e) => setErr(e.message));
  }, [runId, select]);
  return (
    <RequireEnv title="Step 5 · What is the goal?">
      {(env) => {
        const assess = async (text: string) => {
          setBusy(true); setErr(null);
          try { const r = await api.assess(env.environment_id, text); setRun(r); go(`goals/${r.run_id}`); await refresh(); }
          catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
        };
        const names = Object.fromEntries((views[env.environment_id]?.objects ?? []).map((o) => [o.id, o.name]));
        const current = run && run.environment_id === env.environment_id ? run : null;
        return (
          <div className="stack rise" style={{ gap: 18 }}>
            <div className="page-head">
              <div>
                <p className="hud-label accent">Steps 1 & 8 · What is the task goal, and which plans could help? · {env.name}</p>
                <h1 className="mt-s">Goals & Plans</h1>
                <p className="lede">AFM interprets the goal with this environment's adapter, checks it before planning (R30), and proposes candidate plans using only registered tools.</p>
              </div>
              {current && <RunStatusBadge s={current.status} />}
            </div>
            <GoalForm env={env} onRun={assess} busy={busy} />
            <Definitions items={env.definitions} />
            {err && <ErrorBox error={err} />}
            {busy && <Loading what="predictions" />}
            {current && (
              <>
                <GoalSummary run={current} />
                {current.assessments.length > 0 && (
                  <Panel title="Candidate plans" right={<a className="btn-primary" href={`#/assessment/${current.run_id}`}><Icon name="spark" size={15} /> See consequence assessment</a>}>
                    <div className="grid g2">
                      {current.assessments.map((a) => (
                        <article key={a.plan.plan_id} className="glass-flat stack" style={{ padding: 14 }}>
                          <div className="row between">
                            <strong>{a.plan.plan_id} · {a.plan.title}</strong>
                            {current.recommendation?.plan_id === a.plan.plan_id && <span className="ribbon">Recommended</span>}
                          </div>
                          <p className="faint tiny">Proposed by {a.plan.proposed_by === "llm" ? "LLM (inferred, validated)" : a.plan.proposed_by.replace("_", " ")} · {a.plan.actions.length} action(s)</p>
                          {a.plan.actions.map((x, i) => <ActionCard key={x.action_id} a={x} names={names} step={i + 1} />)}
                        </article>
                      ))}
                    </div>
                  </Panel>
                )}
                <Panel title="Tools available in this environment">
                  <ul className="list">{env.tools.map((t) => (
                    <li key={t.name} className="between small"><span><span className="mono">{t.name}</span> <span className="faint">· {t.description}</span></span><PermissionBadge p={t.permission} /></li>
                  ))}</ul>
                </Panel>
              </>
            )}
            <Plain>A plan is a list of actions with exact parameters. AFM has already played every plan out on a copy of the environment; the next page shows what it predicts will change. Nothing real has changed.</Plain>
          </div>
        );
      }}
    </RequireEnv>
  );
}
