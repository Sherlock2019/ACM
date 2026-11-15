import { EnforcementBadge, Loading, Panel, Plain, StatusBadge } from "../components/ui";
import { useAFM } from "../state";
import type { CheckStatus, ToolSpec } from "../types/afm";

function ToolsTable({ tools, caption }: { tools: ToolSpec[]; caption: string }) {
  const cell = (t: ToolSpec, col: "allowed" | "approval" | "prohibited"): [CheckStatus, string] => {
    if (col === "allowed") return t.permission === "allowed" ? ["PASS", "yes"] : t.permission === "requires_approval" ? ["REVIEW REQUIRED", "only with approval"] : ["FAIL", "no"];
    if (col === "approval") return t.permission === "requires_approval" ? ["REVIEW REQUIRED", "required"] : t.permission === "allowed" ? ["PASS", "not needed"] : ["FAIL", "n/a"];
    return t.permission === "prohibited" ? ["FAIL", "PROHIBITED"] : ["PASS", "no"];
  };
  return (
    <div className="table-wrap">
      <table className="tbl">
        <caption className="sr-only">{caption}</caption>
        <thead><tr><th scope="col">Tool</th><th scope="col">What it does</th><th scope="col">Technically possible</th><th scope="col">Allowed</th><th scope="col">Requires approval</th><th scope="col">Prohibited</th></tr></thead>
        <tbody>
          {tools.map((t) => (
            <tr key={t.name}>
              <td className="strong mono">{t.name}<div className="faint tiny">{t.modifies_state ? "changes state" : "read-only"}{t.reversible != null ? ` · ${t.reversible ? "reversible" : "not reversible"}` : ""}</div></td>
              <td className="small">{t.description}{Object.keys(t.parameters).length > 0 && <div className="faint tiny mono">{Object.entries(t.parameters).map(([k, v]) => `${k}: ${v}`).join(" · ")}</div>}</td>
              <td><span className="row" style={{ gap: 6 }}><StatusBadge s="PASS" /><span className="tiny dim">yes</span></span></td>
              {(["allowed", "approval", "prohibited"] as const).map((c) => {
                const [s, txt] = cell(t, c);
                return <td key={c}><span className="row" style={{ gap: 6 }}><StatusBadge s={s} /><span className="tiny dim">{txt}</span></span></td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Identity() {
  const { profile, llm, envs, selected } = useAFM();
  if (!profile) return <Loading what="AFM profile" />;
  const p = profile.profile;
  const env = envs.find((e) => e.environment_id === selected);
  const enforced = profile.conduct.rules.filter((r) => r.enforcement === "enforced").length;
  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head">
        <div>
          <p className="hud-label accent">Step 2 · Who am I and what may I do?</p>
          <h1 className="mt-s">Identity & Rules</h1>
          <p className="lede">Identity, permanent rules and permissions live in versioned configuration, outside the LLM. No goal, chat message or LLM answer can change them.</p>
        </div>
        <span className="chip">{profile.rules_version}</span>
      </div>

      <div className="grid g2">
        <Panel title="Identity">
          <dl className="kv">
            <dt>name</dt><dd>{p.name}</dd>
            <dt>identity</dt><dd>{p.identity}</dd>
            <dt>purpose</dt><dd>{p.purpose}</dd>
            <dt>goal</dt><dd>{p.goal_source}</dd>
            <dt>environment</dt><dd>{p.environment}</dd>
            <dt>LLM tool</dt><dd>{llm?.provider ?? "…"}<p className="faint tiny">{llm?.note}</p><p className="faint tiny">{llm?.privacy}</p></dd>
          </dl>
        </Panel>
        <Panel title="Permissions">
          <ul className="bullets">{p.permissions_summary.map((x) => <li key={x}>{x}</li>)}</ul>
          <p className="hud-label mt">Administrative only</p>
          <ul className="bullets mt-s">{p.administrative_only.map((x) => <li key={x}>{x}</li>)}</ul>
        </Panel>
      </div>

      <Panel title={`Rules of conduct: permanent and global (${profile.conduct.rules.length})`} right={<span className="chip">{enforced} enforced by code · {profile.conduct.rules.length - enforced} partially</span>}>
        <p className="small dim">{profile.conduct.note}</p>
        <div className="table-wrap mt">
          <table className="tbl">
            <caption className="sr-only">AFM rules of conduct</caption>
            <thead><tr><th scope="col">ID</th><th scope="col">Rule</th><th scope="col">What AFM must do</th><th scope="col">How it is enforced here</th></tr></thead>
            <tbody>{profile.conduct.rules.map((r) => (
              <tr key={r.id}>
                <td className="strong mono">{r.id}</td>
                <td className="strong">{r.title}</td>
                <td className="small">{r.text}</td>
                <td className="small"><EnforcementBadge e={r.enforcement} /><div className="faint tiny mt-s">{r.how}</div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </Panel>

      {env ? (
        <Panel title={`Environment rules: ${env.name}`}>
          <ul className="list">{env.rules.map((r) => (
            <li key={r.id} className="glass-flat" style={{ padding: "10px 12px", alignItems: "flex-start", flexWrap: "nowrap" }}>
              <span className="mono accent small" style={{ minWidth: 26 }}>{r.id}</span>
              <span style={{ flex: 1 }}><span className="small">{r.text}</span><span className="faint tiny" style={{ display: "block" }}>{r.how}</span></span>
              <EnforcementBadge e={r.enforcement} />
            </li>
          ))}</ul>
          <p className="faint tiny mt">These change when you select another playground. The rules of conduct above stay the same everywhere.</p>
        </Panel>
      ) : <Panel title="Environment rules"><p className="faint small">Select a playground to see its specific rules.</p></Panel>}

      <Panel title="Tools: generic (every environment)"><ToolsTable tools={p.tools} caption="Generic tools" /></Panel>
      {env && <Panel title={`Tools: ${env.name}`}><ToolsTable tools={env.tools} caption={`${env.name} tools`} /></Panel>}
      <Panel title="Security note"><p className="small dim">{p.security_note}</p></Panel>
      <Plain>“Technically possible” means the action exists. “Allowed” is what AFM may do. “Requires approval” means a human must say yes to the exact plan first. “Prohibited” means AFM will never do it, even if a human approves (R24). Rules marked “partially enforced” are honest about their limits: for example, AFM has no tool that could move money, but it does not check real-world resource use.</Plain>
    </div>
  );
}
