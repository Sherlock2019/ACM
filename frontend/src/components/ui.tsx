// UI primitives adapted from ACMP (Panel, Plain, Stat, provenance badges), extended for AFM statuses.
import type { ReactNode } from "react";
import type { CheckStatus, Evidence, PermissionClass } from "../types/afm";
import { Icon } from "./icons";

export function Panel({ title, right, children, className = "", id }: { title: string; right?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  return (
    <section className={`glass panel ${className}`} aria-labelledby={id ? `${id}-h` : undefined} id={id}>
      <header className="panel-head">
        <h2 className="hud-label" id={id ? `${id}-h` : undefined}>{title}</h2>
        {right}
      </header>
      {children}
    </section>
  );
}

const ST: Record<CheckStatus, { cls: string; ico: string }> = {
  PASS: { cls: "st-pass", ico: "✓" },
  FAIL: { cls: "st-fail", ico: "✕" },
  "REVIEW REQUIRED": { cls: "st-review", ico: "!" },
  UNKNOWN: { cls: "st-unknown", ico: "?" },
};
export function StatusBadge({ s }: { s: CheckStatus }) {
  const v = ST[s];
  return <span className={`badge ${v.cls}`}><span className="ico" aria-hidden="true">{v.ico}</span>{s}</span>;
}

const RES: Record<string, CheckStatus> = { MATCH: "PASS", MISMATCH: "FAIL", DIFFERENCE: "FAIL", "NOT VERIFIED": "UNKNOWN", PASS: "PASS", FAIL: "FAIL" };
export function ResultBadge({ r }: { r: string }) {
  const v = ST[RES[r] ?? "UNKNOWN"];
  return <span className={`badge ${v.cls}`}><span className="ico" aria-hidden="true">{v.ico}</span>{r === "DIFFERENCE" ? "MISMATCH" : r}</span>;
}

const EV: Record<Evidence, { ico: string; title: string }> = {
  observed: { ico: "◉", title: "Returned by a trusted local inspection or the simulator" },
  configured: { ico: "✎", title: "Explicitly defined in the scenario" },
  inferred: { ico: "≈", title: "Suggested by the LLM or a prediction" },
  unknown: { ico: "?", title: "Not established" },
};
export function EvidenceBadge({ e }: { e: Evidence }) {
  return <span className={`ev ev-${e}`} title={EV[e].title}><span aria-hidden="true">{EV[e].ico}</span>{e}</span>;
}

const PERM: Record<PermissionClass, { s: CheckStatus; label: string }> = {
  allowed: { s: "PASS", label: "Allowed" },
  requires_approval: { s: "REVIEW REQUIRED", label: "Requires approval" },
  prohibited: { s: "FAIL", label: "Prohibited" },
  unknown: { s: "UNKNOWN", label: "Unknown" },
};
export function PermissionBadge({ p }: { p: PermissionClass }) {
  const v = PERM[p];
  return <span className={`badge ${ST[v.s].cls}`}><span className="ico" aria-hidden="true">{ST[v.s].ico}</span>{v.label}</span>;
}

const RUN: Record<string, { s: CheckStatus; label: string }> = {
  awaiting_review: { s: "REVIEW REQUIRED", label: "Awaiting review" },
  approved: { s: "REVIEW REQUIRED", label: "Approved · not executed" },
  executed: { s: "PASS", label: "Executed (simulated)" },
  rejected: { s: "FAIL", label: "Rejected" },
  stale: { s: "UNKNOWN", label: "Stale: re-assess" },
  execution_blocked: { s: "FAIL", label: "Execution blocked" },
  unsupported_goal: { s: "UNKNOWN", label: "Unsupported goal" },
  no_viable_plan: { s: "FAIL", label: "No viable plan" },
};
export function RunStatusBadge({ s }: { s: string }) {
  const v = RUN[s] ?? { s: "UNKNOWN" as CheckStatus, label: s };
  return <span className={`badge ${ST[v.s].cls}`}><span className="ico" aria-hidden="true">{ST[v.s].ico}</span>{v.label}</span>;
}

export function Plain({ children, label = "In plain words" }: { children: ReactNode; label?: string }) {
  return <aside className="plain"><span className="hud-label">{label}</span><div>{children}</div></aside>;
}

export function Stat({ value, label, sub }: { value: ReactNode; label: string; sub?: string }) {
  return (
    <div className="glass-flat brackets stat">
      <p className="stat-value">{value}</p>
      <p className="hud-label mt-s">{label}</p>
      {sub && <p className="faint tiny mt-s">{sub}</p>}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return <div className="glass-flat loading hud-label" role="status">Loading {what}…</div>;
}
export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="error-box row between" role="alert">
      <span className="row"><Icon name="info" /> {error}</span>
      {onRetry && <button className="btn" onClick={onRetry}>Retry</button>}
    </div>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function fmtVal(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function fmtTime(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}

const isDict = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

/** before → after per key. Nested dicts are expanded one level; `changedOnly` hides unchanged keys. */
export function StateDelta({ before, after, names, changedOnly = false }: {
  before: Record<string, unknown>; after: Record<string, unknown>; names?: Record<string, string>; changedOnly?: boolean;
}) {
  const rows: [string, unknown, unknown][] = [];
  for (const k of Array.from(new Set([...Object.keys(before), ...Object.keys(after)]))) {
    const b = before[k], a = after[k];
    if (isDict(b) || isDict(a)) {
      const bd = isDict(b) ? b : {}, ad = isDict(a) ? a : {};
      for (const sk of Array.from(new Set([...Object.keys(bd), ...Object.keys(ad)]))) rows.push([`${names?.[k] ?? k} › ${names?.[sk] ?? sk}`, bd[sk], ad[sk]]);
    } else rows.push([names?.[k] ?? k, b, a]);
  }
  const shown = changedOnly ? rows.filter(([, b, a]) => JSON.stringify(b) !== JSON.stringify(a)) : rows;
  if (!shown.length) return <span className="faint small">No measurable change.</span>;
  return (
    <div className="stack" style={{ gap: 4 }}>
      {shown.map(([label, b, a]) => {
        const same = JSON.stringify(b) === JSON.stringify(a);
        return (
          <div key={label} className="delta small">
            <span className="faint">{label}: </span>
            {b === undefined ? <span className="faint">new</span> : <span>{fmtVal(b)}</span>}
            {!same && <><span className="arrow" aria-label="becomes">→</span><strong>{fmtVal(a)}</strong></>}
          </div>
        );
      })}
    </div>
  );
}

export function Definitions({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="note" role="note">
      <strong style={{ color: "var(--text)" }}>Definitions used for goal evaluation in this environment.</strong>{" "}
      {items.join(" ")}
    </div>
  );
}

export function EnforcementBadge({ e }: { e: "enforced" | "partial" | "guidance" }) {
  const m = { enforced: ["PASS", "Enforced by code"], partial: ["REVIEW REQUIRED", "Partially enforced"], guidance: ["UNKNOWN", "Guidance only"] } as const;
  const [s, label] = m[e];
  return <span className={`badge ${ST[s as CheckStatus].cls}`}><span className="ico" aria-hidden="true">{ST[s as CheckStatus].ico}</span>{label}</span>;
}

export function EffectBadge({ e }: { e: "benefit" | "neutral" | "warning" }) {
  if (e === "neutral") return <span className="chip">neutral</span>;
  return e === "benefit"
    ? <span className="badge st-pass"><span className="ico" aria-hidden="true">+</span>benefit</span>
    : <span className="badge st-review"><span className="ico" aria-hidden="true">!</span>warning</span>;
}

export function ConnectionBadge({ status }: { status: "simulated" | "connected" | "not_implemented" | "not_connected" }) {
  const m = { simulated: ["REVIEW REQUIRED", "Simulated"], connected: ["PASS", "Connected"], not_implemented: ["UNKNOWN", "Not implemented"], not_connected: ["UNKNOWN", "Not connected"] } as const;
  const [s, label] = m[status];
  return <span className={`badge ${ST[s as CheckStatus].cls}`}><span className="ico" aria-hidden="true">{ST[s as CheckStatus].ico}</span>{label}</span>;
}

export function Capabilities({ c }: { c: { inspect: boolean; simulate: boolean; execute: boolean } }) {
  return (
    <span className="row" style={{ gap: 6 }} aria-label="Adapter capabilities">
      {(["inspect", "simulate", "execute"] as const).map((k) => (
        <span key={k} className="chip" title={c[k] ? "supported" : "unsupported"}>
          <span aria-hidden="true" style={{ color: c[k] ? "var(--pass)" : "var(--fail)" }}>{c[k] ? "✓" : "✕"}</span> {k}<span className="sr-only">: {c[k] ? "supported" : "unsupported"}</span>
        </span>
      ))}
    </span>
  );
}
