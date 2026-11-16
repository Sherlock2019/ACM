// Real-project mode (Phase 1): connect a local folder or public GitHub repo, then walk the 16 steps on REAL test results.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Icon } from "../components/icons";
import { ErrorBox, Loading, ResultBadge } from "../components/ui";
import { WinBody } from "../components/WinPanel";
import { api } from "../services/api";
import { go, useAFM } from "../state";
import type { PCheck, PCheckType, PConsequence, PCriterion, PPrecheck, PPrediction, ProjectDraft, ProjectListItem, ProjectTest } from "../types/afm";

type S = "completed" | "waiting_info" | "waiting_review" | "approved" | "rejected" | "ready" | "failed" | "not_started" | "optional" | "not_verified" | "in_progress";
const ST: Record<S, [string, string, string]> = {
  completed: ["st-pass", "✓", "Completed"], approved: ["st-pass", "✓", "Approved"], waiting_info: ["st-review", "!", "Waiting for information"],
  waiting_review: ["st-review", "!", "Waiting for review"], ready: ["st-review", "▸", "Ready to run"], rejected: ["st-fail", "✕", "Rejected"],
  failed: ["st-fail", "✕", "Failed"], not_started: ["st-unknown", "○", "Not started"], optional: ["st-unknown", "·", "Optional"],
  not_verified: ["st-unknown", "?", "Not verified"], in_progress: ["st-review", "…", "In progress"],
};
const CLS: Partial<Record<S, string>> = { completed: "done", approved: "approved", waiting_info: "awaiting_info", waiting_review: "awaiting_review", ready: "ready", rejected: "rejected", failed: "failed", not_started: "not_started" };

function Step({ n, title, s, children, open }: { n: number; title: string; s: S; children: ReactNode; open?: boolean }) {
  const [cls, ico, label] = ST[s];
  return (
    <li className={`step step-${CLS[s] ?? s}`} id={`pstep-${n}`}>
      <details open={open}>
        <summary><span className="step-n mono">{n}</span><span className="step-title">{title}</span>
          <span className="row" style={{ marginLeft: "auto" }}><span className={`badge ${cls}`}><span className="ico" aria-hidden="true">{ico}</span>{label}</span></span></summary>
        <div className="step-body">{children}</div>
      </details>
    </li>
  );
}

const CHECK_LABEL: Record<PCheckType, string> = { command_exit: "Command exit code", test_outcome: "One test's outcome", no_other_changes: "No other test changes", manual: "Checked by a human" };
const blankCheck = (): PCheck => ({ type: "command_exit", command: 0, test: "", expect: "0" });

function CheckEditor({ c, onChange, commands, id }: { c: PCheck; onChange: (c: PCheck) => void; commands: string[][]; id: string }) {
  return (
    <div className="row" style={{ gap: 6 }}>
      <select className="field" style={{ width: "auto" }} aria-label="How it is measured" value={c.type}
        onChange={(e) => { const t = e.target.value as PCheckType; onChange({ ...c, type: t, expect: t === "command_exit" ? "0" : t === "test_outcome" ? "passed" : "" }); }}>
        {(Object.keys(CHECK_LABEL) as PCheckType[]).map((t) => <option key={t} value={t}>{CHECK_LABEL[t]}</option>)}
      </select>
      {c.type !== "manual" && (
        <select className="field" style={{ width: "auto" }} aria-label="Command" value={c.command} onChange={(e) => onChange({ ...c, command: Number(e.target.value) })}>
          {(commands.length ? commands : [[]]).map((a, i) => <option key={i} value={i}>cmd {i + 1}{a.length ? `: ${a.join(" ").slice(0, 30)}` : ""}</option>)}
        </select>
      )}
      {c.type === "test_outcome" && <input className="field" style={{ flex: 1, minWidth: 180 }} aria-label="Test id" placeholder="tests/test_x.py::test_y" value={c.test} onChange={(e) => onChange({ ...c, test: e.target.value })} list={`${id}-tests`} />}
      {c.type === "command_exit" && (
        <select className="field" style={{ width: "auto" }} aria-label="Expected exit" value={c.expect} onChange={(e) => onChange({ ...c, expect: e.target.value })}>
          <option value="0">exits 0 (success)</option><option value="nonzero">exits non-zero</option><option value="same">same as before the change</option></select>
      )}
      {c.type === "test_outcome" && (
        <select className="field" style={{ width: "auto" }} aria-label="Expected outcome" value={c.expect} onChange={(e) => onChange({ ...c, expect: e.target.value })}>
          <option value="passed">passes</option><option value="failed">fails</option></select>
      )}
    </div>
  );
}

interface Form { goal: string; desired_input: string; desired_output: string; patch: string; commands: string; predictions: PPrediction[]; criteria: PCriterion[]; assumptions: string; unknowns: string; plan_source: "human" | "llm_draft_edited";
  plan_title: string; consequences: PConsequence[]; alternatives: { title: string; applies: boolean; risks: number; files: number }[] }
const toForm = (p: ProjectTest): Form => ({
  goal: p.goal, desired_input: p.desired_input, desired_output: p.desired_output, patch: p.patch,
  commands: p.commands.map((a) => a.join(" ")).join("\n") || (p.inspection.suggested_commands[0]?.argv.join(" ") ?? ""),
  predictions: p.predictions.map((x) => ({ statement: x.statement, check: x.check, required: x.required })),
  criteria: p.criteria.map((c) => ({ text: c.text, check: c.check, source: c.source })),
  assumptions: p.assumptions.join("\n"), unknowns: p.unknowns.join("\n"), plan_source: p.plan_source,
  plan_title: p.plan_title ?? "", consequences: p.consequences ?? [], alternatives: p.alternatives ?? [],
});
const KIND: Record<PConsequence["kind"], [string, string]> = { benefit: ["st-pass", "benefit"], risk: ["st-fail", "risk"], neutral: ["st-unknown", "neutral"], unknown: ["st-review", "unknown"] };
const REL: Record<PConsequence["relation"], string> = { target: "direct · target", connected: "connected", environment: "whole project" };

