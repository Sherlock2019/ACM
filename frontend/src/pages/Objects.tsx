import { Fragment, useEffect, useState } from "react";
import { RequireEnv } from "../components/EnvPicker";
import { Icon, typeIcon } from "../components/icons";
import { RelationshipGraph } from "../components/RelationshipGraph";
import { Empty, ErrorBox, EvidenceBadge, Loading, Panel, fmtTime, fmtVal } from "../components/ui";
import { api } from "../services/api";
import { go, useAFM } from "../state";
import type { EnvironmentDescription, EnvObject, ObjectTypeExplanation } from "../types/afm";

function Understanding({ env, obj, names }: { env: EnvironmentDescription; obj: EnvObject; names: Record<string, string> }) {
  const { views, llm } = useAFM();
  const [out, setOut] = useState<ObjectTypeExplanation | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setOut(null); setErr(null); }, [obj.id]);
  const rels = views[env.environment_id].relationships.filter((r) => r.source === obj.id || r.target === obj.id);
  const unknownRels = rels.filter((r) => r.evidence === "unknown");
  const ask = async () => {
    setBusy(true); setErr(null);
    try { setOut(await api.askLLM(env.environment_id, obj.id)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="grid g3">
      <Panel title="What AFM observed in this environment" right={<EvidenceBadge e={obj.evidence} />}>
        <p className="faint tiny">Returned by {env.adapter} ({env.kind}). Last observed {fmtTime(obj.last_observed)}.</p>
        {Object.keys(obj.state).length ? (
          <dl className="kv mt-s">{Object.entries(obj.state).map(([k, v]) => (
            <Fragment key={k}><dt>{k}</dt><dd className="mono small">{Array.isArray(v) ? (v.length ? v.map((x) => names[String(x)] ?? String(x)).join(", ") : "none") : fmtVal(v)}</dd></Fragment>
          ))}</dl>
        ) : <p className="faint small mt-s">No state is known.</p>}
        <p className="hud-label mt">Configured behavior</p><p className="small mt-s">{obj.behavior || "—"}</p>
        <p className="hud-label mt">Relationships</p>
        <ul className="list mt-s">{rels.map((r) => (
          <li key={r.id} className="small"><EvidenceBadge e={r.evidence} /><span>{names[r.source] ?? r.source} <span className="mono accent">{r.type.replace(/_/g, " ")}</span> {names[r.target] ?? r.target}</span></li>
        ))}</ul>
      </Panel>
      <Panel title="What the LLM says about this object type" right={<span className="ev ev-inferred">≈ LLM-generated</span>}>
        <button className="btn" onClick={ask} disabled={busy}><Icon name="brain" size={15} /> {busy ? "Asking…" : `Ask about “${obj.type.replace(/_/g, " ")}”`}</button>
        <p className="faint tiny mt-s">General knowledge from {llm?.provider ?? "the LLM tool"}. It has not inspected this object. {llm?.privacy}</p>
        {err && <div className="mt"><ErrorBox error={err} /></div>}
        {out && (
          <div className="stack mt" aria-live="polite">
            <p className="small">{out.explanation}</p>
            <p className="small dim">{out.typical_behavior}</p>
            <div><p className="hud-label">Might depend on / affect</p><ul className="bullets tiny">{out.potential_relationships.map((x) => <li key={x}>{x}</li>)}</ul></div>
            <div><p className="hud-label">Inspect to verify</p><ul className="bullets tiny">{out.suggested_read_only_inspections.map((x) => <li key={x}>{x}</li>)}</ul></div>
            {out.ignored_instructions.length > 0 && <div className="warn tiny"><strong>Instruction-like text in the object was ignored</strong> (R22): “{out.ignored_instructions[0]}”</div>}
            <details><summary className="tiny dim" style={{ cursor: "pointer" }}>{out.data_sent_to_provider?.sent ? "Data sent to the provider" : "Data that would be sent if a real provider were enabled"}</summary>
              <pre className="mini mt-s" style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(out.data_sent_to_provider, null, 2)}</pre></details>
          </div>
        )}
      </Panel>
      <Panel title="Unknown or not verified" right={<EvidenceBadge e="unknown" />}>
        <ul className="bullets">
          {obj.known_unknowns.map((u) => <li key={u}>{u}</li>)}
          {unknownRels.map((r) => <li key={r.id}>Unverified link: {r.description}</li>)}
          {out?.unknowns.map((u) => <li key={u}>LLM: {u}</li>)}
          <li>Dependencies outside the known catalog (discovery is never complete, R19).</li>
        </ul>
        {obj.untrusted_text && (
          <div className="warn small mt"><strong>Untrusted text found in this object.</strong> Shown as data, never followed as an instruction:
            <p className="mono tiny mt-s">“{obj.untrusted_text}”</p></div>
        )}
      </Panel>
    </div>
  );
}

