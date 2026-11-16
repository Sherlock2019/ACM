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
import { Project } from "./pages/Project";
import { Problem, ProblemNav } from "./pages/Problem";
import { useAFM, useRoute } from "./state";
import { ThemeToggle } from "./theme";

const NAV = [
  { id: "overview", label: "Overview", icon: "overview", step: "1" },
  { id: "builder", label: "Create a use case", icon: "brain", step: "" },
  { id: "project", label: "Your real project", icon: "play", step: "" },
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
  // "why" is the old name of the Problem page; keep old links working
  const isProblem = page === "problem" || page === "why";
  const topbar = (
    <header className="topbar">
      <div className="brand-block">
        <a href="#/problem" className="brand" aria-label="ACFM: The Problem">
          <Mark size={56} />
          <span><span className="brand-name">ACFM</span><span className="brand-tag">Action–Consequence Foresight Model</span></span>
        </a>
        <p className="brand-credit">
          Made with <span className="credit-love">love</span> by{" "}
          <a href="mailto:DzoanNguyentran@gmail.com">DzoanNguyentran@gmail.com</a> · <span className="credit-builder">A better World Builder</span>
        </p>
      </div>
      <nav className="top-tabs" aria-label="Sections">
        <a href="#/problem" aria-current={isProblem ? "page" : undefined}><Icon name="unknown" size={15} /> The Problem</a>
        <a href="#/overview" aria-current={!isProblem ? "page" : undefined}><Icon name="spark" size={15} /> Test it</a>
      </nav>
      <span className="top-right">
        <span className="faint tiny top-note">Think before acting.</span>
        <ThemeToggle />
      </span>
    </header>
  );
  if (isProblem) {
    return (
      <div className="app">
        <a href="#main" className="sr-only">Skip to content</a>
        {topbar}
        <div className="shell">
          <aside className="sidebar" aria-label="The Problem sections"><ProblemNav /></aside>
          <main className="main" id="main">
            {error && <div style={{ marginBottom: 16 }}><ErrorBox error={error} onRetry={refresh} /></div>}
            <Problem />
          </main>
        </div>
      </div>
    );
  }
  return (
    <div className="app">
    <a href="#main" className="sr-only">Skip to content</a>
    {topbar}
    <div className="shell">
      <aside className="sidebar" aria-label="Test the consequence prediction model">
        <nav className="nav" aria-label="Test it">
          <p className="nav-group">Test the consequence prediction model</p>
          {NAV.map((n) => (
            <a key={n.id} href={`#/${n.id}`} aria-current={page === n.id ? "page" : undefined}>
              <Icon name={n.icon} /> <span>{n.label}</span>{n.step && <span className="step">{n.step}</span>}
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
          <p className="faint tiny">Think before acting. Playgrounds are simulated; real-project tests run only the commands you approve, in a separate copy.</p>
        </div>
      </aside>
      <main className="main" id="main">
        {error && <div style={{ marginBottom: 16 }}><ErrorBox error={error} onRetry={refresh} /></div>}
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
        {page === "project" && <Project id={route[1]} />}
        {![...NAV.map((n) => n.id), "builder", "simulate", "llm"].includes(page) && <ErrorBox error={`Page "${page}" does not exist.`} />}
      </main>
    </div>
    </div>
  );
}