/** Drafts saved before multi-plan support become a single plan. */
const withPlans = (d: ProjectDraft["draft"]): ProjectDraft["draft"] => d.plans?.length ? d : {
  ...d, recommended: 0, recommended_why: "",
  plans: [{ title: "Plan A", approach: "", edits: [], patch: d.patch ?? "", consequences: [], predictions: d.predictions ?? [], risks: [],
    applies: undefined, patch_check: (d as { patch_check?: PPrecheck[] }).patch_check }],
};

/** Step 8: the alternative plans side by side, each with its predicted consequences, and ACFM's recommendation. */
function PlanCompare({ draft, canUse, onUse }: { draft: ProjectDraft["draft"]; canUse: boolean; onUse: (i: number) => void }) {
  const [open, setOpen] = useState<number | null>(null);
  const plans = draft.plans;
  return (
    <div className="mt-s">
      <p className="tiny faint">{plans.length} plan(s) · {draft.commands.length} test command(s) · {draft.criteria.length} success criteria <span className="ev ev-inferred">LLM-generated</span></p>
      {plans.length > 1 && draft.recommended_why && <p className="small mt-s"><strong>ACFM recommends {plans[draft.recommended]?.title}:</strong> {draft.recommended_why}</p>}
      <div className={`grid ${plans.length > 2 ? "g3" : plans.length === 2 ? "g2" : ""} mt-s`}>
        {plans.map((pl, k) => {
          const risks = pl.consequences.filter((c) => c.kind === "risk").length, benefits = pl.consequences.filter((c) => c.kind === "benefit").length;
          const rec = plans.length > 1 && k === draft.recommended;
          const st = pl.applies === undefined ? (pl.patch ? "not checked" : "no code change") : pl.applies ? "applies cleanly" : pl.patch ? "does not apply" : "no code change";
          return (
            <div key={k} className="glass-flat plan-card" style={{ padding: 10, borderColor: rec ? "rgba(var(--accent-rgb),.6)" : undefined }}>
              <p className="row between" style={{ flexWrap: "nowrap", gap: 6 }}><strong className="small">{pl.title}</strong>{rec && <span className="badge st-pass">recommended</span>}</p>
              {pl.approach && <p className="tiny dim mt-s">{pl.approach}</p>}
              <p className="tiny mt-s"><span className={`badge ${pl.applies ? "st-pass" : pl.patch ? "st-fail" : "st-unknown"}`}>{st}</span> {pl.changed_files?.length ? pl.changed_files.join(", ") : ""}</p>
              {pl.edit_problems && pl.edit_problems.length > 0 && <ul className="bullets tiny mt-s" style={{ color: "var(--fail)" }}>{pl.edit_problems.map((x) => <li key={x}>{x}</li>)}</ul>}
              <p className="tiny mt-s">Predicted consequences: <strong>{pl.consequences.length}</strong> · <span style={{ color: "var(--pass)" }}>{benefits} benefit(s)</span> · <span style={{ color: "var(--fail)" }}>{risks} risk(s)</span> · {pl.predictions.length} testable prediction(s)</p>
              {pl.risks.length > 0 && <ul className="bullets tiny mt-s">{pl.risks.slice(0, 4).map((x) => <li key={x}>{x}</li>)}</ul>}
              <div className="row mt-s"><button className="btn" onClick={() => setOpen(open === k ? null : k)}>{open === k ? "Hide details" : "Consequences & code"}</button>
                {canUse && <button className={rec || plans.length === 1 ? "btn-primary" : "btn"} onClick={() => onUse(k)}><Icon name="check" size={14} /> Use {plans.length > 1 ? `plan ${String.fromCharCode(65 + k)}` : "this plan"}</button>}</div>
            </div>
          );
        })}
      </div>
      {open !== null && plans[open] && (
        <div className="glass-flat mt-s" style={{ padding: 10 }}>
          <p className="hud-label">{plans[open].title} · predicted consequences per object</p>
          <div className="mt-s"><ConsequenceTable items={plans[open].consequences} /></div>
          {plans[open].patch && <><p className="hud-label mt">Exact code change (built by ACFM from the edits)</p><pre className="code tiny">{plans[open].patch}</pre></>}
        </div>
      )}
      {canUse && <p className="tiny faint mt-s">“Use” fills steps 1, 8, 10 and 11 with that plan and runs the pre-check. Nothing runs until you approve in step 12.</p>}
    </div>
  );
}

function ConsequenceTable({ items }: { items: PConsequence[] }) {
  if (!items.length) return <p className="tiny faint">No consequences predicted.</p>;
  const order = { target: 0, connected: 1, environment: 2 } as const;
  return (
    <div className="table-wrap"><table className="tbl"><thead><tr><th scope="col">Object</th><th scope="col">Relation</th><th scope="col">Predicted effect</th><th scope="col">Kind</th><th scope="col">Source</th></tr></thead>
      <tbody>{[...items].sort((a, b) => order[a.relation] - order[b.relation]).map((c, i) => (
        <tr key={i}><td className="mono tiny" style={{ overflowWrap: "anywhere" }}>{c.object}</td><td className="tiny">{REL[c.relation]}</td>
          <td className="tiny">{c.effect}{c.why && <div className="faint">{c.why}</div>}</td>
          <td><span className={`badge ${KIND[c.kind][0]}`}>{KIND[c.kind][1]}</span><div className="tiny faint">{c.likelihood}</div></td>
          <td>{c.source === "acfm_search" ? <span className="ev ev-observed">found by ACFM</span> : c.source === "human" ? <span className="ev ev-configured">human</span> : <span className="ev ev-inferred">LLM-inferred</span>}</td></tr>
      ))}</tbody></table></div>
  );
}
const parseCommands = (t: string) => t.split("\n").map((l) => l.trim().split(/\s+/).filter(Boolean)).filter((a) => a.length);
const lines = (t: string) => t.split("\n").map((l) => l.trim()).filter(Boolean);
const toBody = (f: Form) => ({ goal: f.goal, desired_input: f.desired_input, desired_output: f.desired_output, patch: f.patch, commands: parseCommands(f.commands),
  predictions: f.predictions.filter((x) => x.statement.trim()), criteria: f.criteria.filter((c) => c.text.trim()), assumptions: lines(f.assumptions), unknowns: lines(f.unknowns), plan_source: f.plan_source,
  plan_title: f.plan_title, consequences: f.consequences, alternatives: f.alternatives });

