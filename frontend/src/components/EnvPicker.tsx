import { useEffect, useState, type ReactNode } from "react";
import { api } from "../services/api";
import { go, useAFM } from "../state";
import type { EnvironmentDescription, SimTemplate } from "../types/afm";

function useRunSimulation() {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const start = async (templateId: string) => {
    setBusy(templateId); setErr(null);
    try { const uc = await api.createSimulation(templateId); go(`simulate/${uc.usecase_id}`); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  return { busy, err, start };
}
import { Icon } from "./icons";
import { Capabilities, ConnectionBadge, Empty } from "./ui";

const BLURB: Record<string, { tag: string; icon: string; main?: boolean }> = {
  "object-playground": { tag: "Simplest example", icon: "environment" },
  "webapp-demo": { tag: "Main demonstration", icon: "spark", main: true },
  "warehouse-demo": { tag: "Business example", icon: "inventory" },
};

export function EnvCard({ d, compact = false }: { d: EnvironmentDescription; compact?: boolean }) {
  const { selected, select } = useAFM();
  const sim = useRunSimulation();
  const b = BLURB[d.environment_id] ?? { tag: "Playground", icon: "environment" };
  const isSel = selected === d.environment_id;
  return (
    <article className={`glass panel env-card ${isSel ? "selected" : ""} ${b.main ? "main" : ""}`} aria-labelledby={`env-${d.environment_id}`}>
      <div className="row between">
        <span className="hud-label" style={{ color: b.main ? "var(--blue)" : undefined }}>{b.tag}</span>
        <ConnectionBadge status={d.kind} />
      </div>
      <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
        <span className="type-ico"><Icon name={b.icon} /></span>
        <div>
          <h3 id={`env-${d.environment_id}`}>{d.name}</h3>
          <p className="small dim mt-s">{d.summary}</p>
        </div>
      </div>
      {!compact && (
        <>
          <dl className="kv">
            <dt>adapter</dt><dd className="mono small">{d.adapter}</dd>
            <dt>known</dt><dd className="small">{d.object_count} objects · {d.relationship_count} relationships</dd>
            <dt>rules</dt><dd className="small">{d.rules.length} environment rules + the permanent rules of conduct</dd>
          </dl>
          <Capabilities c={d.capabilities} />
          <details><summary className="small dim" style={{ cursor: "pointer" }}>Discovery limitations ({d.limitations.length})</summary>
            <ul className="bullets tiny mt-s">{d.limitations.map((l) => <li key={l}>{l}</li>)}</ul></details>
        </>
      )}
      <div className="row" style={{ marginTop: "auto" }}>
        <button className={isSel ? "btn" : "btn-primary"} onClick={() => select(d.environment_id)} aria-pressed={isSel}>
          {isSel ? <><Icon name="check" size={14} /> Selected</> : "Select playground"}
        </button>
        <button className="btn" onClick={() => { select(d.environment_id); void sim.start(d.environment_id); }} disabled={!!sim.busy}>
          <Icon name="play" size={14} /> {sim.busy ? "Starting…" : "Run simulation"}
        </button>
      </div>
      {sim.err && <p className="tiny" style={{ color: "var(--fail)" }}>{sim.err}</p>}
    </article>
  );
}

/** Use cases without a working adapter (e.g. Data Readiness Agent): the simulation runs, honestly marked not connected. */
function TemplateCard({ t }: { t: SimTemplate }) {
  const sim = useRunSimulation();
  return (
    <article className="glass panel env-card" aria-labelledby={`tpl-${t.template_id}`}>
      <div className="row between"><span className="hud-label">Not connected · illustrative</span><ConnectionBadge status="not_connected" /></div>
      <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
        <span className="type-ico"><Icon name="unknown" /></span>
        <div><h3 id={`tpl-${t.template_id}`}>{t.title}</h3><p className="small dim mt-s">{t.tagline}</p></div>
      </div>
      <p className="faint tiny">No AFM adapter exists for this project. The simulation walks the 15 steps honestly: AFM cannot inspect, simulate or execute here, and its notes are illustrative.</p>
      <Capabilities c={{ inspect: false, simulate: false, execute: false }} />
      <div className="row" style={{ marginTop: "auto" }}>
        <button className="btn" onClick={() => void sim.start(t.template_id)} disabled={!!sim.busy}><Icon name="play" size={14} /> {sim.busy ? "Starting…" : "Run simulation"}</button>
      </div>
      {sim.err && <p className="tiny" style={{ color: "var(--fail)" }}>{sim.err}</p>}
    </article>
  );
}

/** Real-project mode: the user's own local folder or public GitHub repository, tested on real results. */
function RealProjectCard() {
  return (
    <article className="glass panel env-card real" aria-labelledby="tpl-real-project">
      <div className="row between"><span className="hud-label real-label">Your use case · real code</span><ConnectionBadge status="connected" /></div>
      <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
        <span className="type-ico"><Icon name="play" /></span>
        <div><h3 id="tpl-real-project">Your real project</h3><p className="small dim mt-s">A local folder or a public GitHub repository. ACFM predicts, you approve, real tests decide.</p></div>
      </div>
      <p className="faint tiny">Describe the change in plain words to your LLM; it drafts the code change, tests and predictions. ACFM works on a separate copy and runs only what you approve: baseline first, then after the change. Not a sandbox.</p>
      <Capabilities c={{ inspect: true, simulate: false, execute: true }} />
      <div className="row" style={{ marginTop: "auto" }}>
        <button className="btn-primary" onClick={() => go("project")}><Icon name="play" size={14} /> Test on your project</button>
      </div>
    </article>
  );
}

export function EnvPicker({ compact = false, withTemplates = false }: { compact?: boolean; withTemplates?: boolean }) {
  const { envs, selected } = useAFM();
  const [tpls, setTpls] = useState<SimTemplate[]>([]);
  const [sample, setSample] = useState<string>("");
  useEffect(() => { if (withTemplates) api.simTemplates().then((t) => setTpls(t.filter((x) => !x.adapter_id))).catch(() => {}); }, [withTemplates]);
  if (!envs.length) return <Empty>Loading playgrounds…</Empty>;
  if (!withTemplates) {
    return <div className="grid g3">{envs.map((d) => <EnvCard key={d.environment_id} d={d} compact={compact} />)}</div>;
  }
  // Overview: the real project (red) next to ONE sample project chosen from a dropdown
  const current = sample || selected || "webapp-demo";
  const env = envs.find((d) => d.environment_id === current);
  const tpl = tpls.find((t) => t.template_id === current);
  return (
    <div className="grid g2">
      <RealProjectCard />
      <div className="sample-pick">
        <label className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
          <span className="hud-label" style={{ whiteSpace: "nowrap" }}>Sample projects</span>
          <select className="field" value={current} onChange={(e) => setSample(e.target.value)} aria-label="Sample project">
            {envs.map((d) => <option key={d.environment_id} value={d.environment_id}>{d.name} · simulated</option>)}
            {tpls.map((t) => <option key={t.template_id} value={t.template_id}>{t.title} · not connected</option>)}
          </select>
        </label>
        {env ? <EnvCard d={env} compact={compact} /> : tpl ? <TemplateCard t={tpl} /> : <EnvCard d={envs[0]} compact={compact} />}
      </div>
    </div>
  );
}

/** Pages that need a selected environment show onboarding instead. */
export function RequireEnv({ children, title }: { children: (env: EnvironmentDescription) => ReactNode; title: string }) {
  const { envs, selected } = useAFM();
  const env = envs.find((e) => e.environment_id === selected);
  if (env) return <>{children(env)}</>;
  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head"><div><p className="hud-label accent">{title}</p><h1 className="mt-s">Choose a playground to begin.</h1>
        <p className="lede">AFM is generic. Pick the environment it should work in. All three are local simulations.</p></div></div>
      <EnvPicker compact />
    </div>
  );
}
