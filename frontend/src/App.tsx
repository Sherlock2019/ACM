import { Icon, Mark } from "./components/icons";
import { ResetButton } from "./components/ResetDialog";
import { ConnectionBadge, ErrorBox } from "./components/ui";
import { Assessment } from "./pages/Assessment";
import { Builder } from "./pages/Builder";
import { Environments } from "./pages/Environments";
import { Goals } from "./pages/Goals";
import { History } from "./pages/History";
import { Identity } from "./pages/Identity";
import { Objects } from "./pages/Objects";
import { Overview } from "./pages/Overview";
import { ReviewPage } from "./pages/Review";
import { Simulate } from "./pages/Simulate";
import { LlmSettings } from "./pages/LlmSettings";
import { Why } from "./pages/Why";
import { useAFM, useRoute } from "./state";

const NAV = [
  { id: "overview", label: "Overview", icon: "overview", step: "1" },
  { id: "identity", label: "Identity & Rules", icon: "identity", step: "2" },
  { id: "environments", label: "Environments", icon: "warehouse", step: "3" },
  { id: "objects", label: "Objects & Relationships", icon: "environment", step: "4" },
  { id: "goals", label: "Goals & Plans", icon: "workspace", step: "5" },
  { id: "assessment", label: "Consequence Assessment", icon: "spark", step: "6" },
  { id: "review", label: "Human Review", icon: "review", step: "7" },
  { id: "history", label: "Results & History", icon: "history", step: "8" },
];

export function App() {
  const route = useRoute();
  const { error, refresh, llm, envs, selected } = useAFM();
  const page = route[0];
  const env = envs.find((e) => e.environment_id === selected);
  return (
    <div className="shell">
      <a href="#main" className="sr-only">Skip to content</a>
      <aside className="sidebar" aria-label="AFM navigation">
        <a href="#/why" className="brand" aria-label="AFM: The WHY">
          <Mark />
          <span><span className="brand-name">AFM</span><span className="brand-tag">Action–Consequence Foresight Model</span></span>
        </a>
        <nav className="nav" aria-label="Main">
          <a href="#/why" aria-current={page === "why" ? "page" : undefined}><Icon name="info" /> <span>The WHY</span></a>
          <p className="nav-group" id="nav-test">Test the consequence prediction model</p>
          <a href="#/builder" aria-current={page === "builder" ? "page" : undefined} aria-describedby="nav-test"><Icon name="brain" /> <span>Create a use case</span></a>
          {NAV.map((n) => (
            <a key={n.id} href={`#/${n.id}`} aria-current={page === n.id ? "page" : undefined}>
              <Icon name={n.icon} /> <span>{n.label}</span><span className="step">{n.step}</span>
            </a>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="glass-flat" style={{ padding: 12 }}>
            <p className="hud-label">Playground</p>
            {env ? <><p className="small mt-s">{env.name} · v{env.version}</p><div className="mt-s"><ConnectionBadge status={env.kind} /></div></>
              : <p className="small mt-s faint">None selected</p>}
            <p className="hud-label mt">LLM tool</p>
            <p className="small mt-s">{llm?.provider ?? "…"}</p>
            <a href="#/llm" className="btn mt-s" style={{ width: "100%" }} aria-current={page === "llm" ? "page" : undefined}><Icon name="brain" size={14} /> Use your LLM model</a>
          </div>
          <ResetButton />
          <p className="faint tiny">Think before acting. Local prototype: simulated environments only, no real systems connected.</p>
        </div>
      </aside>
      <main className="main" id="main">
        {error && <div style={{ marginBottom: 16 }}><ErrorBox error={error} onRetry={refresh} /></div>}
        {page === "why" && <Why />}
        {page === "overview" && <Overview />}
        {page === "identity" && <Identity />}
        {page === "environments" && <Environments />}
        {page === "objects" && <Objects selectedId={route[1]} />}
        {page === "goals" && <Goals runId={route[1]} />}
        {page === "assessment" && <Assessment runId={route[1]} />}
        {page === "review" && <ReviewPage runId={route[1]} planId={route[2]} />}
        {page === "history" && <History runId={route[1]} />}
        {page === "builder" && <Builder usecaseId={route[1]} />}
        {page === "simulate" && <Simulate usecaseId={route[1]} />}
        {page === "llm" && <LlmSettings />}
        {![...NAV.map((n) => n.id), "why", "builder", "simulate", "llm"].includes(page) && <ErrorBox error={`Page "${page}" does not exist.`} />}
      </main>
    </div>
  );
}