function ProjectFlow({ id }: { id: string }) {
  const { llm } = useAFM();
  const [p, setP] = useState<ProjectTest | null>(null);
  const [f, setF] = useState<Form | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [filter, setFilter] = useState("");
  const [ask, setAsk] = useState("");
  const [reviewer, setReviewer] = useState("local human");
  const [agreed, setAgreed] = useState(false);
  const [ver, setVer] = useState({ kind: "prediction" as "prediction" | "criterion" | "rule", ref: "", status: "PASS" as "PASS" | "FAIL", evidence: "" });

  const load = useCallback(async () => {
    try { const x = await api.project(id); setP(x); setF(toForm(x)); setErr(null); } catch (e) { setErr((e as Error).message); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  // explain the project automatically once, right after the scan (saved, so it never repeats for this project test)
  const autoAsked = useRef(false);
  useEffect(() => {
    if (p && !p.overview && !autoAsked.current && llm && !llm.mock && p.status === "inspected" && !p.chat.length) {
      autoAsked.current = true;
      void describe();
    }
  });
  const act = async (label: string, fn: () => Promise<ProjectTest | void>) => {
    setBusy(label); setErr(null);
    try { const x = await fn(); if (x) { setP(x); setF(toForm(x)); } } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  const describe = async () => {
    setBusy("describe"); setErr(null);
    try { const x = await api.describeProject(id); setP(x); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  const dirty = useMemo(() => !!(p && f && JSON.stringify(toBody(f)) !== JSON.stringify(toBody(toForm(p)))), [p, f]);
  if (err && !p) return <ErrorBox error={err} onRetry={load} />;
  if (!p || !f) return <Loading what="project test" />;

  const ins = p.inspection;
  const ran = p.status === "executed" || p.status === "failed";
  const preFail = p.precheck.some((i) => i.status === "FAIL");
  const d = p.decision;
  const cmds = parseCommands(f.commands);
  const set = (patch: Partial<Form>) => setF({ ...f, ...patch });
  const save = () => act("save", () => api.saveProjectPlan(p.id, toBody(f)));
  const sendAsk = () => act("ask", async () => {
    const x = await api.chatProject(p.id, ask.trim(), picked);
    setAsk("");
    setP(x);  // keep the user's unsaved form edits; only the chat changes
  });
  const applyDraft = (x: ProjectDraft["draft"], i: number) => {
    const pl = x.plans[i];
    // the latest plain-words request is the newest intent: its goal replaces the saved one (still editable in step 1)
    const next: Form = { ...f, goal: x.goal || f.goal, desired_input: x.desired_input || f.desired_input,
      desired_output: x.desired_output || f.desired_output, patch: pl?.patch || f.patch,
      commands: x.commands.length ? x.commands.map((a) => a.join(" ")).join("\n") : f.commands,
      predictions: pl?.predictions.length ? pl.predictions : f.predictions, criteria: x.criteria.length ? x.criteria : f.criteria,
      assumptions: x.assumptions.length ? x.assumptions.join("\n") : f.assumptions, unknowns: x.unknowns.length ? x.unknowns.join("\n") : f.unknowns,
      plan_source: "llm_draft_edited", plan_title: pl?.title ?? "", consequences: pl?.consequences ?? [],
      alternatives: x.plans.filter((_, j) => j !== i).map((o) => ({ title: o.title, applies: !!o.applies, risks: o.consequences.filter((c) => c.kind === "risk").length, files: o.changed_files?.length ?? 0 })) };
    setF(next);
    if (!next.goal.trim()) { setErr("Write the Task Goal in step 1, then press “Use this plan” again."); return; }
    void act("save", () => api.saveProjectPlan(p.id, toBody(next)));
  };
  const SaveBtn = () => ran ? null : (
    <div className="row mt"><button className="btn-primary" disabled={!!busy || !dirty || !f.goal.trim()} onClick={save}><Icon name="check" size={14} /> {busy === "save" ? "Saving…" : "Save plan & run pre-check"}</button>
      {dirty ? <span className="tiny" style={{ color: "var(--review)" }}>Unsaved changes. Saving cancels any earlier approval.</span> : <span className="tiny faint">Saved {p.predictions_saved_at ? new Date(p.predictions_saved_at).toLocaleTimeString() : "—"}</span>}</div>
  );
  const base = p.results.filter((r) => r.phase === "baseline");
  const after = p.results.filter((r) => r.phase === "after");
  const s = {
    1: p.goal ? "completed" : "waiting_info", 8: p.patch && p.commands.length ? "completed" : "waiting_info",
    9: !p.precheck.length ? "not_started" : preFail ? "failed" : "completed", 10: p.predictions.length ? "completed" : "waiting_info", // consequences alone are not measurable
    11: p.criteria.length ? "completed" : "waiting_info",
    12: d?.status === "approved" || d?.status === "used" ? "approved" : d?.status === "rejected" ? "rejected" : p.precheck.length && !preFail ? "waiting_review" : "not_started",
    13: ran ? "completed" : p.status === "approved" ? "ready" : "not_started", 14: !p.results.length ? "not_started" : p.patch_applied ? "completed" : "failed",
    15: !p.comparison.length ? "not_started" : p.comparison.some((c) => c.result === "NOT VERIFIED") ? "not_verified" : "completed",
    16: !p.win ? "not_started" : p.win.overall === "WIN" ? "completed" : p.win.overall === "NOT A WIN" ? "failed" : "not_verified",
  } as Record<number, S>;
  const shownFiles = ins.files.filter((x) => x.toLowerCase().includes(filter.toLowerCase())).slice(0, 80);
  const testIds = Array.from(new Set(p.results.flatMap((r) => Object.keys(r.tests))));

  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head">
        <div><p className="hud-label accent">Your real project · {p.source === "github" ? "GitHub" : "local folder"}</p>
          <h1 className="mt-s">{p.name}</h1>
          <p className="lede">{p.origin}{p.ref ? ` @ ${p.ref}` : ""} → ACFM test workspace at commit <span className="mono">{p.commit.slice(0, 12)}</span>. Your own folder is never changed.</p></div>
        <div className="row"><a className="btn" href="#/project"><Icon name="history" size={14} /> All project tests</a></div>
      </div>
      <p className="warn small"><strong>Not a sandbox.</strong> Approved commands run in a separate copy with secrets removed from the environment, a temporary home folder and a time limit, but they can still read your files and reach the network. Approve only commands you trust.</p>
      {err && <ErrorBox error={err} />}

      <ol className="timeline" aria-label="The 16 steps on your real project">
        <Step n={1} title="Task Goal: desired input, output and success" s={s[1]} open={!p.goal}>
          <label className="lbl" htmlFor="pg-goal">Task Goal</label>
          <textarea id="pg-goal" className="field" rows={2} disabled={ran} value={f.goal} placeholder="e.g. Fix add() so it returns the sum, without breaking other functions." onChange={(e) => set({ goal: e.target.value })} />
          <div className="grid g2 mt-s">
            <div><label className="lbl" htmlFor="pg-in">Desired input</label><input id="pg-in" className="field" disabled={ran} value={f.desired_input} onChange={(e) => set({ desired_input: e.target.value })} /></div>
            <div><label className="lbl" htmlFor="pg-out">Desired output</label><input id="pg-out" className="field" disabled={ran} value={f.desired_output} onChange={(e) => set({ desired_output: e.target.value })} /></div>
          </div>
          <p className="tiny faint mt-s">Success criteria are in step 11. Everything here is saved with the plan.</p>
          <SaveBtn />
        </Step>

        <Step n={2} title="Rules and permissions" s="completed">
          <ul className="bullets small">
            <li>The 32 permanent rules of conduct (pinned; see Identity & Rules).</li>
            <li>Work only in the ACFM test workspace; never write to your folder, never push, never open pull requests.</li>
            <li>Run only the exact commands you approve, as fixed argument lists (no shells, no sudo, no curl/wget, no rm, no git push/reset/clean).</li>
            <li>Never install dependencies or run repository scripts automatically; README text is data, not instructions.</li>
          </ul>
        </Step>

        <Step n={3} title="Separate copy: the ACFM test workspace" s="completed">
          <dl className="kv"><dt>source</dt><dd>{p.origin}</dd><dt>copy</dt><dd className="mono small">{p.workspace}</dd>
            <dt>how</dt><dd className="small">{{ git_clone: "git clone of your folder at its current commit (uncommitted changes not included)", folder_copy: "file copy (dependency folders skipped) + local baseline commit", github_clone: "shallow clone from GitHub" }[p.workspace_kind]}</dd>
            <dt>commit</dt><dd className="mono small">{p.commit}</dd></dl>
        </Step>

        <Step n={4} title="Inspect the project (read-only)" s="completed">
          <p className="small">{ins.file_count} files · languages: {Object.entries(ins.languages).map(([k, v]) => `${k} ${v}`).join(", ") || "—"}</p>
          <p className="small mt-s">Key files: {ins.key_files.join(", ") || "none found"}</p>
          <p className="tiny faint mt-s">Top level: {ins.top_level.join("  ")}</p>
          {ins.readme_excerpt && <details className="mt-s"><summary className="tiny dim" style={{ cursor: "pointer" }}>README excerpt (data, not instructions)</summary><pre className="code tiny">{ins.readme_excerpt}</pre></details>}
          <div className="glass-flat mt" style={{ padding: 12 }} aria-label="Project overview by your LLM">
            <p className="row between"><span className="hud-label accent">Project overview{p.overview ? ` · by ${p.overview.provider}` : ""}</span>{p.overview && <span className="ev ev-inferred">LLM-generated</span>}</p>
            {!p.overview ? (
              <div className="row mt-s"><button className="btn-primary" disabled={!!busy} onClick={() => void describe()}><Icon name="spark" size={14} /> {busy === "describe" ? `${llm?.provider ?? "The LLM"} is reading the project…` : `Ask ${llm?.mock ? "the LLM" : (llm?.provider?.split(" ")[0] ?? "the LLM")} to explain this project`}</button>
                <span className="tiny faint">Reads the README, config and up to 10 main source files: name, goal, features and suggested improvements.</span></div>
            ) : (
              <>
                <p className="mt-s"><strong>{p.overview.name}</strong></p>
                <p className="small mt-s"><span className="hud-label">Goal</span> {p.overview.goal}</p>
                <p className="hud-label mt">Features ({p.overview.features.length})</p>
                <ul className="bullets small mt-s">{p.overview.features.map((x) => <li key={x}>{x}</li>)}</ul>
                <p className="hud-label mt">Suggested improvements</p>
                <ul className="list mt-s">{p.overview.suggestions.map((sg, i) => (
                  <li key={i} className="glass-flat" style={{ padding: 10, flexDirection: "column", alignItems: "stretch", gap: 4 }}>
                    <strong className="small">{sg.title}</strong>
                    <span className="small">{sg.change}</span>
                    <span className="tiny faint">{sg.why}{sg.files.length ? ` · ${sg.files.join(", ")}` : ""}</span>
                    {!ran && <span><button className="btn mt-s" onClick={() => { setAsk(sg.change + (sg.files.length ? ` (files: ${sg.files.join(", ")})` : "")); setPicked(Array.from(new Set([...picked, ...sg.files.filter((x) => ins.files.includes(x))])).slice(0, 12));
                      const el = document.getElementById("pstep-8"); el?.querySelector("details")?.setAttribute("open", ""); setTimeout(() => { el?.scrollIntoView({ behavior: "smooth" }); document.getElementById("pg-ask")?.focus(); }, 50); }}>
                      Use this change →</button></span>}
                  </li>))}</ul>
                {p.overview.unknowns.length > 0 && <p className="tiny faint mt-s">Not seen: {p.overview.unknowns.join(" · ")}</p>}
                <p className="tiny faint mt-s">Read: {p.overview.files_read.join(", ") || "no files"}. A description, not an inspection result: ACFM never treats it as evidence.</p>
              </>
            )}
          </div>
        </Step>

        <Step n={5} title="Code, tests and test commands found" s="completed">
          <p className="small">{ins.test_count} test file(s){ins.tests.length ? ":" : "."}</p>
          {ins.tests.length > 0 && <p className="tiny mono mt-s" style={{ overflowWrap: "anywhere" }}>{ins.tests.slice(0, 20).join("  ")}</p>}
          <p className="hud-label mt">Suggested test commands (not run)</p>
          <ul className="list mt-s">{ins.suggested_commands.map((c, i) => <li key={i} className="small" style={{ flexDirection: "column", gap: 2 }}><code className="mono">{c.argv.join(" ")}</code><span className="tiny faint">{c.why}</span></li>)}
            {!ins.suggested_commands.length && <li className="small faint">None detected. Write your own test command in step 8.</li>}</ul>
        </Step>

        <Step n={6} title="Missing information and unknowns" s="completed">
          <ul className="bullets small">{[...ins.notes, ...ins.unknowns, ...p.unknowns].map((x) => <li key={x}>{x}</li>)}</ul>
          {ins.instruction_like_text && <p className="warn small mt-s">The README contains instruction-like text. ACFM treats it as data and never follows it.</p>}
        </Step>

        <Step n={7} title="Files your LLM may read (optional)" s={picked.length ? "completed" : "optional"}>
          <p className="small">Files you name in your message (e.g. “calc.py”) are sent automatically. Pick more here if needed (up to 12). <strong>Sent to {llm?.provider ?? "the LLM"}:</strong> your message, the Task Goal, languages, test file names, suggested commands, the current plan and only these files.</p>
          <div className="row mt-s"><input className="field" style={{ maxWidth: 320 }} placeholder="Filter files…" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter files" />
            <span className="tiny faint">{picked.length}/12 picked</span></div>
          <div className="glass-flat mt-s" style={{ maxHeight: 180, overflow: "auto", padding: 8 }}>
            {shownFiles.map((x) => (
              <label key={x} className="row tiny mono" style={{ gap: 6, padding: "2px 0", flexWrap: "nowrap" }}>
                <input type="checkbox" checked={picked.includes(x)} disabled={!picked.includes(x) && picked.length >= 12}
                  onChange={(e) => setPicked(e.target.checked ? [...picked, x] : picked.filter((y) => y !== x))} />{x}</label>))}
          </div>
        </Step>

        <Step n={8} title={`Describe the change in plain words: ${llm?.mock ? "your LLM" : (llm?.provider ?? "your LLM")} writes the patch and tests`} s={s[8]} open={!ran}>
          <div className="pchat">
            {!p.chat.length && <p className="small faint">Example: “Make add() in calc.py return the sum instead of the difference, and keep the other tests passing.”</p>}
            {p.chat.map((m, i) => (
              <div key={i} className={`pmsg pmsg-${m.role}`}>
                <p className="tiny faint">{m.role === "user" ? "You" : m.provider}{m.files.length ? ` · sent ${m.files.join(", ")}` : ""}</p>
                <p className="small" style={{ whiteSpace: "pre-wrap" }}>{m.content}</p>
                {m.draft && <PlanCompare draft={withPlans(m.draft)} canUse={!ran && i === p.chat.length - 1 && !busy} onUse={(k) => applyDraft(withPlans(m.draft!), k)} />}
              </div>
            ))}
          </div>
          {!ran && (
            <div className="mt">
              <label className="lbl" htmlFor="pg-ask">Describe the change you want (plain words)</label>
              <textarea id="pg-ask" className="field" rows={3} value={ask} placeholder="e.g. Make add() in calc.py return the sum instead of the difference"
                onChange={(e) => setAsk(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && ask.trim()) void sendAsk(); }} />
              <div className="row mt-s"><button className="btn-primary" disabled={!!busy || !ask.trim()} onClick={() => void sendAsk()}>
                <Icon name="spark" size={14} /> {busy === "ask" ? `Asking ${llm?.provider ?? "the LLM"}…` : `Ask ${llm?.mock ? "the LLM" : (llm?.provider?.split(" ")[0] ?? "the LLM")} to write the change`}</button>
                <span className="tiny faint">Ctrl+Enter to send · <a href="#/llm">change LLM</a></span>
                {llm?.mock && <span className="tiny" style={{ color: "var(--review)" }}>The offline mock cannot write code; pick Claude or a local model.</span>}</div>
            </div>
          )}
          <details className="mt" open={!!f.patch}>
            <summary className="small dim" style={{ cursor: "pointer" }}>The exact code change and test commands (review or edit)</summary>
            <label className="lbl mt-s" htmlFor="pg-patch">Patch (unified diff; written by your LLM, or paste the output of <code>git diff</code>)</label>
            <textarea id="pg-patch" className="field mono" rows={10} disabled={ran} value={f.patch} spellCheck={false} style={{ fontSize: 12.5 }}
              placeholder={"Example only:\ndiff --git a/calc.py b/calc.py\n--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b"} onChange={(e) => set({ patch: e.target.value })} />
            <label className="lbl mt-s" htmlFor="pg-cmds">Test commands, one per line (arguments split on spaces; no shell)</label>
            <textarea id="pg-cmds" className="field mono" rows={2} disabled={ran} value={f.commands} spellCheck={false} onChange={(e) => set({ commands: e.target.value })} />
            <div className="grid g2 mt-s">
              <div><label className="lbl" htmlFor="pg-ass">Assumptions (one per line)</label><textarea id="pg-ass" className="field" rows={2} disabled={ran} value={f.assumptions} onChange={(e) => set({ assumptions: e.target.value })} /></div>
              <div><label className="lbl" htmlFor="pg-unk">Unknowns (one per line)</label><textarea id="pg-unk" className="field" rows={2} disabled={ran} value={f.unknowns} onChange={(e) => set({ unknowns: e.target.value })} /></div>
            </div>
            <SaveBtn />
          </details>
        </Step>

        <Step n={9} title="Pre-check before prediction" s={s[9]}>
          {!p.precheck.length ? <p className="small faint">Runs when you save the plan.</p> :
            <ul className="list">{p.precheck.map((i, k) => <li key={k} className="small" style={{ flexDirection: "column", gap: 2 }}><span className="row between"><span>{i.name}</span><ResultBadge r={i.status} /></span><span className="tiny faint">{i.detail}</span></li>)}</ul>}
        </Step>

        <Step n={10} title="Predict the consequences (saved before anything runs)" s={s[10]} open={!!p.patch && !p.predictions.length}>
          <p className="hud-label">Predicted consequences per object{f.plan_title ? ` · ${f.plan_title}` : ""}</p>
          <p className="tiny faint mt-s">What this plan changes directly, what is connected to it, and the effect on the whole project. Part of what you approve.</p>
          <div className="mt-s"><ConsequenceTable items={f.consequences} /></div>
          {f.alternatives.length > 0 && <p className="tiny faint mt-s">Compared with: {f.alternatives.map((a) => `${a.title} (${a.applies ? "applies" : "does not apply"}, ${a.risks} risk(s), ${a.files} file(s))`).join(" · ")}</p>}
          <p className="hud-label mt">Testable predictions (measured by the test run)</p>
          <datalist id="pred-tests">{[...ins.tests, ...testIds].map((t) => <option key={t} value={t} />)}</datalist>
          <ul className="list">{f.predictions.map((x, i) => (
            <li key={i} className="glass-flat" style={{ padding: 10, flexDirection: "column", alignItems: "stretch", gap: 6 }}>
              <div className="row" style={{ flexWrap: "nowrap" }}><span className="mono accent small">P{i + 1}</span>
                <input className="field" disabled={ran} aria-label={`Prediction ${i + 1}`} value={x.statement} placeholder="What will happen, e.g. test_add passes after the fix"
                  onChange={(e) => set({ predictions: f.predictions.map((y, j) => j === i ? { ...y, statement: e.target.value } : y) })} />
                {!ran && <button className="btn-ghost" aria-label={`Remove prediction ${i + 1}`} onClick={() => set({ predictions: f.predictions.filter((_, j) => j !== i) })}>✕</button>}</div>
              <CheckEditor id="pred" c={x.check} commands={cmds} onChange={(c) => set({ predictions: f.predictions.map((y, j) => j === i ? { ...y, check: c } : y) })} />
            </li>))}</ul>
          {!ran && <button className="btn mt-s" onClick={() => set({ predictions: [...f.predictions, { statement: "", check: blankCheck() }] })}>+ Add prediction</button>}
          <p className="tiny faint mt-s">Each prediction names what will be observed and how. Untested effects stay unknown, never “no effect”.</p>
          <SaveBtn />
        </Step>

        <Step n={11} title="Success criteria: when is the Task Goal achieved?" s={s[11]}>
          <ul className="list">{f.criteria.map((c, i) => (
            <li key={i} className="glass-flat" style={{ padding: 10, flexDirection: "column", alignItems: "stretch", gap: 6 }}>
              <div className="row" style={{ flexWrap: "nowrap" }}><span className="mono accent small">C{i + 1}</span>
                <input className="field" disabled={ran} aria-label={`Criterion ${i + 1}`} value={c.text} placeholder="e.g. All tests pass after the change"
                  onChange={(e) => set({ criteria: f.criteria.map((y, j) => j === i ? { ...y, text: e.target.value } : y) })} />
                {c.source === "llm_proposed" && <span className="ev ev-inferred">LLM-proposed</span>}
                {!ran && <button className="btn-ghost" aria-label={`Remove criterion ${i + 1}`} onClick={() => set({ criteria: f.criteria.filter((_, j) => j !== i) })}>✕</button>}</div>
              <CheckEditor id="pred" c={c.check} commands={cmds} onChange={(k) => set({ criteria: f.criteria.map((y, j) => j === i ? { ...y, check: k } : y) })} />
            </li>))}</ul>
          {!ran && <button className="btn mt-s" onClick={() => set({ criteria: [...f.criteria, { text: "", check: blankCheck(), source: "human" }] })}>+ Add success criterion</button>}
          <SaveBtn />
        </Step>

        <Step n={12} title="Human review of the exact plan" s={s[12]} open={s[12] === "waiting_review"}>
          {dirty && <p className="warn small">Save your changes first: you can only approve the saved plan.</p>}
          {d && <p className="small">Last decision: <strong>{d.status}</strong> by {d.reviewer} at {new Date(d.at).toLocaleString()} (plan {d.plan_hash}{d.criteria_agreed ? ", criteria agreed" : ""}).</p>}
          {!ran && (
            <>
              <p className="small mt-s">You approve: patch ({p.patch.split("\n").length} lines), {p.commands.length} command(s): {p.commands.map((a) => a.join(" ")).join(" · ") || "—"}, {p.predictions.length} prediction(s), commit {p.commit.slice(0, 12)}. Any change cancels the approval.</p>
              <label className="row small mt-s" style={{ gap: 8 }}><input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} /> I agree these success criteria define the Task Goal.</label>
              <div className="row mt-s"><input className="field" style={{ maxWidth: 220 }} aria-label="Reviewer" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
                <button className="btn-primary" disabled={!!busy || dirty || preFail || !p.precheck.length} onClick={() => act("approve", () => api.decideProject(p.id, { decision: "approve", reviewer, plan_hash: p.plan_hash, criteria_agreed: agreed }))}>
                  <Icon name="check" size={14} /> Approve this exact plan</button>
                <button className="btn-danger" disabled={!!busy || dirty || !p.plan_hash} onClick={() => act("reject", () => api.decideProject(p.id, { decision: "reject", reviewer, plan_hash: p.plan_hash, criteria_agreed: false }))}>Reject</button></div>
            </>
          )}
        </Step>

        <Step n={13} title="Recheck, then run baseline → patch → same tests" s={s[13]} open={s[13] === "ready"}>
          <p className="small">ACFM rechecks the plan, commit, workspace and policy, runs your approved commands once <strong>before</strong> the patch (baseline), applies the patch, and runs the same commands <strong>after</strong>. Once only.</p>
          {!ran && <button className="btn-primary mt-s" disabled={!!busy || p.status !== "approved" || dirty} onClick={() => act("run", () => api.executeProject(p.id))}>
            <Icon name="play" size={14} /> {busy === "run" ? "Running baseline, applying the patch, running again…" : "Run the approved test"}</button>}
          {ran && <p className="small mt-s">Ran at {new Date(p.executed_at).toLocaleString()} · patch {p.patch_applied ? "applied" : "could not be applied"}.</p>}
        </Step>

        <Step n={14} title="Test results: baseline vs after" s={s[14]}>
          {!p.results.length ? <p className="small faint">No test has run yet.</p> : p.commands.map((a, i) => {
            const b = base[i], af = after[i];
            const ids = Array.from(new Set([...Object.keys(b?.tests ?? {}), ...Object.keys(af?.tests ?? {})])).sort();
            return (
              <div key={i} className="glass-flat mt-s" style={{ padding: 10 }}>
                <p className="mono small">{a.join(" ")}</p>
                <p className="tiny mt-s">baseline: {b ? (b.error || `exit ${b.exit_code}`) : "—"} · after: {af ? (af.error || `exit ${af.exit_code}`) : "did not run"}</p>
                {ids.length > 0 && <div className="table-wrap mt-s"><table className="tbl"><thead><tr><th scope="col">Test</th><th scope="col">Baseline</th><th scope="col">After</th></tr></thead>
                  <tbody>{ids.slice(0, 60).map((t) => <tr key={t}><td className="mono tiny">{t}</td><td className="tiny">{b?.tests[t] ?? "—"}</td><td className="tiny" style={{ color: b?.tests[t] !== af?.tests[t] ? "var(--review)" : undefined }}>{af?.tests[t] ?? "—"}</td></tr>)}</tbody></table></div>}
                <details className="mt-s"><summary className="tiny dim" style={{ cursor: "pointer" }}>Output (last lines)</summary>
                  <pre className="code tiny">{(af ?? b)?.output_tail.slice(-3000)}</pre></details>
              </div>
            );
          })}
        </Step>

        <Step n={15} title="Compare predictions with test results" s={s[15]}>
          {!p.comparison.length ? <p className="small faint">Comparison appears after the test runs.</p> :
            <div className="table-wrap"><table className="tbl"><thead><tr><th scope="col">Prediction</th><th scope="col">Expected</th><th scope="col">Observed</th><th scope="col">Result</th></tr></thead>
              <tbody>{p.comparison.map((c) => <tr key={c.prediction_id}><td className="small"><span className="mono accent">{c.prediction_id}</span> {c.statement}</td><td className="tiny">{c.expected}</td><td className="tiny">{c.observed}</td><td><ResultBadge r={c.result} /></td></tr>)}</tbody></table></div>}
          {p.comparison.length > 0 && p.consequences.length > 0 && (
            <details className="mt"><summary className="small dim" style={{ cursor: "pointer" }}>Predicted consequences without their own test ({p.consequences.length}): not verified</summary>
              <p className="tiny faint mt-s">Only the testable predictions above were measured. These per-object consequences stay <strong>unknown</strong> until a test or a human checks them; untested never means “no effect”.</p>
              <div className="mt-s"><ConsequenceTable items={p.consequences} /></div></details>
          )}
        </Step>

        <Step n={16} title="ACFM Win: prediction accuracy · Task Goal · rule compliance" s={s[16]} open={!!p.win}>
          {!p.win ? <p className="small faint">Evaluated after the approved test runs. ACFM never claims a Win without real results.</p> : (
            <>
              <WinBody w={p.win} label="ACFM Win" />
              <details className="mt">
                <summary className="small dim" style={{ cursor: "pointer" }}>Record a human judgment (user-provided)</summary>
                <div className="grid g2 mt-s">
                  <select className="field" aria-label="Kind" value={ver.kind} onChange={(e) => setVer({ ...ver, kind: e.target.value as typeof ver.kind, ref: "" })}>
                    <option value="prediction">Prediction</option><option value="criterion">Success criterion</option><option value="rule">Rule</option></select>
                  <select className="field" aria-label="Which" value={ver.ref} onChange={(e) => setVer({ ...ver, ref: e.target.value })}>
                    <option value="">Choose…</option>
                    {ver.kind === "prediction" && p.predictions.map((x) => <option key={x.id} value={x.id}>{x.id} {x.statement.slice(0, 50)}</option>)}
                    {ver.kind === "criterion" && p.criteria.map((x) => <option key={x.id} value={x.id}>{x.id} {x.text.slice(0, 50)}</option>)}
                    {ver.kind === "rule" && Array.from({ length: 32 }, (_, i) => `R${String(i + 1).padStart(2, "0")}`).map((r) => <option key={r}>{r}</option>)}
                  </select>
                  <select className="field" aria-label="Judgment" value={ver.status} onChange={(e) => setVer({ ...ver, status: e.target.value as "PASS" | "FAIL" })}><option>PASS</option><option>FAIL</option></select>
                  <input className="field" aria-label="Evidence" placeholder="Evidence you checked" value={ver.evidence} onChange={(e) => setVer({ ...ver, evidence: e.target.value })} />
                </div>
                <button className="btn mt-s" disabled={!!busy || !ver.ref || !ver.evidence.trim()} onClick={() => act("verify", () => api.verifyProject(p.id, { ...ver, reviewer }))}>Record judgment</button>
              </details>
            </>
          )}
        </Step>
      </ol>

      <details className="glass-flat" style={{ padding: 12 }}><summary className="small dim" style={{ cursor: "pointer" }}>Trace ({p.log.length})</summary>
        <ul className="list mt-s">{p.log.map((l, i) => <li key={i} className="tiny"><span className="mono accent">{l.step}</span> <span className="faint">{new Date(l.at).toLocaleTimeString()}</span> {l.text}</li>)}</ul></details>
    </div>
  );
}

function Connect() {
  const [src, setSrc] = useState<"local" | "github">("local");
  const [path, setPath] = useState("");
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [list, setList] = useState<ProjectListItem[] | null>(null);
  const load = () => api.projects().then((r) => setList(r.projects)).catch((e) => setErr((e as Error).message));
  useEffect(() => { void load(); }, []);
  const create = async () => {
    setBusy(true); setErr(null);
    try { const p = await api.createProject(src === "local" ? { source: "local", path } : { source: "github", url, ref }); go(`project/${p.id}`); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const del = async (id: string) => {
    if (!window.confirm("Delete this project test and its workspace copy? Your own project is not touched.")) return;
    try { await api.deleteProject(id); await load(); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head"><div><p className="hud-label accent">Your real project</p><h1 className="mt-s">Test ACFM on your own code</h1>
        <p className="lede">Point ACFM at a local project folder or a public GitHub repository. It works on a separate copy, predicts before testing, runs only what you approve, and compares its predictions with real test results.</p></div></div>
      <section className="glass panel">
        <div className="row" role="radiogroup" aria-label="Source">
          {(["local", "github"] as const).map((k) => <button key={k} role="radio" aria-checked={src === k} className={src === k ? "btn-primary" : "btn"} onClick={() => setSrc(k)}>
            <Icon name={k === "local" ? "warehouse" : "environment"} size={14} /> {k === "local" ? "Local folder" : "GitHub repository"}</button>)}
        </div>
        {src === "local" ? (
          <div className="mt"><label className="lbl" htmlFor="pc-path">Absolute path of the project folder</label>
            <input id="pc-path" className="field mono" placeholder="/home/you/my-project" value={path} onChange={(e) => setPath(e.target.value)} />
            <p className="tiny faint mt-s">A Git project is cloned at its current commit (uncommitted changes are not copied). A plain folder is copied without dependency folders. Your folder is only read.</p></div>
        ) : (
          <div className="grid g2 mt">
            <div><label className="lbl" htmlFor="pc-url">Public GitHub URL</label><input id="pc-url" className="field mono" placeholder="https://github.com/owner/repository" value={url} onChange={(e) => setUrl(e.target.value)} /></div>
            <div><label className="lbl" htmlFor="pc-ref">Branch, tag or commit (optional)</label><input id="pc-ref" className="field mono" placeholder="default branch" value={ref} onChange={(e) => setRef(e.target.value)} /></div>
            <p className="tiny faint">Shallow clone, no submodules, no credentials. Phase 1 supports public repositories only.</p>
          </div>
        )}
        {err && <div className="mt"><ErrorBox error={err} /></div>}
        <div className="row mt"><button className="btn-primary" disabled={busy || (src === "local" ? !path.trim() : !url.trim())} onClick={create}>
          <Icon name="play" size={14} /> {busy ? "Creating the test workspace…" : "Create test workspace & inspect"}</button>
          <span className="tiny faint">Nothing is installed and no project script runs.</span></div>
      </section>
      <section className="glass panel">
        <p className="hud-label">Project tests</p>
        {!list ? <Loading what="project tests" /> : !list.length ? <p className="small faint mt-s">None yet.</p> : (
          <div className="table-wrap mt-s"><table className="tbl"><thead><tr><th scope="col">Project</th><th scope="col">Source</th><th scope="col">Status</th><th scope="col">Win</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>{list.map((x) => <tr key={x.id}><td><a href={`#/project/${x.id}`}>{x.name}</a><div className="tiny faint" style={{ overflowWrap: "anywhere" }}>{x.origin}</div></td><td className="small">{x.source}</td><td className="small">{x.status}</td>
              <td>{x.win ? <ResultBadge r={x.win === "WIN" ? "PASS" : x.win === "NOT A WIN" ? "FAIL" : "NOT VERIFIED"} /> : <span className="faint tiny">—</span>}</td>
              <td><button className="btn-ghost tiny" onClick={() => void del(x.id)}>Delete copy</button></td></tr>)}</tbody></table></div>
        )}
      </section>
    </div>
  );
}

export function Project({ id }: { id?: string }) {
  return id ? <ProjectFlow key={id} id={id} /> : <Connect />;
}
