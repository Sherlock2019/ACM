// Step 16: the AFM Result panel. All numbers come from the backend Win evaluation; the UI only displays them.
import { useState } from "react";
import { api } from "../services/api";
import type { Rule, Run, WinCondition } from "../types/afm";
import { ResultBadge } from "./ui";

const TITLES: Record<WinCondition["condition"], string> = {
  prediction_accuracy: "1 · Prediction accuracy", task_goal: "2 · Task goal achievement", rule_compliance: "3 · Rule compliance",
};
const OVERALL: Record<string, [string, string, string]> = {
  WIN: ["st-pass", "✓", "WIN"], "NOT A WIN": ["st-fail", "✕", "NOT A WIN"], "NOT VERIFIED": ["st-unknown", "?", "NOT VERIFIED"],
};

export function WinPanel({ run, rules, onChange }: { run: Run; rules: Rule[]; onChange?: (r: Run) => void }) {
  const [form, setForm] = useState({ kind: "criterion" as "criterion" | "rule", ref: "", status: "PASS" as "PASS" | "FAIL" | "NOT VERIFIED", evidence: "", reviewer: "local human" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!run.win) {
    const why = { rejected: "The plan was rejected, so nothing was executed.", unsupported: "Execution is unsupported by this adapter.",
      failed: "Execution was blocked: the approval was invalidated.", not_approved: "No plan was approved.", not_attempted: "No plan has been executed yet.",
      executed: "This run was executed before the Win evaluation existed, so it was not evaluated." }[run.execution_status];
    return (
      <section className="glass panel win-panel" aria-label="AFM Result">
        <p className="hud-label accent">AFM Result</p>
        <p className="small mt-s"><strong>Not evaluated.</strong> {why} AFM never invents observations or claims an execution-based Win without an approved, executed plan.</p>
      </section>
    );
  }
  const w = run.win;
  const manual = run.goal.success_criteria.filter((c) => c.kind === "manual");
  const submit = async () => {
    setBusy(true); setErr(null);
    try { const r = await api.verify(run.run_id, form); onChange?.(r); setForm({ ...form, evidence: "" }); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const [cls, ico, label] = OVERALL[w.overall];
  return (
    <section className="glass panel win-panel brackets" aria-label="AFM Result">
      <div className="row between">
        <p className="hud-label accent">AFM Result{w.simulated ? " · simulated" : ""}</p>
        <span className={`badge ${cls}`} style={{ fontSize: 14, padding: ".35rem .8rem" }}><span className="ico" aria-hidden="true">{ico}</span>Overall: {label}</span>
      </div>
      <p className="small mt-s">{w.explanation}</p>
      <div className="stack mt">
        {w.conditions.map((c) => (
          <details key={c.condition} className="glass-flat" style={{ padding: "10px 12px" }} open={c.status !== "PASS"}>
            <summary className="row between" style={{ cursor: "pointer" }}>
              <span><strong>{TITLES[c.condition]}</strong> <span className="faint small">· {c.question}</span></span>
              <ResultBadge r={c.status} />
            </summary>
            <p className="faint tiny mt-s">{c.summary}</p>
            <ul className="list mt-s">{c.checks.map((k, i) => (
              <li key={i} className="small" style={{ flexDirection: "column", alignItems: "stretch", gap: 2 }}>
                <span className="row between"><span>{k.name}{k.phase && <span className="chip" style={{ marginLeft: 6 }}>{k.phase}</span>}</span><ResultBadge r={k.status} /></span>
                <span className="faint tiny" style={{ overflowWrap: "anywhere" }}>{k.evidence}</span>
              </li>
            ))}</ul>
          </details>
        ))}
      </div>
      <details className="mt">
        <summary className="small dim" style={{ cursor: "pointer" }}>Record a human judgment (manual criterion or broad rule)</summary>
        <div className="grid g2 mt-s">
          <div><label className="lbl" htmlFor="v-kind">Kind</label>
            <select id="v-kind" className="field" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as "criterion" | "rule", ref: "" })}>
              <option value="criterion">Human success criterion</option><option value="rule">Rule (human judgment)</option></select></div>
          <div><label className="lbl" htmlFor="v-ref">Which</label>
            <select id="v-ref" className="field" value={form.ref} onChange={(e) => setForm({ ...form, ref: e.target.value })}>
              <option value="">Choose…</option>
              {form.kind === "criterion" ? manual.map((c) => <option key={c.id} value={c.id}>{c.description}</option>)
                : rules.map((r) => <option key={r.id} value={r.id}>{r.id} {r.title || r.text.slice(0, 40)}</option>)}
            </select></div>
          <div><label className="lbl" htmlFor="v-status">Judgment</label>
            <select id="v-status" className="field" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as "PASS" | "FAIL" | "NOT VERIFIED" })}>
              <option>PASS</option><option>FAIL</option><option>NOT VERIFIED</option></select></div>
          <div><label className="lbl" htmlFor="v-rev">Reviewer</label><input id="v-rev" className="field" value={form.reviewer} onChange={(e) => setForm({ ...form, reviewer: e.target.value })} /></div>
        </div>
        <label className="lbl mt-s" htmlFor="v-ev">Evidence reviewed</label>
        <textarea id="v-ev" className="field" rows={2} value={form.evidence} onChange={(e) => setForm({ ...form, evidence: e.target.value })} />
        {err && <p className="tiny mt-s" style={{ color: "var(--fail)" }}>{err}</p>}
        <button className="btn mt-s" disabled={busy || !form.ref || !form.evidence.trim()} onClick={submit}>Record judgment</button>
        <p className="faint tiny mt-s">A recorded FAIL always stays visible; a later PASS cannot hide it. Human approval never overrides a prohibited action.</p>
      </details>
    </section>
  );
}
