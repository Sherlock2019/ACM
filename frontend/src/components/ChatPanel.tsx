import { Fragment, useEffect, useRef, useState } from "react";
import { useAFM } from "../state";
import type { ChatMessage, UseCase } from "../types/afm";
import { Icon } from "./icons";

export const FIELD_LABEL: Record<string, string> = {
  role: "Role", purpose: "Purpose", environment_type: "Environment type", environment_name: "Environment name", adapter_id: "Adapter",
  target_name: "Target name", target_type: "Target type", target_identifier: "Identifier / path", proposed_action: "Proposed action",
  goal_outcome: "Task goal (step 1)", desired_input: "Desired input (step 1)", desired_output: "Desired output (step 1)",
  success_criteria: "Success criteria (step 1)", constraints: "Constraints (step 1)", extra_rules: "Use-case rules (step 2)",
  ...Object.fromEntries(Array.from({ length: 16 }, (_, i) => [`step_${i + 1}`, `Step ${i + 1} note`])),
};
const LABELS: Record<string, [string, string]> = {
  llm_general: ["ev-inferred", "General knowledge (LLM)"], simulated: ["ev-configured", "Based on a simulated environment"],
  observed: ["ev-observed", "Observed adapter result"], prediction: ["ev-inferred", "Prediction / inference"], unknown: ["ev-unknown", "Unknown / unverified"],
};

function Proposal({ m, index, onResolve }: { m: ChatMessage; index: number; onResolve: (i: number, d: "accept" | "dismiss", f?: Record<string, string>) => void }) {
  const [edit, setEdit] = useState(false);
  const [vals, setVals] = useState(m.proposed_fields);
  if (m.proposal_status !== "pending") return Object.keys(m.proposed_fields).length ? <p className="faint tiny mt-s">Proposed fields {m.proposal_status}.</p> : null;
  return (
    <div className="proposal" role="group" aria-label="Proposed updates">
      <p className="hud-label" style={{ color: "var(--amber)" }}>Proposed updates · not applied yet</p>
      <dl className="kv mt-s">{Object.entries(vals).map(([k, v]) => (
        <Fragment key={k}><dt>{FIELD_LABEL[k] ?? k}</dt><dd>{edit
          ? (v.length > 60 || k.startsWith("step_") || k === "extra_rules"
            ? <textarea className="field" rows={2} aria-label={FIELD_LABEL[k] ?? k} value={v} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} />
            : <input className="field" aria-label={FIELD_LABEL[k] ?? k} value={v} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} />)
          : <span className="small" style={{ whiteSpace: "pre-wrap" }}>{v}</span>}</dd></Fragment>
      ))}</dl>
      <div className="row mt-s">
        <button className="btn-primary" onClick={() => onResolve(index, "accept", vals)}><Icon name="check" size={14} /> Accept{edit ? " edited" : ""}</button>
        {!edit && <button className="btn" onClick={() => setEdit(true)}>Edit</button>}
        <button className="btn-ghost" onClick={() => onResolve(index, "dismiss")}>Dismiss</button>
      </div>
    </div>
  );
}

export function ChatPanel({ uc, busy, onSend, onResolve, placeholder, compact = false }: {
  uc: UseCase; busy: boolean; onSend: (text: string) => Promise<boolean>;
  onResolve: (i: number, d: "accept" | "dismiss", f?: Record<string, string>) => void; placeholder?: string; compact?: boolean;
}) {
  const { llm } = useAFM();
  const [msg, setMsg] = useState("");
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }); }, [uc.messages.length]);
  const send = async () => { if (msg.trim() && (await onSend(msg.trim()))) setMsg(""); };
  return (
    <section className={`glass panel chat ${compact ? "chat-compact" : ""}`} aria-label="AFM chat">
      <div className="row between"><h2 className="hud-label accent">AFM chat · {llm?.mock ? "Mock (offline)" : llm?.provider}</h2><a href="#/llm" className="chip" style={{ cursor: "pointer" }}>Use your LLM model</a></div>
      <p className="faint tiny mt-s">{llm?.privacy} Suggestions are never applied until you accept them; Claude cannot change rules, permissions or approvals.</p>
      <div className="chat-log mt" ref={logRef} aria-live="polite">
        {uc.messages.length === 0 && <p className="faint small">{placeholder ?? "Describe your use case, ask what AFM needs, or ask about an object type."}</p>}
        {uc.messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "assistant" && <div className="row" style={{ gap: 6, marginBottom: 6 }}>{m.labels.map((l) => <span key={l} className={`ev ${LABELS[l]?.[0] ?? "ev-unknown"}`}>{LABELS[l]?.[1] ?? l}</span>)}<span className="faint tiny">{m.provider}</span></div>}
            <p style={{ whiteSpace: "pre-wrap" }}>{m.content}</p>
            {m.role === "assistant" && <Proposal m={m} index={i} onResolve={onResolve} />}
            {m.role === "assistant" && m.suggested_questions.length > 0 && i === uc.messages.length - 1 && (
              <div className="row mt-s">{m.suggested_questions.map((q) => <button key={q} className="chip" style={{ cursor: "pointer" }} onClick={() => setMsg(q.replace(/\?$/, ": "))}>{q}</button>)}</div>
            )}
          </div>
        ))}
        {busy && <p className="faint small">AFM is asking the LLM tool…</p>}
      </div>
      <form className="row mt" style={{ flexWrap: "nowrap" }} onSubmit={(e) => { e.preventDefault(); void send(); }}>
        <label htmlFor="chat-in" className="sr-only">Message</label>
        <textarea id="chat-in" className="field" rows={2} value={msg} onChange={(e) => setMsg(e.target.value)} maxLength={2000}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }} placeholder="Message AFM… (Enter to send)" />
        <button className="btn-primary" disabled={busy || !msg.trim()}>{busy ? "…" : "Send"}</button>
      </form>
    </section>
  );
}
