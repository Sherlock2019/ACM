// "The Problem": the problem ACFM solves (AI agents act without seeing the domino effect of their actions),
// who feels it, why now, what ACFM does, how it works, the benefits, the current stack and what comes next.
import { useEffect, useState, type ReactNode } from "react";
import { ConsequenceCascade } from "../components/ConsequenceCascade";
import { Icon } from "../components/icons";
import { Personas } from "../components/Personas";
import { useAFM } from "../state";

const SECTIONS = [
  { id: "problem", label: "The problem", icon: "unknown" }, { id: "who", label: "Who feels it", icon: "identity" }, { id: "whynow", label: "Why now", icon: "history" },
  { id: "solution", label: "What ACFM does", icon: "info" }, { id: "how", label: "How it works", icon: "environment" },
  { id: "sowhat", label: "So what?", icon: "review" }, { id: "stack", label: "Current stack", icon: "warehouse" }, { id: "next", label: "What comes next", icon: "arrow" },
  { id: "principle", label: "Our principle", icon: "spark" },
];

/** Left panel of the Problem page: jumps to a section and highlights the one being read */
export function ProblemNav() {
  const [active, setActive] = useState(SECTIONS[0].id);
  useEffect(() => {
    const on = () => {
      const line = 140;
      let cur = SECTIONS[0].id;
      for (const s of SECTIONS) { const el = document.getElementById(s.id); if (el && el.getBoundingClientRect().top <= line) cur = s.id; }
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) cur = SECTIONS[SECTIONS.length - 1].id;
      setActive(cur);
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <nav className="nav" aria-label="The Problem sections">
      <p className="nav-group">The Problem</p>
      {SECTIONS.map((s) => (
        <a key={s.id} href={`#/problem`} aria-current={active === s.id ? "location" : undefined}
          onClick={(e) => { e.preventDefault(); setActive(s.id); document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth" }); }}>
          <Icon name={s.icon} /> <span>{s.label}</span>
        </a>
      ))}
    </nav>
  );
}

function Section({ id, kicker, title, children }: { id: string; kicker: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="why-section" aria-labelledby={`${id}-h`}>
      <p className="hud-label accent">{kicker}</p>
      <h2 id={`${id}-h`} className="why-h2">{title}</h2>
      <div className="stack mt" style={{ gap: 14 }}>{children}</div>
    </section>
  );
}

function Table({ head, rows, caption }: { head: string[]; rows: ReactNode[][]; caption: string }) {
  return (
    <div className="table-wrap glass-flat" style={{ padding: 4 }}>
      <table className="tbl">
        <caption className="sr-only">{caption}</caption>
        <thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={j === 0 ? "strong" : "small"}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function Status({ s }: { s: "today" | "next" | "planned" }) {
  const m = { today: ["st-pass", "✓", "working today"], next: ["st-review", "▸", "next · in design"], planned: ["st-unknown", "○", "planned"] }[s];
  return <span className={`badge ${m[0]}`}><span className="ico" aria-hidden="true">{m[1]}</span>{m[2]}</span>;
}

function Sub({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="glass-flat" style={{ padding: 14 }}>
      <p className="row" style={{ gap: 10, flexWrap: "nowrap" }}><span className="step-n mono">{n}</span><strong>{title}</strong></p>
      <div className="stack mt-s small" style={{ gap: 8 }}>{children}</div>
    </div>
  );
}

/** The ACFM cycle as a flow */
function Cycle() {
  const steps = ["Task Goal", "Rules & permissions", "Inspect environment & objects", "Propose plans", "Predict consequences per plan",
    "Compare against goal & rules", "Human review", "Apply & test approved plan", "Compare predictions with results", "Evaluate & record feedback"];
  return (
    <figure className="glass-flat why-figure">
      <svg viewBox="0 0 900 190" role="img" aria-label={`The ACFM cycle: ${steps.join(", then ")}, then back to the next task.`}>
        <defs><marker id="cyc" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--accent)" /></marker></defs>
        {steps.map((s, i) => {
          const row = i < 5 ? 0 : 1, col = row === 0 ? i : 9 - i;
          const x = 20 + col * 176, y = 20 + row * 100;
          const human = s === "Human review", test = s.startsWith("Apply");
          return (
            <g key={s}>
              <rect x={x} y={y} width={156} height={56} rx={10} fill="var(--bg-2)" stroke={human ? "var(--review)" : test ? "var(--blue)" : i === 0 || i === 9 ? "var(--accent)" : "var(--glass-border-hi)"} strokeWidth={1.5} />
              <text x={x + 78} y={y + 22} textAnchor="middle" className="d-sub" style={{ fill: "var(--accent)" }}>{i + 1}</text>
              <text x={x + 78} y={y + 40} textAnchor="middle" className="d-sub" style={{ fill: "var(--text)", fontSize: 11 }}>{s.length > 24 ? s.slice(0, 23) + "…" : s}</text>
              {i < 4 && <line x1={x + 158} y1={y + 28} x2={x + 174} y2={y + 28} stroke="var(--accent)" strokeWidth={1.4} markerEnd="url(#cyc)" />}
              {i >= 5 && i < 9 && <line x1={x - 2} y1={y + 28} x2={x - 18} y2={y + 28} stroke="var(--accent)" strokeWidth={1.4} markerEnd="url(#cyc)" />}
            </g>
          );
        })}
        <line x1={20 + 4 * 176 + 78} y1={78} x2={20 + 4 * 176 + 78} y2={118} stroke="var(--accent)" strokeWidth={1.4} markerEnd="url(#cyc)" />
      </svg>
    </figure>
  );
}

/** Existing LLM + ACFM tools + ACFM engine → evidence-based assessment */
function ArchitectureDiagram() {
  const box = (x: number, y: number, w: number, title: string, sub: string, color: string) => (
    <g>
      <rect x={x} y={y} width={w} height={70} rx={12} fill="var(--bg-2)" stroke={color} strokeWidth={1.6} />
      <text x={x + w / 2} y={y + 28} textAnchor="middle" className="d-title">{title}</text>
      <text x={x + w / 2} y={y + 50} textAnchor="middle" className="d-sub">{sub}</text>
    </g>
  );
  return (
    <figure className="glass-flat why-figure">
      <svg viewBox="0 0 900 300" role="img" aria-label="Architecture: an existing LLM explains and proposes; ACFM tools inspect and test; the ACFM engine predicts and checks rules; together they produce an evidence-based consequence assessment that a human reviews.">
        <defs><marker id="why-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--accent)" /></marker></defs>
        {box(20, 20, 260, "Existing LLM (a tool)", "explains, interprets, proposes", "var(--review)")}
        {box(320, 20, 260, "ACFM tools & adapters", "inspect, simulate, test", "var(--blue)")}
        {box(620, 20, 260, "ACFM consequence engine", "predicts, checks rules", "var(--accent)")}
        {[150, 450, 750].map((x) => <line key={x} x1={x} y1={92} x2={450} y2={180} stroke="var(--accent)" strokeWidth={1.6} markerEnd="url(#why-arr)" />)}
        <rect x={250} y={182} width={400} height={56} rx={12} fill="rgba(var(--accent-rgb),.12)" stroke="var(--accent)" strokeWidth={2} />
        <text x={450} y={208} textAnchor="middle" className="d-title">Evidence-based consequence assessment</text>
        <text x={450} y={227} textAnchor="middle" className="d-sub">predicted · conditional · unknown, per object</text>
        <line x1={450} y1={240} x2={450} y2={272} stroke="var(--accent)" strokeWidth={1.6} markerEnd="url(#why-arr)" />
        <text x={450} y={292} textAnchor="middle" className="d-sub">Human review → apply & test once → observe → compare → Win</text>
      </svg>
    </figure>
  );
}

/** Real-project mode: project → ACFM test workspace → baseline → patch → approved tests → compare */
function RealProjectFlow() {
  const steps = [["Your project", "local path or GitHub URL"], ["ACFM test workspace", "separate copy · commit recorded"], ["Read-only inspection", "code, config, existing tests"],
    ["Predictions saved", "testable, before anything runs"], ["Review", "exact patch + exact commands"], ["Baseline tests", "before the patch"],
    ["Apply patch + same tests", "clean environment, timeout"], ["Compare & Win", "MATCH / MISMATCH / NOT VERIFIED"]];
  return (
    <figure className="glass-flat why-figure">
      <svg viewBox="0 0 900 200" role="img" aria-label={`Real-project flow: ${steps.map((s) => s[0]).join(", then ")}.`}>
        <defs><marker id="rp" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--blue)" /></marker></defs>
        {steps.map(([t, s], i) => {
          const row = i < 4 ? 0 : 1, col = row === 0 ? i : 7 - i, x = 18 + col * 220, y = 16 + row * 104;
          return (
            <g key={t}>
              <rect x={x} y={y} width={200} height={64} rx={10} fill="var(--bg-2)" stroke={t === "Review" ? "var(--review)" : t.startsWith("Compare") ? "var(--accent)" : "var(--blue)"} strokeWidth={1.4} />
              <text x={x + 100} y={y + 27} textAnchor="middle" className="d-title" style={{ fontSize: 13 }}>{t}</text>
              <text x={x + 100} y={y + 46} textAnchor="middle" className="d-sub" style={{ fontSize: 10.5 }}>{s}</text>
              {i < 3 && <line x1={x + 202} y1={y + 32} x2={x + 218} y2={y + 32} stroke="var(--blue)" strokeWidth={1.4} markerEnd="url(#rp)" />}
              {i >= 4 && i < 7 && <line x1={x - 2} y1={y + 32} x2={x - 18} y2={y + 32} stroke="var(--blue)" strokeWidth={1.4} markerEnd="url(#rp)" />}
            </g>
          );
        })}
        <line x1={18 + 3 * 220 + 100} y1={82} x2={18 + 3 * 220 + 100} y2={118} stroke="var(--blue)" strokeWidth={1.4} markerEnd="url(#rp)" />
      </svg>
    </figure>
  );
}

/** The supervised-learning loop */
function LearningLoop() {
  const steps = ["ACFM predicts consequences", "Human approves the test", "Test produces observations", "Compare predictions & results",
    "Human reviews corrections", "Approved training examples", "Train or adapt the predictor", "Evaluate on unseen projects"];
  const cx = 450, cy = 190, r = 150;
  const pts = steps.map((_, i) => { const a = -Math.PI / 2 + (i * 2 * Math.PI) / steps.length; return [cx + r * 1.65 * Math.cos(a), cy + r * Math.sin(a)]; });
  return (
    <figure className="glass-flat why-figure">
      <svg viewBox="0 0 900 400" role="img" aria-label={`Supervised learning loop: ${steps.join(", then ")}. If better than the baseline, consider using the updated predictor; if not, investigate data and model.`}>
        <defs><marker id="loop-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--text-faint)" /></marker></defs>
        <ellipse cx={cx} cy={cy} rx={r * 1.65} ry={r} fill="none" stroke="rgba(255,255,255,.12)" strokeDasharray="5 6" />
        {pts.map(([x, y], i) => {
          const [nx, ny] = pts[(i + 1) % pts.length];
          return <line key={`l${i}`} x1={x + (nx - x) * 0.18} y1={y + (ny - y) * 0.18} x2={x + (nx - x) * 0.82} y2={y + (ny - y) * 0.82} stroke="var(--text-faint)" strokeWidth={1.2} markerEnd="url(#loop-arr)" />;
        })}
        {pts.map(([x, y], i) => (
          <g key={i}>
            <rect x={x - 92} y={y - 22} width={184} height={44} rx={10} fill="var(--bg-2)" stroke={i === 6 ? "var(--accent)" : i === 4 ? "var(--review)" : "var(--glass-border-hi)"} strokeWidth={i === 6 || i === 4 ? 1.8 : 1.2} />
            <text x={x} y={y + 4} textAnchor="middle" className="d-sub" style={{ fill: "var(--text)" }}>{steps[i]}</text>
          </g>
        ))}
        <text x={cx} y={cy - 6} textAnchor="middle" className="d-title">Better than the baseline?</text>
        <text x={cx} y={cy + 16} textAnchor="middle" className="d-sub">yes → consider the updated predictor · no → investigate data & model</text>
      </svg>
      <figcaption className="faint tiny mt-s">Supervised learning: the model learns from examples with human-reviewed target outcomes. Saving a failed prediction does not, by itself, change any model.</figcaption>
    </figure>
  );
}

const PROBLEMS = [
  { n: "01", title: "Agents act on assumptions", text: "The state of the system is assumed from the prompt, not inspected. The agent changes what it was told about, not what is really there." },
  { n: "02", title: "Consequences hide in connections", text: "The change lands on one object; the damage lands on the objects connected to it: the proxy, the monitor, the client nobody mentioned." },
  { n: "03", title: "Confidence is not evidence", text: "A fluent answer sounds certain. Nobody records what the agent predicted, so nobody can measure whether it was right, or learn when it was wrong." },
];

const WHY_NOW = [
  { title: "Agents now act, not just suggest", text: "AI assistants have moved from writing suggestions to running commands, editing repositories and changing infrastructure." },
  { title: "More autonomy, bigger blast radius", text: "Every step a human no longer checks is a step where one wrong assumption can topple the next system in line." },
  { title: "Trust needs measurement", text: "Teams need a way to see consequences before approving, and a score for how often the agent foresaw them correctly." },
];

export function Problem() {
  const { profile } = useAFM();
  const loop = profile?.profile.core_loop ?? [];
  return (
    <div className="stack rise why" style={{ gap: 34 }}>
      <section className="glass panel brackets why-hero problem-hero">
        <p className="hud-label accent">The problem · ACFM — Action–Consequence Foresight Model</p>
        <h1 className="mt-s">AI agents can now act. <span className="grad-text">They can't yet see what their actions will break.</span></h1>
        <p className="lede hero-lede">One small change (a port, a permission, a column) can topple a chain of connected systems. <strong>ACFM predicts that domino effect before anything runs</strong>, so a human decides with evidence instead of hope.</p>
        <div className="row mt hero-ctas">
          <a className="btn-primary btn-lg" href="#/overview">See it predict →</a>
          <a className="btn btn-lg" href="#/project">Try it on your repo</a>
        </div>
        <div className="mt-l"><ConsequenceCascade /></div>
      </section>

      <Section id="problem" kicker="The problem" title="Every action has consequences an AI agent cannot see">
        <p className="lede-lg">AI can write code, manage infrastructure, analyse data and make decisions. But before an agent acts on a real system, someone has to answer one question:</p>
        <blockquote className="why-quote">“If I do this, what will happen to the object I change, and to the people and systems connected to it?”</blockquote>
        <p>Today, nobody answers it systematically. Three gaps make AI actions risky:</p>
        <div className="grid g3">
          {PROBLEMS.map((p) => (
            <div key={p.n} className="glass-flat pcard">
              <span className="pcard-n mono">{p.n}</span>
              <strong className="pcard-title">{p.title}</strong>
              <p className="small dim">{p.text}</p>
            </div>
          ))}
        </div>
        <div className="glass-flat" style={{ padding: 14 }}>
          <p className="hud-label accent">Example · changing an application port</p>
          <p className="mt-s">“Move the application from port 8000 to port 9000 while keeping it accessible.”</p>
          <p className="small dim mt-s">An agent might only change the application configuration. ACFM also asks: does the web server forward to the old port? Does a health monitor check it? Which tests would show users can still reach the app? What is known, and what remains unknown?</p>
          <div className="mt"><Table caption="Port change plans" head={["Plan", "Predicted result"]} rows={[
            ["Change only the application port", "The app may start on 9000, but the web server may still send requests to 8000: users can lose access, and the monitor may alert."],
            ["Change the app and its known dependent configurations", "The app should remain accessible if the identified changes and checks succeed."],
          ]} /></div>
          <p className="small mt-s">The human reviews the proposed plan before any state-changing action. <a href="#/overview">Try it in the Web application playground →</a></p>
        </div>
        <div className="grid g2">
          <ul className="bullets">
            <li>Does the agent know the <strong>actual state</strong> of the environment?</li>
            <li>Has it identified the objects <strong>connected</strong> to the one it wants to change?</li>
            <li>Has it considered both the <strong>benefits and the negative effects</strong>?</li>
            <li>Does it have <strong>evidence</strong> for its prediction?</li>
          </ul>
          <ul className="bullets">
            <li>Will it <strong>admit when information is missing</strong>?</li>
            <li>Can we <strong>test</strong> whether its prediction was correct?</li>
            <li>Did it <strong>respect the human's rules</strong> while pursuing the goal?</li>
          </ul>
        </div>
      </Section>

      <Section id="who" kicker="Who feels it" title="Anyone who lets software change real systems">
        <Personas />
      </Section>

      <Section id="whynow" kicker="Why now" title="Agents are getting the keys to production">
        <div className="grid g3">
          {WHY_NOW.map((w, i) => (
            <div key={w.title} className="glass-flat pcard">
              <span className="pcard-n mono">{String(i + 1).padStart(2, "0")}</span>
              <strong className="pcard-title">{w.title}</strong>
              <p className="small dim">{w.text}</p>
            </div>
          ))}
        </div>
        <p>A text response alone does not guarantee that the model inspected the system, discovered the right dependencies or verified the result. <strong>ACFM connects reasoning with evidence and feedback:</strong> inspect what it can, predict what may happen, ask for review, and compare the prediction with actual results.</p>
      </Section>

      <Section id="solution" kicker="What ACFM does" title="A consequence-aware layer between an AI agent and the systems it changes">
        <p>ACFM helps an AI agent understand a task, explore its environment, propose possible actions and assess their consequences <strong>before a human decides whether to proceed</strong>. It starts with five questions:</p>
        <ol className="grid g3" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {["What is my Task Goal?", "What rules and permissions must I respect?", "What objects and systems exist in my environment?", "What could happen if I take this action?", "Will the result meet the goal while respecting the rules?"].map((q, i) => (
            <li key={q} className="glass-flat row" style={{ padding: "12px 14px", flexWrap: "nowrap" }}><span className="step-n mono">{i + 1}</span><strong>{q}</strong></li>
          ))}
        </ol>
        <p>For example, to change a web application's port, ACFM considers more than the application configuration: it also investigates whether the web server, health monitor or other known systems depend on that port.</p>
        <p className="dim">ACFM uses an existing LLM as a <strong>tool</strong> to help understand environments, objects and possible plans, and combines that understanding with inspection tools, rules, simulations, tests and human review. The LLM is never the authority on what is true, what is allowed or what happened.</p>
        <Table caption="LLM agent compared with ACFM" head={["", "Typical LLM agent", "ACFM"]} rows={[
          ["Environment", "Assumed from the prompt", "Inspected through authorized adapters; evidence labelled observed / configured / inferred / unknown"],
          ["Consequences", "Implicit, if any", "Explicit per object: direct, connected and whole environment, each with its rule and assumptions"],
          ["Rules", "Instructions in a prompt", "32 permanent rules of conduct pinned in code, plus environment and task rules; enforced by the backend"],
          ["Human control", "Optional confirmation", "Approval bound to the exact plan, parameters, state and policy; rechecked before execution"],
          ["Uncertainty", "Confident-sounding guesses", "“Conditional” and “unknown” are first-class answers; ACFM says “I don't know”"],
          ["After acting", "Moves on", "Observes, compares prediction vs result, evaluates prediction accuracy, goal and rules"],
        ]} />
      </Section>

      <Section id="how" kicker="How does ACFM work?" title="One cycle, from Task Goal to evaluated outcome">
        <Cycle />
        <div className="grid g2">
          <Sub n={1} title="Understand the Task Goal">
            <p>The human describes what they want, the target object if known, and any success criteria. For example: <em>“Improve the security of the orders API without breaking the existing client.”</em></p>
            <p className="dim">ACFM captures the desired input and output, identifies missing information and helps make the goal <strong>testable</strong> before proposing a change. Criteria it proposes are labelled as proposals until the human agrees.</p>
          </Sub>
          <Sub n={2} title="Understand the environment">
            <p>Authorized tools inspect the relevant environment (a repository, application, infrastructure component, spreadsheet, business system or simulated playground) for objects and states, inputs, outputs and behavior, relationships and dependencies, permitted actions, and known unknowns.</p>
            <p className="dim">The LLM explains object types and suggests what to inspect; <strong>inspection provides the evidence</strong>.</p>
          </Sub>
          <Sub n={3} title="Propose plans and predict consequences">
            <p>For each plan: the direct effect on the target, effects on connected objects, expected benefits, potential harm or disruption, assumptions and uncertainty, and the <strong>tests that could check each prediction</strong>.</p>
            <p className="dim">Plans with prohibited actions are rejected before prediction. When the evidence is insufficient, ACFM says <strong>“I don't know.”</strong></p>
          </Sub>
          <Sub n={4} title="Check rules and request human review">
            <p>Each plan is checked against global rules, task-specific rules and tool permissions. Before any state-changing action the human sees the exact plan, the objects and files it changes, predicted consequences, rules, intended tests, assumptions and unknowns.</p>
            <p className="dim">Approval applies to that reviewed plan only. It never grants access to an unauthorized system or permits a prohibited action, and any change in plan, state or policy cancels it.</p>
          </Sub>
          <Sub n={5} title="Test and observe">
            <p>Where supported and authorized, the approved plan is applied and tested once in the selected test environment. ACFM records what it predicted, what was tested, what actually happened, and what could not be verified.</p>
            <p className="dim">The original prediction is preserved so it can be compared honestly with the result.</p>
          </Sub>
          <Sub n={6} title="Evaluate the outcome">
            <Table caption="Win conditions" head={["Condition", "Question"]} rows={[
              ["Prediction accuracy", "Did the required predictions match the observed test results?"],
              ["Task Goal achievement", "Did the observed outcome meet the agreed success criteria?"],
              ["Rule compliance", "Were the applicable rules respected and verified?"],
            ]} />
            <p>An <strong>ACFM Win</strong> requires all three. Any failure means <strong>Not a Win</strong>. If something can't be verified, the result is <strong>Not Verified</strong>; ACFM never invents a success.</p>
          </Sub>
        </div>

        <p className="hud-label mt">Where ACFM can run</p>
        <div className="grid g2">
          <div className="glass-flat" style={{ padding: 14 }}>
            <p className="row between"><strong>Simulated playgrounds</strong><Status s="today" /></p>
            <p className="small dim mt-s">Generic object chain, web application port change and inventory assistant. Explicit, fictional behavior, with the full 16-step assessment, live 2D view and Win evaluation.</p>
            <a className="btn mt-s" href="#/overview">Open the playgrounds</a>
          </div>
          <div className="glass-flat" style={{ padding: 14, borderColor: "rgba(106,168,255,.45)" }}>
            <p className="row between"><strong>Your real project</strong><Status s="today" /></p>
            <p className="small dim mt-s">Point ACFM at a local project or a public GitHub repository. It works in a separate <strong>ACFM test workspace</strong>, predicts before testing, and compares with real test results. Details below.</p>
            <a className="btn mt-s" href="#/project">Test on your project</a>
          </div>
        </div>

        <div className="glass panel" style={{ borderColor: "rgba(106,168,255,.4)" }}>
          <p className="row between"><span className="hud-label" style={{ color: "var(--blue)" }}>Real-project mode: how it works</span><Status s="today" /></p>
          <div className="mt"><RealProjectFlow /></div>
          <div className="grid g2 mt">
            <ul className="bullets small">
              <li><strong>Two sources, one workflow.</strong> A local project or a public GitHub repository (default branch or a chosen commit). Same Task Goal, rules, review, comparison and Win as the playgrounds.</li>
              <li><strong>Your work stays untouched.</strong> A local Git project is cloned into a separate copy at its current commit (uncommitted changes are not copied); a plain folder is copied without dependency folders. A GitHub repository is shallow-cloned into a new folder. Nothing is reset, cleaned, overwritten, pushed or opened as a pull request, and ACFM checks afterwards that your folder is unchanged.</li>
              <li><strong>Inspection first.</strong> Read-only: purpose, technology, files, functions, APIs, configuration, existing tests and documented test commands. README text, scripts and comments are data, never instructions.</li>
              <li><strong>Testable predictions, saved before anything runs.</strong> Each one names what will be observed, the expected value, and the approved command that measures it (e.g. “tests/test_orders.py goes from fail to pass; no other test changes”).</li>
            </ul>
            <ul className="bullets small">
              <li><strong>Exact review.</strong> You approve the exact patch (checked with <code>git apply --check</code>, confined to the workspace) and the exact commands, run as fixed argument lists, not shell strings. Any change to commit, files, patch, commands or rules cancels the approval.</li>
              <li><strong>Baseline, then change.</strong> Approved tests run before the patch and again after it, so a failure that existed before is not blamed on the change.</li>
              <li><strong>Reduced exposure, honestly labelled.</strong> Commands run with secrets removed from the environment, a temporary home folder, a timeout and output limits; AFM's git calls disable hooks and fsmonitor. A workspace is <strong>not a sandbox</strong>: tests can still reach your files and network. A container mode with network off is planned for real isolation.</li>
              <li><strong>Honest results.</strong> Tests that fail, can't run or need missing services stay NOT VERIFIED; results you run yourself are labelled user-provided. You can add feedback without overwriting the original prediction.</li>
            </ul>
          </div>
        </div>

        <ArchitectureDiagram />
        <details className="glass-flat" style={{ padding: 12 }}>
          <summary className="small" style={{ cursor: "pointer" }}><strong>The 16 steps of every assessment in this prototype</strong></summary>
          <ol className="grid g4 mt" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {loop.map((s, i) => (
              <li key={i} className="glass-flat row" style={{ padding: "8px 10px", alignItems: "flex-start", flexWrap: "nowrap" }}><span className="mono accent small" style={{ minWidth: 22 }}>{i + 1}</span><span className="tiny">{s}</span></li>
            ))}
          </ol>
        </details>
      </Section>

      <Section id="sowhat" kicker="So what? The benefits" title="More informed decisions before changing a system">
        <Table caption="Benefits" head={["Potential benefit", "How ACFM supports it"]} rows={[
          ["Better visibility before change", "Shows which objects may be affected and why."],
          ["More informed decisions", "Compares possible plans, benefits, risks and trade-offs."],
          ["Human control", "Presents state-changing plans for review before execution, bound to the exact plan and state."],
          ["More honest AI behavior", "Separates observed facts, predictions and unknowns."],
          ["Measurable prediction quality", "Compares predictions with test results rather than relying only on explanations."],
          ["Learning from mistakes", "Records mismatches and human corrections for later analysis."],
          ["Reuse across environments", "Applies the same assessment to different systems through environment-specific adapters."],
        ]} />
        <p className="warn small">These are <strong>design goals</strong>. Their effectiveness must be measured through tests and real use cases. ACFM cannot guarantee that it has found every dependency or predicted every consequence.</p>
      </Section>

      <Section id="stack" kicker="What is the current stack?" title="A hybrid framework, not yet a trained ACFM model">
        <Table caption="Current stack" head={["Component", "Role", "In this prototype"]} rows={[
          ["Existing LLM", "Interprets goals, explains object types, proposes candidate plans", "Mock (offline), Claude, OpenAI-compatible cloud, or a local model such as Ollama; never decides"],
          ["ACFM controller", "Coordinates the assessment workflow", "16-step engine: task goal → Win (engine/service.py)"],
          ["Environment & object model", "Known objects, states, behavior, relationships", "Adapters with evidence labels (adapters/, engine/environment.py)"],
          ["Inspection tools & adapters", "Gather evidence from supported environments", "3 simulated adapters + read-only inspection of your real project (projects/)"],
          ["Consequence engine", "Predicts effects using rules, simulation and reasoning", "Deterministic, rule-based simulation on a copy (engine/simulator.py)"],
          ["Rules & permission checks", "Define and enforce boundaries", "32 pinned rules of conduct + environment + task rules; pre-check, policy versioning"],
          ["Human review", "Review state-changing plans", "Approval bound to plan hash, state and policy; rechecked before execution"],
          ["Test & observation tools", "Collect results after approved actions", "Simulated observation in playgrounds; real baseline and after test runs on your project"],
          ["Evaluator & experience history", "Compare predictions with outcomes; record feedback", "MATCH / MISMATCH / NOT VERIFIED, three-condition Win, local history"],
        ]} />
        <p className="small dim">Capabilities depend on the implemented adapters, tools and permissions: environments may be simulated, read-only, unsupported or not connected. Built with Python, FastAPI, Pydantic, SQLite, React, TypeScript and Vite, with 100 automated backend tests plus browser walk-throughs. This framework is <strong>not yet a newly trained ACFM foundation model</strong>: it is the system we use to explore the idea, test predictions and collect evidence.</p>
      </Section>

      <Section id="next" kicker="What comes next?" title="Using the framework to build a specialized ACFM model">
        <p>Our longer-term ambition is a <strong>specialized Action–Consequence Foresight model</strong> that learns to predict the effects of actions across objects and environments. The same framework helps us build it:</p>
        <ol className="grid g4" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {[["Run use cases", "real or simulated environments"], ["Record predictions", "what ACFM expected, before testing"], ["Observe results", "test outcomes and evidence"], ["Review mismatches", "humans validate or correct"],
            ["Build a dataset", "approved environment → action → consequence examples"], ["Train or adapt a model", "a specialized consequence predictor"], ["Evaluate on unseen cases", "vs baselines, projects not used in training"], ["Improve and repeat", "measured failures guide the next version"]].map(([t, d], i) => (
            <li key={t} className="glass-flat" style={{ padding: "10px 12px" }}><p className="row" style={{ gap: 8, flexWrap: "nowrap" }}><span className="step-n mono">{i + 1}</span><strong className="small">{t}</strong></p><p className="tiny dim mt-s">{d}</p></li>
          ))}
        </ol>
        <p className="hud-label mt">Three ways to build the predictor</p>
        <Table caption="Ways to build the predictor" head={["Approach", "What we build", "Data needed", "When"]} rows={[
          ["1 · Rule-based", "Explicit object behavior and consequence rules", "Designed scenarios and rules", "Now: the reliable baseline (what ACFM does today)"],
          ["2 · Adapt an existing model", "Fine-tune on reviewed action–consequence examples", "Quality examples + evaluation tasks", "Next, where the benchmark shows the baseline falls short"],
          ["3 · Train from scratch", "A new architecture for consequence prediction", "Substantial data, compute and research", "Long term, only if adaptation is not enough"],
        ]} />
        <p className="small">Recommendation: <strong>1 → 2</strong>. A model adapted and measured on the ACFM task is still <em>our</em> specialized predictor. It could be a fine-tuned LLM with structured output, a small model for one outcome (will this test fail?), or several specialists per environment type.</p>
        <p className="hud-label mt">Anatomy of a training example</p>
        <Table caption="Training example" head={["Field", "Content", "Example: require authentication on /orders"]} rows={[
          ["Input", "Project state, objects, relationships, proposed action", "/orders accepts unauthenticated requests; action: require authentication"],
          ["Original prediction", "Kept separately and never rewritten, so the error can be measured", "Unauthenticated requests rejected; existing client keeps working"],
          ["Observed result", "Approved test results", "Unauthenticated: rejected ✓ · existing client: fails (sends no credentials) ✕"],
          ["Target output", "Observed or human-verified consequence", "Authentication breaks the existing client unless it is updated to send credentials"],
          ["Evidence", "Tests, logs or code supporting the outcome", "Endpoint test output, client source"],
          ["Unknowns", "Effects not tested or verified", "Other clients may exist but were not inspected"],
        ]} />
        <p className="warn small"><strong>Untested ≠ no effect.</strong> An effect nobody tested stays <em>unknown</em> in the dataset; labelling it “no effect” would teach false lessons.</p>
        <LearningLoop />
        <p className="hud-label mt">How we will know it is better</p>
        <Table caption="Benchmark metrics" head={["Metric", "What it tells us"]} rows={[
          ["Consequence detection", "Did ACFM identify effects that actually occurred?"], ["Prediction correctness", "Were its predicted effects correct?"],
          ["Missed consequences", "Which observed effects did it fail to predict?"], ["False alarms", "Which predicted effects did not occur under test?"],
          ["Unknown handling", "Did it admit uncertainty when evidence was insufficient?"], ["Three-condition Win rate", "How often did prediction, goal and rules all pass?"],
        ]} />
        <p className="small">A focused first predictor: <strong>“Given a proposed Python code change, predict which existing tests or connected components may be affected.”</strong> Real-project mode produces exactly these examples. From there we test whether the approach generalizes to applications, infrastructure and business systems.</p>
        <section className="glass panel brackets mt">
          <p className="hud-label accent">Our ambition</p>
          <p className="mt-s">Make ACFM <strong>best in its class at action–consequence prediction</strong>. That is a research goal, not a claim about current performance. We will need transparent benchmarks, strong baselines and evidence from unseen tasks to know whether we achieve it.</p>
        </section>
      </Section>

      <section id="principle" className="glass panel brackets why-hero why-section" aria-label="Our principle">
        <p className="hud-label accent">Our principle</p>
        <blockquote className="why-quote">Know the goal. Understand the environment. Predict the consequences. Respect the rules. Ask before acting. Learn from what happens.</blockquote>
        <p className="row between mt"><strong>ACFM: see the domino effect before acting.</strong><span className="row"><a className="btn" href="#/project">Try it on your repo</a><a className="btn-primary" href="#/overview">Test it →</a></span></p>
      </section>
    </div>
  );
}
