import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "../components/icons";
import { ActionCard, ChecksList, ConsequenceList, nameOf } from "../components/PlanParts";
import { Definitions, Empty, ErrorBox, EvidenceBadge, Loading, Panel, Plain, RunStatusBadge, StateDelta, StatusBadge, fmtTime } from "../components/ui";
import { api } from "../services/api";
import { go, useAFM } from "../state";
import type { Decision, Review } from "../types/afm";

function Pending() {
  const { runs } = useAFM();
  const open = runs.filter((r) => r.status === "awaiting_review" || r.status === "approved");
  return (
    <Panel title="Plans waiting for a human">
      {open.length === 0 ? <Empty>Nothing is waiting for review. Assess a goal in <a href="#/goals">Goals & Plans</a> first.</Empty> : (
        <ul className="list">{open.map((r) => (
          <li key={r.run_id} className="glass-flat between" style={{ padding: 12 }}>
            <span><span className="small">“{r.goal}”</span><span className="faint tiny" style={{ display: "block" }}>{r.environment_name} · {fmtTime(r.created_at)} · {r.run_id}</span></span>
            <span className="row"><RunStatusBadge s={r.status} />
              {r.recommended && <a className="btn-primary" href={`#/review/${r.run_id}/${r.recommended}`}>Review {r.recommended}</a>}
              <a className="btn" href={`#/assessment/${r.run_id}`}>All plans</a></span>
          </li>
        ))}</ul>
      )}
    </Panel>
  );
}

