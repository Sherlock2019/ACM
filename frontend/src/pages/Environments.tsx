import { EnvPicker } from "../components/EnvPicker";
import { ConnectionBadge, Panel, Plain } from "../components/ui";
import { useAFM } from "../state";

export function Environments() {
  const { future } = useAFM();
  return (
    <div className="stack rise" style={{ gap: 18 }}>
      <div className="page-head">
        <div>
          <p className="hud-label accent">Step 3 · Where am I?</p>
          <h1 className="mt-s">Environments</h1>
          <p className="lede">Each environment is reached through an adapter that describes its objects, relationships, actions and simulation rules. The AFM engine is the same for all of them.</p>
        </div>
      </div>
      <EnvPicker withTemplates />
      <Panel title="Adapters: coming later">
        <p className="small dim">These environments have no working adapter. AFM cannot inspect, simulate or change them. Describing one in a use case does not connect it.</p>
        <ul className="grid g3 mt" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {future.map((f) => (
            <li key={f.name} className="glass-flat" style={{ padding: 12 }}>
              <div className="row between"><strong className="small">{f.name}</strong><ConnectionBadge status={f.status} /></div>
              <p className="faint tiny mt-s">{f.kind} · {f.note}</p>
            </li>
          ))}
        </ul>
      </Panel>
      <Plain>“Simulated” means AFM works on a local, fictional model whose behavior is written down explicitly. No adapter here is connected to a real system. A future adapter would have to report honestly what it can inspect, simulate and execute.</Plain>
    </div>
  );
}
