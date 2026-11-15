import { useEffect, useState } from "react";
import { Icon } from "../components/icons";
import { ActionCard, ChecksList, ConsequenceList, nameOf, predictedDeltas } from "../components/PlanParts";
import { RelationshipGraph } from "../components/RelationshipGraph";
import { Definitions, Empty, ErrorBox, Loading, Panel, Plain, RunStatusBadge, StatusBadge } from "../components/ui";
import { api } from "../services/api";
import { useAFM } from "../state";
import type { PlanAssessment, Run } from "../types/afm";
import { GoalSummary } from "./Goals";

const check = (a: PlanAssessment, k: string) => a.checks.find((c) => c.check === k)!.status;

function Comparison({ run, names }: { run: Run; names: Record<string, string> }) {
  const rec = run.recommendation?.plan_id;
  const deltas = Object.fromEntries(run.assessments.map((a) => [a.plan.plan_id, predictedDeltas(a)]));
  const ids = Array.from(new Set(run.assessments.flatMap((a) => a.simulation.consequences.filter((c) => c.status !== "unknown").map((c) => c.affected_object_id))));
  const cell = (a: PlanAssessment, id: string) => {
    const cs = a.simulation.consequences.filter((c) => c.affected_object_id === id);
    if (!cs.length) return <span className="faint">unchanged</span>;
    const warn = cs.some((c) => c.effect === "warning"), good = cs.some((c) => c.effect === "benefit");
    return (
      <span className="delta small" style={{ color: warn ? "var(--review)" : undefined }}>
        {warn ? "⚠ " : good ? "✓ " : ""}{deltas[a.plan.plan_id][id] ?? cs[cs.length - 1].description}
      </span>
    );
  };
  return (
    <Panel title="Side-by-side comparison (R31)">
      <div className="table-wrap">
        <table className="tbl">
          <caption className="sr-only">Plans compared by predicted effect</caption>
          <thead><tr><th scope="col">Object / check</th>{run.assessments.map((a) => (
            <th scope="col" key={a.plan.plan_id}>{a.plan.plan_id} · {a.plan.title}{a.plan.plan_id === rec && <span className="ribbon" style={{ marginLeft: 8 }}>Recommended</span>}</th>
          ))}</tr></thead>
          <tbody>
            {ids.map((id) => <tr key={id}><td className="strong">{nameOf(names, id)}</td>{run.assessments.map((a) => <td key={a.plan.plan_id}>{cell(a, id)}</td>)}</tr>)}
            {(["goal", "rules", "permission", "human_review"] as const).map((k) => (
              <tr key={k}><td className="strong">{{ goal: "Goal satisfied", rules: "Rule compliance", permission: "Permission", human_review: "Approval" }[k]}</td>
                {run.assessments.map((a) => <td key={a.plan.plan_id}><StatusBadge s={check(a, k)} /></td>)}</tr>
            ))}
            <tr><td className="strong">Benefits / warnings</td>{run.assessments.map((a) => <td key={a.plan.plan_id} className="small">+{a.benefits} / ⚠{a.warnings}</td>)}</tr>
            <tr><td className="strong">Objects changed · reversible</td>{run.assessments.map((a) => <td key={a.plan.plan_id} className="small">{a.changed_objects} · {a.reversible == null ? "unknown" : a.reversible ? "yes" : "no"}</td>)}</tr>
            <tr><td className="strong">Unknowns</td>{run.assessments.map((a) => <td key={a.plan.plan_id} className="small">{a.simulation.unknowns.length} reported · {a.simulation.consequences.filter((c) => c.status === "unknown").length} unknown dependency</td>)}</tr>
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function PlanCard({ a, run, names }: { a: PlanAssessment; run: Run; names: Record<string, string> }) {
  const rec = run.recommendation?.plan_id === a.plan.plan_id;
  const decision = run.decisions.find((d) => d.plan_id === a.plan.plan_id);
  const open = !run.executed_plan_id && !["stale", "unsupported_goal"].includes(run.status);
  return (
    <article className={`glass panel plan-card ${rec ? "recommended" : ""}`} aria-labelledby={`plan-${a.plan.plan_id}`}>
      <div className="row between">
        <div>
          <p className="hud-label">{a.plan.plan_id} · proposed by {a.plan.proposed_by === "llm" ? "LLM (inferred, validated)" : a.plan.proposed_by.replace("_", " ")}</p>
          <h3 id={`plan-${a.plan.plan_id}`} className="mt-s">{a.plan.title}</h3>
        </div>
        {rec && <span className="ribbon"><Icon name="check" size={12} /> AFM recommends</span>}
      </div>
      <details><summary className="small dim" style={{ cursor: "pointer" }}>Proposed actions ({a.plan.actions.length})</summary>
        <div className="stack mt-s">{a.plan.actions.map((x, i) => <ActionCard key={x.action_id} a={x} names={names} step={i + 1} />)}</div></details>
      {a.simulation.errors.map((e) => <ErrorBox key={e.action_id} error={`Step ${e.step}: ${e.message}`} />)}
      <div><p className="hud-label">Direct consequences</p><div className="mt-s"><ConsequenceList items={a.simulation.consequences} names={names} filter="direct" /></div></div>
      <div><p className="hud-label">Effects on connected objects</p><div className="mt-s"><ConsequenceList items={a.simulation.consequences} names={names} filter="connected" /></div></div>
      <div><p className="hud-label">Checks</p><div className="mt-s"><ChecksList checks={a.checks} compact /></div>
        <details className="mt-s"><summary className="small dim" style={{ cursor: "pointer" }}>Show check details</summary><div className="mt-s"><ChecksList checks={a.checks} /></div></details></div>
      <details><summary className="small dim" style={{ cursor: "pointer" }}>Evidence, assumptions & unknowns</summary>
        <ul className="bullets tiny mt-s">
          {a.plan.assumptions.map((x) => <li key={x}>Assumption: {x}</li>)}
          {a.plan.known_limitations.map((x) => <li key={x}>Limitation: {x}</li>)}
          {a.simulation.unknowns.map((x) => <li key={x}>Unknown: {x}</li>)}
        </ul>
        <p className="faint tiny mt-s">{a.simulation.applies_to}</p>
      </details>
      <p className={a.approvable && !a.meets_goal_and_rules ? "warn small" : "small dim"}>{a.approvable_reason}</p>
      <div className="row">
        {decision && <span className="chip">{decision.decision === "approve" ? `Approved · ${decision.status}` : "Rejected"}</span>}
        {a.approvable && open && !decision && <a className={rec ? "btn-primary" : "btn"} href={`#/review/${run.run_id}/${a.plan.plan_id}`}><Icon name="review" size={15} /> Review this plan</a>}
        {decision?.status === "active" && <a className="btn-primary" href={`#/review/${run.run_id}/${a.plan.plan_id}`}>Go to execution</a>}
      </div>
    </article>
  );
}

export function Assessment({ runId }: { runId?: string }) {
  const { views, envs, runs, selected, select } = useAFM();
  const [run, setRun] = useState<Run | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [shown, setShown] = useState<string | null>(null);
  const target = runId ?? runs.find((r) => r.environment_id === selected && r.status !== "unsupported_goal")?.run_id;
  useEffect(() => {
    if (!target) { setRun(null); return; }
    api.run(target).then((r) => { setRun(r); setShown(r.recommendation?.plan_id ?? r.assessments[0]?.plan.plan_id ?? null); select(r.environment_id); }).catch((e) => setErr(e.message));
  }, [target, select]);
  if (err) return <ErrorBox error={err} />;
  if (!target) return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head"><div><p className="hud-label accent">Step 6 · What could happen?</p><h1 className="mt-s">Consequence Assessment</h1></div></div>
      <Empty>No assessment yet{selected ? " for this playground" : ""}. Enter a goal in <a href="#/goals">Goals & Plans</a> first.</Empty>
    </div>
  );
  if (!run) return <Loading what="assessment" />;
  const view = views[run.environment_id];
  const env = envs.find((e) => e.environment_id === run.environment_id);
  const names: Record<string, string> = Object.fromEntries((view?.objects ?? []).map((o) => [o.id, o.name]));
  const shownA = run.assessments.find((a) => a.plan.plan_id === shown);
  const warnIds = shownA ? Array.from(new Set(shownA.simulation.consequences.filter((c) => c.effect === "warning").map((c) => c.affected_object_id))) : [];
  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head">
        <div>
          <p className="hud-label accent">Step 6 · What could happen? · {run.environment_name}</p>
          <h1 className="mt-s">Consequence Assessment</h1>
          <p className="lede">Each plan was simulated on a copy of the environment. Predictions are labelled known in simulation, conditional or unknown; nothing real has changed.</p>
        </div>
        <RunStatusBadge s={run.status} />
      </div>
      <GoalSummary run={run} />
      {run.recommendation && run.goal.supported && (
        <section className={run.recommendation.plan_id ? "glass panel brackets" : "error-box"} aria-label="AFM recommendation">
          <p className="hud-label accent">AFM recommendation</p>
          <p className="mt-s" style={{ fontSize: 16 }}>{run.recommendation.plan_id ? <strong>Recommend {run.recommendation.plan_id}. </strong> : <strong>No plan recommended. </strong>}{run.recommendation.reason}</p>
        </section>
      )}
      {view && run.assessments.length > 0 && (
        <Panel title="Predicted change across connected objects" right={
          <div className="row" role="group" aria-label="Show plan">{run.assessments.map((a) => (
            <button key={a.plan.plan_id} className="btn" aria-pressed={shown === a.plan.plan_id} onClick={() => setShown(a.plan.plan_id)}
              style={shown === a.plan.plan_id ? { borderColor: "var(--accent)", background: "var(--accent-dim)" } : undefined}>{a.plan.plan_id}</button>
          ))}</div>}>
          {shownA && <RelationshipGraph objects={view.objects} relationships={view.relationships} layout={view.layout} deltas={predictedDeltas(shownA)} warn={warnIds} />}
          {shownA && (
            <ol className="bullets mt" aria-label={`Predicted changes for ${shownA.plan.plan_id}, as a list`}>
              {shownA.simulation.consequences.map((c, i) => (
                <li key={i}>{c.effect === "warning" ? "⚠ " : c.effect === "benefit" ? "✓ " : ""}<strong>{nameOf(names, c.affected_object_id)}</strong> ({c.type}, {c.status.replace(/_/g, " ")}): {c.description} <span className="faint tiny mono">{c.evidence_rule.split(" ")[0]}</span></li>
              ))}
            </ol>
          )}
        </Panel>
      )}
      {env && <Definitions items={env.definitions} />}
      {run.assessments.length > 0 && <Comparison run={run} names={names} />}
      {run.assessments.length > 0 && <div className="grid g2">{run.assessments.map((a) => <PlanCard key={a.plan.plan_id} a={a} run={run} names={names} />)}</div>}
      {run.llm_rejections.length > 0 && (
        <Panel title="LLM suggestions rejected by AFM's gate">
          <p className="small dim">The LLM may propose plans only in AFM's structured format. Each proposal is validated with the same schemas, tools and permissions as AFM's own plans. These were refused; nothing in them was executed (R09, R22):</p>
          <ul className="list mt">{run.llm_rejections.map((r, i) => (
            <li key={i} className="glass-flat" style={{ padding: 12, flexDirection: "column", alignItems: "stretch" }}>
              <div className="row between"><strong className="small">{String(r.raw.title ?? "Untitled proposal")}</strong><StatusBadge s="FAIL" /></div>
              <ul className="bullets tiny mt-s">{r.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
            </li>
          ))}</ul>
        </Panel>
      )}
      <Plain>Green ✓ marks a predicted benefit, amber ⚠ a predicted problem. “Conditional” means the prediction depends on assumptions listed with it; “unknown” means AFM cannot tell. Approving a plan is the next step, and it is always yours.</Plain>
    </div>
  );
}
