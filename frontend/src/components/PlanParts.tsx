import type { CheckResult, Consequence, PlanAssessment } from "../types/afm";
import { Icon } from "./icons";
import { EffectBadge, PermissionBadge, StateDelta, StatusBadge } from "./ui";

const STATUS_LABEL: Record<Consequence["status"], string> = {
  known_in_simulation: "known in simulation",
  conditional: "conditional",
  unknown: "unknown",
};

export function nameOf(names: Record<string, string>, id: string) {
  return names[id] ?? (id.startsWith("res-") ? `New reservation (${id})` : id);
}

export function ConsequenceList({ items, names, filter }: { items: Consequence[]; names: Record<string, string>; filter?: "direct" | "connected" }) {
  const list = filter ? items.filter((c) => c.type === filter) : items;
  if (!list.length) return <p className="faint small">None.</p>;
  return (
    <ul className="cons" aria-label={filter ? `${filter} consequences` : "consequences"} style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {list.map((c, i) => (
        <li key={i} className={`cons-item ${c.status} ${c.effect === "warning" ? "bad" : ""} ${c.effect === "benefit" ? "good" : ""}`}>
          <div className="row between">
            <strong className="small">{nameOf(names, c.affected_object_id)}</strong>
            <span className="row" style={{ gap: 6 }}>
              <EffectBadge e={c.effect} />
              <span className={`ev ${c.status === "known_in_simulation" ? "ev-observed" : c.status === "conditional" ? "ev-inferred" : "ev-unknown"}`}>
                prediction · {STATUS_LABEL[c.status]}
              </span>
            </span>
          </div>
          <p className="small mt-s">{c.description}</p>
          {(Object.keys(c.before).length > 0 || Object.keys(c.predicted_after).length > 0) && (
            <div className="mt-s"><StateDelta changedOnly={c.type === "connected" && Object.keys(c.before).length > 0} before={c.before} after={c.predicted_after} names={names} /></div>
          )}
          <p className="faint tiny mt-s"><span className="mono">{c.evidence_rule.split(" ")[0]}</span> · {c.evidence_rule.split(" ").slice(1).join(" ")} · {c.type} · {c.relationship_to_target} · step {c.step}</p>
          {c.assumptions.length > 0 && <ul className="bullets tiny mt-s">{c.assumptions.map((a) => <li key={a}>Assumes: {a}</li>)}</ul>}
        </li>
      ))}
    </ul>
  );
}

export function ChecksList({ checks, compact = false }: { checks: CheckResult[]; compact?: boolean }) {
  return (
    <ul className="list">
      {checks.map((c) => (
        <li key={c.check} style={{ flexDirection: "column", gap: 4 }}>
          <div className="row between" style={{ width: "100%" }}>
            <span className="small">{c.label}</span>
            <StatusBadge s={c.status} />
          </div>
          {!compact && <ul className="bullets tiny">{c.details.map((d) => <li key={d}>{d}</li>)}</ul>}
        </li>
      ))}
    </ul>
  );
}

export function ActionCard({ a, names, step }: { a: PlanAssessment["plan"]["actions"][number]; names: Record<string, string>; step?: number }) {
  return (
    <div className="glass-flat" style={{ padding: 12 }}>
      <div className="row between">
        <span className="row small"><Icon name="play" size={14} />{step != null && <span className="mono accent">{step}.</span>} <span className="mono">{a.tool}</span> · {a.operation}</span>
        <PermissionBadge p={a.permission} />
      </div>
      <dl className="kv mt-s">
        <dt>target</dt><dd>{nameOf(names, a.target_object_id)} <span className="faint mono tiny">({a.target_object_id})</span></dd>
        <dt>parameters</dt><dd className="mono small">{Object.entries(a.parameters).map(([k, v]) => `${k} = ${typeof v === "string" && names[v] ? names[v] : String(v)}`).join(" · ") || "—"}</dd>
        <dt>purpose</dt><dd className="small">{a.purpose}</dd>
      </dl>
      {a.expected_preconditions.length > 0 && (
        <details className="mt-s"><summary className="small dim" style={{ cursor: "pointer" }}>Expected preconditions ({a.expected_preconditions.length})</summary>
          <ul className="bullets tiny mt-s">{a.expected_preconditions.map((p) => <li key={p}>{p}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

/** compact before→after per object for a plan's final predicted state (used in graphs and tables) */
export function predictedDeltas(a: PlanAssessment): Record<string, string> {
  const out: Record<string, string> = {};
  const fmt = (v: unknown) => (v === undefined ? "new" : typeof v === "boolean" ? (v ? "yes" : "no") : typeof v === "object" ? "…" : String(v));
  for (const c of a.simulation.consequences) {
    const id = c.affected_object_id;
    if (out[id] && c.effect !== "warning") continue; // keep the first change; a warning always wins
    const keys = Object.keys(c.predicted_after).filter((k) => JSON.stringify(c.before[k]) !== JSON.stringify(c.predicted_after[k]));
    if (!keys.length) {
      const k0 = Object.keys(c.predicted_after)[0];
      if (c.effect === "benefit" && k0 && !out[id]) out[id] = `${k0.replace(/_/g, " ")}: ${fmt(c.predicted_after[k0])} (kept)`;
      continue;
    }
    // the last changed scalar field is the outcome (e.g. processor output, available stock)
    const k = [...keys].reverse().find((x) => typeof c.predicted_after[x] !== "object") ?? keys[0];
    out[id] = `${k.replace(/_/g, " ")}: ${fmt(c.before[k])} → ${fmt(c.predicted_after[k])}`;
  }
  return out;
}
