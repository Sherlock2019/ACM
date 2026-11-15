import { useCallback, useEffect, useState } from "react";
import { ChatPanel } from "../components/ChatPanel";
import { Icon } from "../components/icons";
import { ConnectionBadge, EnforcementBadge, ErrorBox, Panel, PermissionBadge, Plain, fmtTime } from "../components/ui";
import { api } from "../services/api";
import { go, useAFM } from "../state";
import type { PrepareResult, UseCase, UseCaseFields, UseCaseListItem, UseCaseSummary } from "../types/afm";

const ROLES = ["Cloud infrastructure assistant", "SAP business process assistant", "Python application engineer", "Mobile application assistant", "Data readiness reviewer", "Calculator assistant"];
const ENV_TYPES = ["Simulated environment", "Python application or repository", "AWS infrastructure", "SAP system", "Mobile application", "Web server", "Business system", "Spreadsheet", "Calculator"];
const EXAMPLES: { title: string; fields: Partial<UseCaseFields> }[] = [
  { title: "Generic Object Playground", fields: { role: "Teaching assistant", purpose: "Show how one change flows through connected objects.", environment_type: "Simulated environment", environment_name: "Generic Object Playground", adapter_id: "object-playground", target_name: "Object A (Input)", target_type: "input", goal_outcome: "Change Object A's value to 10 and show me what will happen." } },
  { title: "Web Application Port Change", fields: { role: "Python application engineer", purpose: "Change configuration without breaking access.", environment_type: "Simulated environment", environment_name: "Web application port change", adapter_id: "webapp-demo", target_name: "Python application", target_type: "python_application", proposed_action: "Change the listening port from 8000 to 9000", goal_outcome: "Change the application to port 9000 while keeping it accessible.", constraints: "Do not delete data. Ask me before making changes." } },
  { title: "Inventory Assistant", fields: { role: "Inventory assistant", purpose: "Fulfil orders without hurting other orders.", environment_type: "Simulated environment", environment_name: "Inventory Assistant", adapter_id: "warehouse-demo", target_name: "Order A", target_type: "customer_order", goal_outcome: "Fulfill Order A while avoiding a shortage for Order B." } },
  { title: "Data Readiness Agent", fields: { role: "Data readiness reviewer", purpose: "Check whether a dataset is ready for use.", environment_type: "Business system", environment_name: "Data readiness agent (separate project)", target_name: "Dataset", goal_outcome: "Assess whether the dataset is ready." } },
];

function Field({ id, label, value, onChange, area = false, hint, list }: { id: string; label: string; value: string; onChange: (v: string) => void; area?: boolean; hint?: string; list?: string }) {
  return (
    <div>
      <label className="lbl" htmlFor={id}>{label}</label>
      {area ? <textarea id={id} className="field" rows={2} value={value} onChange={(e) => onChange(e.target.value)} aria-describedby={hint ? `${id}-h` : undefined} />
        : <input id={id} className="field" value={value} onChange={(e) => onChange(e.target.value)} list={list} aria-describedby={hint ? `${id}-h` : undefined} />}
      {hint && <p id={`${id}-h`} className="faint tiny mt-s">{hint}</p>}
    </div>
  );
}

