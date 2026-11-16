// "Who feels this problem?": pick a role, read the question they face, and watch ACFM's answer type out.
// Rotates on its own until the visitor picks a role; reduced motion shows the answer at once.
import { useEffect, useState } from "react";

const PERSONAS = [
  { id: "cto", chip: "CTO", q: "As a CTO, would you let an AI agent change production if you couldn't see what it might break?",
    a: "ACFM shows every object a change touches, and what happens to each one, before anyone approves it." },
  { id: "sre", chip: "SRE / DevOps", q: "As an SRE, how many incidents started with a “small” configuration change?",
    a: "ACFM traces the dependencies (proxy, monitors, alerts, clients) and predicts the blast radius first." },
  { id: "agents", chip: "AI agent builders", q: "Building AI agents, how do you prove an agent understood the consequences before it acted?",
    a: "ACFM gives agents a pre-action consequence check, with evidence, rules and a human gate, then scores the prediction." },
  { id: "sec", chip: "Security & compliance", q: "In security, can you show an auditor why an automated change was allowed?",
    a: "Every approval is bound to the exact plan, rules and state, and recorded next to the observed outcome." },
  { id: "data", chip: "Data teams", q: "On a data team, which dashboards and models break when one table changes?",
    a: "ACFM maps the downstream objects and flags what it could not verify, instead of guessing." },
  { id: "cfo", chip: "CFO", q: "As a CFO, what does one avoidable outage cost compared with a minute of foresight?",
    a: "ACFM catches harmful consequences while they are still predictions, not incident reports." },
];

function prefersReduced() {
  try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; }
}

export function Personas() {
  const [reduced] = useState(prefersReduced);
  const [i, setI] = useState(0);
  const [auto, setAuto] = useState(!reduced);
  const [typed, setTyped] = useState(reduced ? PERSONAS[0].a.length : 0);
  const p = PERSONAS[i];

  useEffect(() => {
    if (reduced) { setTyped(p.a.length); return; }
    setTyped(0);
    let n = 0;
    const id = window.setInterval(() => { n += 1; setTyped(n); if (n >= p.a.length) window.clearInterval(id); }, 24);
    return () => window.clearInterval(id);
  }, [i, p.a.length, reduced]);

  useEffect(() => {
    if (!auto || typed < p.a.length) return;
    const id = window.setTimeout(() => setI((x) => (x + 1) % PERSONAS.length), 3200);
    return () => window.clearTimeout(id);
  }, [auto, typed, p.a.length]);

  return (
    <div className="personas">
      <p className="small strong-text">Who is ACFM for?</p>
      <div className="persona-chips" role="tablist" aria-label="Roles">
        {PERSONAS.map((x, k) => (
          <button key={x.id} type="button" role="tab" aria-selected={k === i} aria-controls="persona-panel"
            className="persona-chip" onClick={() => { setAuto(false); setI(k); }}>{x.chip}</button>
        ))}
      </div>
      <div id="persona-panel" role="tabpanel" className="persona-panel" aria-live="polite">
        <p className="hud-label accent">{p.chip}</p>
        <p key={p.id} className="persona-q rise">{p.q}</p>
        <p className="persona-a">
          <span className="sr-only">{p.a}</span><span aria-hidden="true">{p.a.slice(0, typed)}</span><span className="caret" aria-hidden="true" />
        </p>
      </div>
    </div>
  );
}