export function ReviewPage({ runId, planId }: { runId?: string; planId?: string }) {
  const { views, envs, profile, refresh } = useAFM();
  const [rv, setRv] = useState<Review | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewer, setReviewer] = useState("local human");
  const [note, setNote] = useState("");
  const [ack, setAck] = useState(false);
  const [agree, setAgree] = useState(false);
  const dlg = useRef<HTMLDialogElement>(null);

  const load = useCallback(async () => {
    if (!runId || !planId) return;
    try { setRv(await api.review(runId, planId)); setErr(null); } catch (e) { setErr((e as Error).message); }
  }, [runId, planId]);
  useEffect(() => { setRv(null); void load(); }, [load]);

  if (!runId || !planId) return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head"><div><p className="hud-label accent">Step 12 · Ask the human</p><h1 className="mt-s">Human Review</h1>
        <p className="lede">Every action that changes an environment needs your explicit approval for that exact plan and environment state (R08, R23).</p></div></div>
      <Pending />
    </div>
  );
  if (err && !rv) return <ErrorBox error={err} onRetry={load} />;
  if (!rv) return <Loading what="review" />;

  const a = rv.assessment;
  const env = envs.find((e) => e.environment_id === rv.environment_id);
  const names: Record<string, string> = Object.fromEntries((views[rv.environment_id]?.objects ?? []).map((o) => [o.id, o.name]));
  const active: Decision | undefined = rv.decisions.find((d) => d.status === "active");
  const done = rv.decisions.find((d) => d.status !== "active");
  const goalFail = a.checks.find((c) => c.check === "goal")?.status !== "PASS";
  const executed = rv.run_status === "executed";

  const decide = async (decision: "approve" | "reject") => {
    setBusy(true); setErr(null);
    try {
      await api.decide(rv.run_id, { plan_id: a.plan.plan_id, decision, plan_hash: a.plan_hash, environment_version: a.simulation.environment_version, reviewer, note, criteria_agreed: decision === "approve" && agree });
      dlg.current?.close(); await load(); await refresh();
    } catch (e) { setErr((e as Error).message); dlg.current?.close(); await load(); } finally { setBusy(false); }
  };
  const execute = async () => {
    if (!active) return;
    setBusy(true); setErr(null);
    try { await api.execute(rv.run_id, a.plan.plan_id, active.approval_id); await refresh(); go(`history/${rv.run_id}`); }
    catch (e) { setErr((e as Error).message); await load(); await refresh(); } finally { setBusy(false); }
  };

  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head">
        <div>
          <p className="hud-label accent">Step 12 · Ask the human · {rv.environment_name} · {rv.run_id}</p>
          <h1 className="mt-s">Review {a.plan.plan_id}: {a.plan.title}</h1>
          <p className="lede">Task goal: “{rv.goal.text}”</p>
        </div>
        <RunStatusBadge s={rv.run_status} />
      </div>
      {rv.stale && <div className="error-box" role="alert"><strong>The environment changed since this prediction</strong> (predicted on v{a.simulation.environment_version}, now v{rv.environment_version_now}). This review is out of date (R13). <a href="#/goals">Run a new assessment</a>.</div>}
      {!rv.execution_supported && <div className="warn">This environment's adapter cannot execute actions. You can record a decision, but execution is unsupported.</div>}
      {err && <ErrorBox error={err} />}

      <div className="grid g2">
        <Panel title="Exact proposed actions">
          <div className="stack">{a.plan.actions.map((x, i) => <ActionCard key={x.action_id} a={x} names={names} step={i + 1} />)}</div>
          <p className="faint tiny mt">Environment: {rv.environment_name} · plan hash <span className="mono">{a.plan_hash}</span> · environment v{a.simulation.environment_version}. Your approval covers exactly this plan, these parameters and this version (R23).</p>
        </Panel>
        <Panel title="Current state → predicted state">
          <ul className="list">{Object.entries(a.simulation.predicted_objects).map(([id, after]) => (
            <li key={id} style={{ flexDirection: "column", alignItems: "stretch", gap: 4 }}>
              <span className="row between"><strong className="small">{nameOf(names, id)}</strong>{rv.evidence[id] ? <EvidenceBadge e={rv.evidence[id]} /> : <span className="chip">new object</span>}</span>
              <StateDelta changedOnly before={rv.current_state[id] ?? {}} after={after} names={names} />
            </li>
          ))}</ul>
          <p className="faint tiny mt">{a.simulation.applies_to}</p>
        </Panel>
      </div>
      <div className="grid g2">
        <Panel title="Direct consequences"><ConsequenceList items={a.simulation.consequences} names={names} filter="direct" /></Panel>
        <Panel title="Effects on connected objects"><ConsequenceList items={a.simulation.consequences} names={names} filter="connected" /></Panel>
      </div>
      <div className="grid g2">
        <Panel title="Rule, permission & goal checks"><ChecksList checks={a.checks} /></Panel>
        <Panel title="Applicable rules, evidence & unknowns">
          <p className="small">The {profile?.conduct.rules.length ?? 32} permanent rules of conduct ({profile?.rules_version}) <a href="#/identity">(view)</a> plus:</p>
          <ul className="bullets mt-s">{env?.rules.map((r) => <li key={r.id}><span className="mono accent">{r.id}</span> {r.text}</li>)}</ul>
          <p className="hud-label mt">Assumptions & unknowns</p>
          <ul className="bullets mt-s">
            {a.plan.assumptions.map((x) => <li key={x}>Assumption: {x}</li>)}
            {a.simulation.unknowns.map((x) => <li key={x}>Unknown: {x}</li>)}
          </ul>
          <p className="hud-label mt">Evidence for affected objects</p>
          <ul className="list mt-s">{Object.entries(rv.evidence).map(([id, e]) => <li key={id} className="small"><EvidenceBadge e={e} /> {nameOf(names, id)}</li>)}</ul>
          <p className="faint tiny mt">Simulation rules used: {Array.from(new Set(a.simulation.consequences.map((c) => c.evidence_rule.split(" ")[0]))).join(", ")}</p>
        </Panel>
      </div>
      {env && <Definitions items={env.definitions} />}

      <section className="glass panel brackets" aria-labelledby="decide-h">
        <h2 id="decide-h" className="hud-label accent">Your decision</h2>
        {executed ? <p className="mt small">This run was executed once. <a href={`#/history/${rv.run_id}`}>See prediction vs observation</a>.</p>
        : done ? <p className="mt small">This plan was <strong>{done.decision === "approve" ? `approved (${done.status})` : "rejected"}</strong> by {done.reviewer} at {fmtTime(done.decided_at)}.{done.invalidated_reason ? ` ${done.invalidated_reason}` : ""}</p>
        : active ? (
          <div className="stack mt">
            <p className="small"><StatusBadge s="PASS" /> Approved by {active.reviewer} at {fmtTime(active.decided_at)} for environment v{active.environment_version}.</p>
            <p className="small dim">Before running, the backend checks the approval again, along with the plan hash, the environment version, permissions and rules. Then it executes once, in the simulation only.</p>
            <div className="row"><button className="btn-primary btn-lg" onClick={execute} disabled={busy || rv.stale || !rv.execution_supported}><Icon name="play" size={15} /> {busy ? "Executing…" : "Run approved simulated execution"}</button></div>
          </div>
        ) : !a.approvable ? <p className="mt small">{a.approvable_reason}</p> : (
          <div className="stack mt">
            {goalFail && <div className="warn small"><strong>Warning:</strong> the predicted result does not meet the goal. {a.checks.find((c) => c.check === "goal")?.details.find((d) => d.startsWith("FAIL"))}</div>}
            <div className="grid g2">
              <div><label className="lbl" htmlFor="reviewer">Reviewer name</label><input id="reviewer" className="field" value={reviewer} onChange={(e) => setReviewer(e.target.value)} maxLength={80} /></div>
              <div><label className="lbl" htmlFor="note">Note (optional)</label><input id="note" className="field" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} /></div>
            </div>
            <div className="row">
              <button className="btn-primary btn-lg" disabled={busy || rv.stale} onClick={() => { setAck(false); setAgree(false); dlg.current?.showModal(); }}><Icon name="check" size={15} /> Approve simulated execution</button>
              <button className="btn-danger btn-lg" disabled={busy} onClick={() => decide("reject")}><Icon name="x" size={15} /> Reject plan</button>
            </div>
            <p className="faint tiny">Local prototype workflow: there is no login, so it does not provide production-grade authentication or authorization.</p>
          </div>
        )}
      </section>

      <dialog ref={dlg} className="modal" aria-labelledby="confirm-h">
        <h2 id="confirm-h">Approve {a.plan.plan_id}?</h2>
        <p className="mt small dim">You approve exactly these changes in the <strong>simulated</strong> {rv.environment_name}:</p>
        <ul className="bullets mt-s">{a.simulation.consequences.filter((c) => c.type === "direct" && c.relationship_to_target === "target").map((c, i) => <li key={i}>{c.description}</li>)}</ul>
        {goalFail && <div className="warn small mt">This plan does not meet the goal.</div>}
        <label className="row mt small" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} style={{ marginTop: 3 }} />
          I reviewed the consequences, checks and unknowns. My approval applies only to this plan, its parameters, environment v{a.simulation.environment_version} and the current policy.
        </label>
        <div className="glass-flat mt" style={{ padding: 10 }}>
          <p className="hud-label">Success criteria (used for the AFM Win)</p>
          <ul className="bullets tiny mt-s">{rv.goal.success_criteria.map((c) => <li key={c.id}>{c.description} <span className="faint">({c.source === "human" ? "yours" : "proposed by adapter"})</span></li>)}</ul>
          <label className="row small mt-s" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} style={{ marginTop: 3 }} />I agree these success criteria define success. (Optional: without it, task goal achievement stays NOT VERIFIED.)</label>
        </div>
        <div className="row mt-l" style={{ justifyContent: "flex-end" }}>
          <button className="btn" onClick={() => dlg.current?.close()}>Cancel</button>
          <button className="btn-primary" disabled={!ack || busy} onClick={() => decide("approve")}>Approve</button>
        </div>
      </dialog>
      <Plain>Nothing has changed yet. If you approve, AFM runs this plan once in the simulation. If anything changed since the prediction, it refuses and asks you to look again (R13).</Plain>
    </div>
  );
}
