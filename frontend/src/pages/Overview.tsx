import { EnvPicker } from "../components/EnvPicker";
import { Icon } from "../components/icons";
import { Loading, Panel, Plain, RunStatusBadge, Stat, fmtTime } from "../components/ui";
import { go, useAFM } from "../state";

export function Overview() {
  const { profile, envs, runs, selected, llm } = useAFM();
  if (!profile) return <Loading what="AFM" />;
  const p = profile.profile;
  const env = envs.find((e) => e.environment_id === selected);
  const latest = runs[0];
  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <section className="glass panel brackets" style={{ padding: "26px 26px 24px" }}>
        <p className="hud-label accent">{p.tagline}</p>
        <div className="page-head" style={{ margin: "10px 0 0" }}>
          <div>
            <h1>{p.name}</h1>
            <p className="lede">Explore a digital environment, understand possible actions, predict their consequences, and review the result before acting.</p>
            <p className="faint small mt-s">Purpose: {p.purpose}</p>
          </div>
          <div className="stack" style={{ alignItems: "stretch" }}>
            <button className="btn-primary btn-lg" onClick={() => go(env ? "goals" : "environments")}><Icon name="workspace" /> {env ? "Start an assessment" : "Choose a playground"}</button>
            <a className="btn" href="#/builder"><Icon name="brain" size={15} /> Create a use case</a>
          </div>
        </div>
        <div className="row mt">
          <a className="btn" href="#/objects">Explore objects</a>
          <a className="btn" href="#/identity">View rules & permissions</a>
          <a className="btn" href="#/goals">Enter or select a goal</a>
        </div>
      </section>

      <div>
        <div className="row between" style={{ marginBottom: 10 }}>
          <h2>{env ? `Selected playground: ${env.name}` : "Choose a playground to begin."}</h2>
          <span className="faint small">All playgrounds are local simulations. Selecting one never changes AFM's identity or rules.</span>
        </div>
        <EnvPicker withTemplates />
      </div>

      <div className="grid g4">
        <Stat value={envs.length} label="Working playgrounds" sub="Simulated adapters. Others are listed as not implemented." />
        <Stat value={profile.conduct.rules.length} label="Rules of conduct" sub={`Permanent, global · ${profile.rules_version}`} />
        <Stat value={env ? env.object_count : "—"} label="Known objects" sub={env ? `${env.relationship_count} relationships in ${env.name}. Not proof every dependency is known.` : "Select a playground"} />
        <Stat value={llm?.mock ? "Mock" : "Claude"} label="LLM tool" sub={llm?.privacy ?? ""} />
      </div>

      <div className="grid g2">
        <Panel title="Without foresight vs with AFM">
          <div className="grid g2">
            <div className="glass-flat" style={{ padding: 12, borderColor: "rgba(255,107,107,.4)" }}>
              <p className="hud-label" style={{ color: "var(--fail)" }}>Without foresight</p>
              <p className="small mt-s">“I changed the port. The application is now unreachable.”</p>
            </div>
            <div className="glass-flat" style={{ padding: 12, borderColor: "rgba(63,207,115,.4)" }}>
              <p className="hud-label" style={{ color: "var(--pass)" }}>With AFM</p>
              <p className="small mt-s">“I predicted the dependency problem, proposed a complete plan, and asked the human to review it.”</p>
            </div>
          </div>
          <p className="faint tiny mt">Try it in the Web application playground: Goal “Change the application to port 9000 while keeping it accessible…”.</p>
        </Panel>
        <Panel title="Latest run">
          {latest ? (
            <div className="stack">
              <span className="row"><RunStatusBadge s={latest.status} /><span className="chip">{latest.environment_name}</span></span>
              <p className="small">“{latest.goal}”</p>
              <p className="faint tiny">{fmtTime(latest.created_at)} · env v{latest.environment_version}{latest.recommended ? ` · recommended ${latest.recommended}` : ""}</p>
              <a className="btn" href={`#/history/${latest.run_id}`}>Open run</a>
            </div>
          ) : <p className="faint small">No runs yet. Pick a playground and start an assessment.</p>}
        </Panel>
      </div>

      <Panel title="How AFM thinks before acting">
        <ol className="grid g3" style={{ margin: 0, paddingLeft: 0, listStyle: "none" }}>
          {p.core_loop.map((s, i) => (
            <li key={s} className="glass-flat row" style={{ padding: "9px 12px", alignItems: "flex-start", flexWrap: "nowrap" }}>
              <span className="mono accent small" style={{ minWidth: 20 }}>{i + 1}</span><span className="small">{s}</span>
            </li>
          ))}
        </ol>
      </Panel>
      <Plain>AFM is the decision-maker; an LLM is only a tool it may consult. AFM copies the environment, tries a plan on the copy, looks at what changes for the target <em>and</em> for connected objects, checks its rules, and then asks you. Nothing changes until you approve, and here only simulations ever change.</Plain>
    </div>
  );
}