export function Objects({ selectedId }: { selectedId?: string }) {
  const { views } = useAFM();
  const [sel, setSel] = useState<string | null>(selectedId ?? null);
  useEffect(() => { if (selectedId) setSel(selectedId); }, [selectedId]);
  return (
    <RequireEnv title="Step 4 · What exists here?">
      {(env) => {
        const view = views[env.environment_id];
        if (!view) return <Loading what="objects" />;
        const objs = Object.fromEntries(view.objects.map((o) => [o.id, o]));
        const names = Object.fromEntries(view.objects.map((o) => [o.id, o.name]));
        const selected = sel && objs[sel] ? objs[sel] : null;
        const pick = (id: string) => { setSel(id); go(`objects/${id}`); };
        return (
          <div className="stack rise" style={{ gap: 18 }}>
            <div className="page-head">
              <div>
                <p className="hud-label accent">Step 4 · What exists here? · {env.name}</p>
                <h1 className="mt-s">Objects & Relationships</h1>
                <p className="lede">{view.objects.length} known objects and {view.relationships.length} known relationships, version {view.version}, from {env.adapter}.</p>
              </div>
              <div className="row" aria-label="Evidence legend"><EvidenceBadge e="observed" /><EvidenceBadge e="configured" /><EvidenceBadge e="inferred" /><EvidenceBadge e="unknown" /></div>
            </div>
            <div className="note">{view.completeness_note}</div>
            <Panel title="Relationship graph"><RelationshipGraph objects={view.objects} relationships={view.relationships} layout={view.layout} selected={sel} onSelect={pick} /></Panel>
            <div className="grid g-side">
              <Panel title="Objects">
                <div className="obj-list">{view.objects.map((o) => (
                  <button key={o.id} className="obj-btn" aria-pressed={o.id === sel} onClick={() => pick(o.id)}>
                    <span className="type-ico"><Icon name={typeIcon(o.type)} /></span>
                    <span style={{ flex: 1, minWidth: 0 }}><span className="small" style={{ display: "block", fontWeight: 600 }}>{o.name}</span><span className="faint tiny">{o.type.replace(/_/g, " ")}</span></span>
                    <EvidenceBadge e={o.evidence} />
                  </button>
                ))}</div>
              </Panel>
              {selected ? (
                <Panel title={selected.name} right={<span className="faint tiny mono">{selected.id} · {selected.type}</span>}>
                  <p className="small dim">{selected.purpose}</p>
                  <div className="grid g2 mt">
                    <div><p className="hud-label">Accepted actions</p><p className="small mt-s">{selected.accepted_actions.join(", ") || "none"}</p></div>
                    <div><p className="hud-label">Outputs</p><p className="small mt-s">{selected.outputs.join(", ") || "none"}</p></div>
                  </div>
                  {selected.constraints.length > 0 && <><p className="hud-label mt">Constraints</p><ul className="bullets mt-s">{selected.constraints.map((c) => <li key={c}>{c}</li>)}</ul></>}
                </Panel>
              ) : <Panel title="Object details"><Empty>Select an object to see what AFM observed, what the LLM says about its type, and what is unknown.</Empty></Panel>}
            </div>
            {selected && <Understanding env={env} obj={selected} names={names} />}
            <Panel title="Relationship list">
              <div className="table-wrap"><table className="tbl">
                <thead><tr><th scope="col">Source</th><th scope="col">Relationship</th><th scope="col">Target</th><th scope="col">Description</th><th scope="col">Evidence</th></tr></thead>
                <tbody>{view.relationships.map((r) => (
                  <tr key={r.id}><td className="strong">{names[r.source] ?? r.source}</td><td className="mono accent small">{r.type.replace(/_/g, " ")}</td><td>{names[r.target] ?? r.target}</td><td className="small">{r.description}</td><td><EvidenceBadge e={r.evidence} /></td></tr>
                ))}</tbody>
              </table></div>
            </Panel>
          </div>
        );
      }}
    </RequireEnv>
  );
}
