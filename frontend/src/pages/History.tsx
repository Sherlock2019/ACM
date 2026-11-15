import { useEffect, useState } from "react";
import { nameOf } from "../components/PlanParts";
import { Empty, ErrorBox, Loading, Panel, Plain, ResultBadge, RunStatusBadge, Stat, fmtTime, fmtVal } from "../components/ui";
import { WinPanel } from "../components/WinPanel";
import { api } from "../services/api";
import { useAFM } from "../state";
import type { Run } from "../types/afm";

function RunDetail({ runId }: { runId: string }) {
  const { views, profile, envs } = useAFM();
  const [run, setRun] = useState<Run | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setRun(null); api.run(runId).then(setRun).catch((e) => setErr(e.message)); }, [runId]);
  if (err) return <ErrorBox error={err} />;
  if (!run) return <Loading what="run" />;
  const names: Record<string, string> = Object.fromEntries((views[run.environment_id]?.objects ?? []).map((o) => [o.id, o.name]));
  const obs = run.observation;
  const n = (r: string) => obs?.items.filter((i) => i.result === r).length ?? 0;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <Panel title={`Run ${run.run_id}`} right={<RunStatusBadge s={run.status} />}>
        <dl className="kv">
          <dt>environment</dt><dd>{run.environment_name} <span className="chip">simulated</span></dd>
          <dt>goal</dt><dd>“{run.goal.text}”</dd>
          {run.task_role && <><dt>task role</dt><dd>{run.task_role}</dd></>}
          {run.usecase_id && <><dt>use case</dt><dd><a href={`#/builder/${run.usecase_id}`}>{run.usecase_id}</a></dd></>}
          <dt>rules</dt><dd className="mono small">{run.rules_version}{run.usecase_rules.length ? ` + ${run.usecase_rules.length} use-case rule(s)` : ""}{run.blocked_tools.length ? ` · blocked: ${run.blocked_tools.join(", ")}` : ""}</dd>
          <dt>created</dt><dd>{fmtTime(run.created_at)}</dd>
          <dt>predicted on</dt><dd>environment v{run.environment_version} <span className="faint mono tiny">({run.environment_fingerprint.slice(0, 8)})</span></dd>
          <dt>recommended</dt><dd>{run.recommendation?.plan_id ?? "none"}</dd>
          <dt>executed</dt><dd>{run.executed_plan_id ?? "not executed"}{obs ? ` → environment v${obs.environment_version_after}` : ""}</dd>
        </dl>
        <div className="row mt"><a className="btn" href={`#/assessment/${run.run_id}`}>See assessment</a></div>
      </Panel>
      <Panel title="Human decisions">
        {run.decisions.length === 0 ? <p className="faint small">No decision recorded.</p> : (
          <div className="table-wrap"><table className="tbl">
            <thead><tr><th scope="col">Plan</th><th scope="col">Decision</th><th scope="col">Reviewer</th><th scope="col">When</th><th scope="col">Env version</th><th scope="col">Approval state</th></tr></thead>
            <tbody>{run.decisions.map((d) => (
              <tr key={d.approval_id}><td className="strong">{d.plan_id}</td><td>{d.decision === "approve" ? "Approved" : "Rejected"}</td><td>{d.reviewer}{d.note && <div className="faint tiny">“{d.note}”</div>}</td>
                <td className="small">{fmtTime(d.decided_at)}</td><td>v{d.environment_version}</td><td className="small">{d.status}{d.invalidated_reason && <div className="faint tiny">{d.invalidated_reason}</div>}</td></tr>
            ))}</tbody>
          </table></div>
        )}
      </Panel>
      <WinPanel run={run} rules={[...(profile?.conduct.rules ?? []), ...(envs.find((e) => e.environment_id === run.environment_id)?.rules ?? [])]} onChange={setRun} />
      {obs ? (
        <Panel title="Prediction vs test results (R15)">
          <div className="grid g3"><Stat value={n("MATCH")} label="Match" /><Stat value={n("DIFFERENCE")} label="Difference" /><Stat value={n("NOT VERIFIED")} label="Not verified" /></div>
          <div className="table-wrap mt"><table className="tbl">
            <thead><tr><th scope="col">Object</th><th scope="col">Field</th><th scope="col">Predicted</th><th scope="col">Observed</th><th scope="col">Result</th></tr></thead>
            <tbody>{obs.items.map((i, k) => (
              <tr key={k}><td className="strong">{nameOf(names, i.object_id)}</td><td className="mono small">{i.field}</td>
                <td className="mono small" style={{ maxWidth: 280 }}>{fmtVal(i.predicted)}</td><td className="mono small">{i.observed === null ? "—" : fmtVal(i.observed)}</td>
                <td><ResultBadge r={i.result} />{i.note && <div className="faint tiny mt-s">{i.note}</div>}</td></tr>
            ))}</tbody>
          </table></div>
          <p className="small dim mt">Unchanged after execution: {obs.unchanged_objects.map((id) => nameOf(names, id)).join(", ") || "none"}.</p>
          <p className="faint tiny mt-s">Observed {fmtTime(obs.observed_at)} by a fresh read-only inspection of the simulated environment.</p>
        </Panel>
      ) : <Panel title="Prediction vs observation"><p className="faint small">Not executed, so there is nothing to compare yet.</p></Panel>}
      <Panel title="Trace">
        <ol className="trace">{run.trace.map((t, i) => (
          <li key={i}><span className="mono accent tiny">{t.event}</span> <span className="faint tiny">{fmtTime(t.at)}</span><p className="small mt-s">{t.detail}</p></li>
        ))}</ol>
      </Panel>
    </div>
  );
}

export function History({ runId }: { runId?: string }) {
  const { runs, refresh } = useAFM();
  useEffect(() => { void refresh(); }, [refresh, runId]);
  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head"><div>
        <p className="hud-label accent">Step 8 · What actually happened?</p>
        <h1 className="mt-s">Results & History</h1>
        <p className="lede">Every run in every playground, every human decision, and how predictions compared with observations. Stored locally as experience history; it does not train any model (R15).</p>
      </div></div>
      <div className="grid g-side">
        <Panel title="Runs">
          {runs.length === 0 ? <Empty>No runs yet.</Empty> : (
            <div className="obj-list">{runs.map((r) => (
              <a key={r.run_id} href={`#/history/${r.run_id}`} className="obj-btn" aria-current={r.run_id === runId ? "page" : undefined}
                style={r.run_id === runId ? { borderColor: "var(--accent)", background: "var(--accent-dim)" } : undefined}>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span className="small" style={{ display: "block" }}>“{r.goal}”</span>
                  <span className="faint tiny">{r.environment_name} · {fmtTime(r.created_at)} · v{r.environment_version}</span>
                  <span className="row" style={{ marginTop: 6, gap: 6 }}><RunStatusBadge s={r.status} />{r.win && <span className={`badge ${r.win === "WIN" ? "st-pass" : r.win === "NOT A WIN" ? "st-fail" : "st-unknown"}`}>{r.win}</span>}</span>
                </span>
              </a>
            ))}</div>
          )}
        </Panel>
        {runId ? <RunDetail runId={runId} /> : <Panel title="Run details"><Empty>Select a run.</Empty></Panel>}
      </div>
      <Plain>“Experience history” records what AFM predicted, what you decided and what was observed. It helps people learn and audit. It does not train the LLM or any machine-learning model.</Plain>
    </div>
  );
}