export function Builder({ usecaseId }: { usecaseId?: string }) {
  const { envs, llm, refresh } = useAFM();
  const [list, setList] = useState<UseCaseListItem[]>([]);
  const [uc, setUc] = useState<UseCase | null>(null);
  const [f, setF] = useState<UseCaseFields | null>(null);
  const [rulesText, setRulesText] = useState("");
  const [title, setTitle] = useState("");
  const [sum, setSum] = useState<UseCaseSummary | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [prep, setPrep] = useState<PrepareResult | null>(null);

  const loadList = useCallback(() => api.usecases().then(setList).catch(() => {}), []);
  const adopt = useCallback(async (u: UseCase) => {
    setUc(u); setF(u.fields); setTitle(u.title); setRulesText(u.extra_rules.map((r) => r.text).join("\n"));
    setSum(await api.usecaseSummary(u.usecase_id).catch(() => null));
  }, []);
  useEffect(() => { void loadList(); }, [loadList]);
  useEffect(() => {
    setPrep(null);
    if (usecaseId) api.usecase(usecaseId).then(adopt).catch((e) => setErr(e.message));
    else { setUc(null); setF(null); setSum(null); }
  }, [usecaseId, adopt]);

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setErr(null);
    try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  const create = (fields?: Partial<UseCaseFields>, t?: string) => run("create", async () => {
    const u = await api.createUseCase(fields, t); await loadList(); go(`builder/${u.usecase_id}`);
  });
  const save = async () => {
    if (!uc || !f) return uc;
    const u = await api.updateUseCase(uc.usecase_id, { fields: f, extra_rules: rulesText.split("\n").map((s) => s.trim()).filter(Boolean), title });
    await adopt(u); await loadList(); return u;
  };
  const send = async (text: string) => {
    let ok = false;
    await run("chat", async () => {
      if (!uc || !text.trim()) return;
      await save();
      await adopt(await api.chat(uc.usecase_id, text.trim())); ok = true;
    });
    return ok;
  };
  const resolve = (i: number, d: "accept" | "dismiss", fields?: Record<string, string>) => run("proposal", async () => {
    if (!uc) return;
    await save();
    await adopt(await api.proposal(uc.usecase_id, i, d, fields));
  });
  const prepare = () => run("prepare", async () => {
    if (!uc) return;
    await save();
    const r = await api.prepare(uc.usecase_id); setPrep(r); await refresh();
  });
  const del = () => run("delete", async () => {
    if (!uc || !window.confirm(`Delete “${uc.title}” and its chat history?`)) return;
    await api.deleteUseCase(uc.usecase_id); await loadList(); go("builder");
  });
  const set = (k: keyof UseCaseFields) => (v: string) => setF((x) => (x ? { ...x, [k]: v } : x));

  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head">
        <div>
          <p className="hud-label accent">Create a use case</p>
          <h1 className="mt-s">Use-case builder</h1>
          <p className="lede">Describe the next AFM use case with the form, the chat, or both. AFM stays the decision-maker: the LLM only helps interpret and explain, and every proposal it makes waits for your acceptance.</p>
        </div>
        <span className="row"><span className={`ev ${llm?.mock ? "ev-configured" : "ev-inferred"}`}>Active provider: {llm?.mock ? "Mock (offline)" : llm?.provider}</span></span>
      </div>
      {err && <ErrorBox error={err} />}

      <Panel title="Saved use cases" right={<button className="btn-primary" onClick={() => create()} disabled={!!busy}><Icon name="spark" size={14} /> New use case</button>}>
        <div className="row">
          <span className="faint small">Start from an example:</span>
          {EXAMPLES.map((x) => <button key={x.title} className="chip" style={{ cursor: "pointer" }} onClick={() => create(x.fields, x.title)}>{x.title}</button>)}
        </div>
        {list.length > 0 && (
          <ul className="list mt">{list.map((u) => (
            <li key={u.usecase_id} className="between small">
              <a href={`#/builder/${u.usecase_id}`} aria-current={u.usecase_id === uc?.usecase_id ? "page" : undefined}>{u.title}</a>
              <span className="faint tiny">{u.adapter_id || u.environment_type || "no environment"} · {u.messages} messages · {u.runs} runs · {fmtTime(u.updated_at)}</span>
            </li>
          ))}</ul>
        )}
        <p className="faint tiny mt">Use cases and chat history are stored locally (SQLite). Saved chat history is not model training.</p>
      </Panel>

      {!uc || !f ? <Plain>Create a new use case or open a saved one to start. The four examples cover the three simulated playgrounds and one environment that is not connected.</Plain> : (
        <>
          <div className="split">
            <section className="glass panel stack" aria-label="Structured use-case form" style={{ gap: 14 }}>
              <div className="row between"><Field id="uc-title" label="Use-case title" value={title} onChange={setTitle} />
                <span className="row" style={{ alignSelf: "flex-end" }}><button className="btn" onClick={() => run("save", async () => { await save(); })} disabled={!!busy}>{busy === "save" ? "Saving…" : "Save"}</button><button className="btn-danger" onClick={del} disabled={!!busy}>Delete</button></span></div>

              <fieldset className="fs"><legend>A · AI agent role</legend>
                <div className="grid g2">
                  <Field id="uc-role" label="What role should AFM play in this use case?" value={f.role} onChange={set("role")} list="roles" />
                  <Field id="uc-purpose" label="Agent purpose (short)" value={f.purpose} onChange={set("purpose")} />
                </div>
                <datalist id="roles">{ROLES.map((r) => <option key={r} value={r} />)}</datalist>
                <p className="faint tiny mt-s">The role sets the task context. It cannot change AFM's identity, rules of conduct, permissions or approval requirements.</p>
              </fieldset>

              <fieldset className="fs"><legend>B · Good-behavior rules</legend>
                <details><summary className="small" style={{ cursor: "pointer" }}>{sum?.global_rules.length ?? 32} global rules of conduct loaded automatically · <span className="mono">{uc.rules_version}</span></summary>
                  <ul className="list mt-s" style={{ maxHeight: 260, overflowY: "auto" }}>{sum?.global_rules.map((r) => (
                    <li key={r.id} className="small" style={{ flexWrap: "nowrap" }}><span className="mono accent">{r.id}</span><span style={{ flex: 1 }}>{r.title}</span><EnforcementBadge e={r.enforcement} /></li>
                  ))}</ul></details>
                <div className="mt"><label className="lbl" htmlFor="uc-rules">Additional use-case rules (one per line)</label>
                  <textarea id="uc-rules" className="field" rows={3} value={rulesText} onChange={(e) => setRulesText(e.target.value)} placeholder={"Do not delete customer records\nDo not change the health monitor"} aria-describedby="uc-rules-h" />
                  <p id="uc-rules-h" className="faint tiny mt-s">Extra rules may only narrow permissions. A rule that names a tool or object type of the selected adapter blocks that tool. Others are recorded but not automatically checked. Rules that weaken global rules are conflicts.</p></div>
                {uc.extra_rules.length > 0 && <ul className="list mt-s">{uc.extra_rules.map((r) => (
                  <li key={r.text} className="small" style={{ flexDirection: "column", alignItems: "stretch", gap: 2 }}>
                    <span className="row between"><span>{r.text}</span>
                      <span className={`badge ${r.status === "enforced" ? "st-pass" : r.status === "conflict" ? "st-fail" : "st-unknown"}`}><span className="ico" aria-hidden="true">{r.status === "enforced" ? "✓" : r.status === "conflict" ? "✕" : "?"}</span>{r.status}</span></span>
                    <span className="faint tiny">{r.explanation}</span>
                  </li>
                ))}</ul>}
              </fieldset>

              <fieldset className="fs"><legend>C · Environment</legend>
                <div className="grid g2">
                  <Field id="uc-envtype" label="What environment will AFM work in?" value={f.environment_type} onChange={set("environment_type")} list="envtypes" />
                  <Field id="uc-envname" label="Environment name" value={f.environment_name} onChange={set("environment_name")} />
                </div>
                <datalist id="envtypes">{ENV_TYPES.map((r) => <option key={r} value={r} />)}</datalist>
                <div className="mt"><Field id="uc-envdesc" label="Description or relevant context" value={f.environment_description} onChange={set("environment_description")} area /></div>
                <div className="grid g2 mt">
                  <div><label className="lbl" htmlFor="uc-adapter">Adapter</label>
                    <select id="uc-adapter" className="field" value={f.adapter_id} onChange={(e) => set("adapter_id")(e.target.value)}>
                      <option value="">None (not connected)</option>
                      {envs.map((x) => <option key={x.environment_id} value={x.environment_id}>{x.name} (simulated)</option>)}
                    </select></div>
                  <div><p className="lbl">Connection status</p>{sum && <span className="row"><ConnectionBadge status={sum.environment.status} /><span className="faint tiny">{sum.environment.label}</span></span>}</div>
                </div>
                <p className="faint tiny mt-s">Describing an environment here or in chat never connects it. Only registered adapters can be inspected or simulated.</p>
              </fieldset>

              <fieldset className="fs"><legend>D · Target object or system</legend>
                <div className="grid g2">
                  <Field id="uc-tname" label="What object or system should AFM assess?" value={f.target_name} onChange={set("target_name")} />
                  <Field id="uc-ttype" label="Object type" value={f.target_type} onChange={set("target_type")} />
                  <Field id="uc-tid" label="Identifier or path (optional)" value={f.target_identifier} onChange={set("target_identifier")} />
                  <Field id="uc-action" label="Proposed action or change (if known)" value={f.proposed_action} onChange={set("proposed_action")} />
                </div>
                <div className="mt"><Field id="uc-known" label="What do you currently know about it?" value={f.target_known_info} onChange={set("target_known_info")} area hint="Not verified until an authorized adapter inspects it." /></div>
              </fieldset>

              <fieldset className="fs"><legend>E · Task goal</legend>
                <Field id="uc-goal" label="What do you want to achieve?" value={f.goal_outcome} onChange={set("goal_outcome")} area />
                <div className="grid g2 mt">
                  <Field id="uc-crit" label="Success criteria (optional)" value={f.success_criteria} onChange={set("success_criteria")} />
                  <Field id="uc-cons" label="Constraints (optional)" value={f.constraints} onChange={set("constraints")} />
                </div>
                <div className="row mt" role="radiogroup" aria-label="Mode">
                  {(["plan", "analysis"] as const).map((m) => (
                    <label key={m} className="row small" style={{ gap: 6 }}><input type="radio" name="mode" checked={f.mode === m} onChange={() => setF({ ...f, mode: m })} />{m === "plan" ? "Propose an action plan" : "Analysis only"}</label>
                  ))}
                </div>
              </fieldset>

              <fieldset className="fs"><legend>F · Evidence & notes (untrusted input)</legend>
                <Field id="uc-evidence" label="Object descriptions, known dependencies, config snippets, links or paths" value={f.evidence} onChange={set("evidence")} area
                  hint="Treated as data that may need verification. Never as instructions that can override AFM's rules." />
              </fieldset>
            </section>

            <ChatPanel uc={uc} busy={busy === "chat"} onSend={send} onResolve={resolve}
              placeholder="Describe your use case in plain language, ask what AFM needs, or ask about an object type. Example: “You are a cloud infrastructure assistant. I want to stop an EC2 instance. What could happen?”" />
          </div>

          {sum && (
            <Panel title="Use-case summary" right={<button className="btn-primary btn-lg" onClick={prepare} disabled={!!busy}><Icon name="spark" size={15} /> {busy === "prepare" ? "Preparing…" : "Prepare assessment"}</button>}>
              <div className="grid g3">
                <div><p className="hud-label">Use case</p><dl className="kv mt-s">
                  <dt>role</dt><dd className="small">{sum.usecase.fields.role || "—"}</dd>
                  <dt>environment</dt><dd className="small">{sum.environment.name} <ConnectionBadge status={sum.environment.status} /></dd>
                  <dt>target</dt><dd className="small">{sum.usecase.fields.target_name || "—"}</dd>
                  <dt>goal</dt><dd className="small">{sum.usecase.fields.goal_outcome || "—"}</dd>
                  <dt>rules</dt><dd className="small mono">{sum.rules_version}{sum.rules_version !== sum.current_rules_version ? " (older than current)" : ""} + {sum.usecase.extra_rules.length} use-case</dd>
                </dl></div>
                <div><p className="hud-label">Tools & permissions</p>
                  {sum.tools.length ? <ul className="list mt-s">{sum.tools.filter((t) => t.scope === "environment").map((t) => <li key={t.name} className="between small"><span className="mono">{t.name}</span><PermissionBadge p={t.permission} /></li>)}</ul>
                    : <p className="faint small mt-s">No adapter: AFM has no tools for this environment.</p>}
                  {sum.objects.length > 0 && <p className="faint tiny mt">{sum.objects.length} known objects · {sum.relationship_count} relationships (simulated)</p>}</div>
                <div><p className="hud-label">Missing information</p>
                  {sum.missing.length ? <ul className="bullets mt-s">{sum.missing.map((m) => <li key={m}>{m}</li>)}</ul> : <p className="small mt-s" style={{ color: "var(--pass)" }}>Nothing essential missing.</p>}
                  {sum.conflicts.length > 0 && <div className="error-box mt">Rule conflict: {sum.conflicts.join("; ")}. Remove it to continue.</div>}</div>
              </div>
            </Panel>
          )}

          {prep && (
            <section className={prep.run ? "glass panel brackets" : "warn"} aria-live="polite">
              <p className="hud-label accent">Prepare assessment · {prep.status.replace(/_/g, " ")}</p>
              <p className="mt-s">{prep.message}</p>
              {prep.run && <div className="row mt"><a className="btn-primary" href={`#/assessment/${prep.run.run_id}`}><Icon name="spark" size={15} /> Open consequence assessment</a><span className="faint small">Recommended: {prep.run.recommendation?.plan_id ?? "none"}</span></div>}
              {!prep.run && prep.missing.length > 0 && <ul className="bullets mt-s">{prep.missing.map((m) => <li key={m}>{m}</li>)}</ul>}
              {prep.llm_explanation && (
                <div className="glass-flat mt" style={{ padding: 12 }}>
                  <span className="ev ev-inferred">General knowledge (LLM), not an inspection</span>
                  <p className="small mt-s">{prep.llm_explanation.explanation}</p>
                  <p className="small dim mt-s">{prep.llm_explanation.typical_behavior}</p>
                </div>
              )}
            </section>
          )}
          <Plain>Nothing you type here connects a system or changes anything. With a simulated adapter, “Prepare assessment” runs the normal AFM loop: predict, check rules, then ask for your review. Without one, AFM only lists what is missing.</Plain>
        </>
      )}
    </div>
  );
}
