// The consequence cascade: one action fires a pulse through a neural field of connected objects.
// Each synapse is a track of dominoes; as they topple, the next object lights up with the consequence
// ACFM predicts for it (intended, conditional, harmful or unknown). Canvas only, theme-aware, and
// reduced-motion safe (shows the final predicted state, no movement). Severity is never colour alone:
// every node carries a symbol and a sentence, and the full cascade is also listed for screen readers.
import { useEffect, useRef, useState } from "react";

type Sev = "action" | "ok" | "warn" | "bad" | "unknown";
interface CNode { id: string; label: string; sub: string; x: number; y: number; sev: Sev }
interface Scenario {
  kicker: string; title: string; goal: string;
  nodes: CNode[]; edges: [string, string][];
  verdict: { tone: "ok" | "warn" | "bad"; title: string; text: string };
}

// Desktop layout lives on a 1000 × 440 grid; the mobile layout is derived by transposing it.
const SCENARIOS: Scenario[] = [
  {
    kicker: "Plan A", title: "Change only the application port", goal: "Move the app from port 8000 to 9000 and keep it reachable.",
    nodes: [
      { id: "act", label: "Action", sub: "set PORT=9000", x: 90, y: 220, sev: "action" },
      { id: "cfg", label: "App config", sub: "port 8000 → 9000", x: 280, y: 220, sev: "ok" },
      { id: "app", label: "App process", sub: "now listens on 9000", x: 470, y: 120, sev: "ok" },
      { id: "mon", label: "Health monitor", sub: "still checks port 8000", x: 470, y: 330, sev: "bad" },
      { id: "proxy", label: "Web server", sub: "still forwards to 8000", x: 680, y: 120, sev: "bad" },
      { id: "page", label: "On-call engineer", sub: "paged by a false outage", x: 680, y: 330, sev: "warn" },
      { id: "users", label: "Users", sub: "502 Bad Gateway", x: 890, y: 120, sev: "bad" },
      { id: "other", label: "Other clients", sub: "not inspected: unknown", x: 890, y: 290, sev: "unknown" },
    ],
    edges: [["act", "cfg"], ["cfg", "app"], ["cfg", "mon"], ["app", "proxy"], ["mon", "page"], ["proxy", "users"], ["proxy", "other"]],
    verdict: { tone: "bad", title: "Not safe: 3 harmful consequences predicted", text: "Predicted before anything ran: users lose access, health checks fail and on-call is paged. ACFM recommends Plan B." },
  },
  {
    kicker: "Plan B", title: "Change the app and its known dependents", goal: "Same goal. ACFM also updates the web server and the health monitor.",
    nodes: [
      { id: "act", label: "Action", sub: "PORT=9000 + dependents", x: 90, y: 220, sev: "action" },
      { id: "cfg", label: "App config", sub: "port 8000 → 9000", x: 280, y: 220, sev: "ok" },
      { id: "app", label: "App process", sub: "now listens on 9000", x: 470, y: 120, sev: "ok" },
      { id: "mon", label: "Health monitor", sub: "now checks port 9000", x: 470, y: 330, sev: "ok" },
      { id: "proxy", label: "Web server", sub: "now forwards to 9000", x: 680, y: 120, sev: "ok" },
      { id: "page", label: "On-call engineer", sub: "no alert", x: 680, y: 330, sev: "ok" },
      { id: "users", label: "Users", sub: "still reach the app", x: 890, y: 120, sev: "ok" },
      { id: "other", label: "Other clients", sub: "flagged for a human", x: 890, y: 290, sev: "unknown" },
    ],
    edges: [["act", "cfg"], ["cfg", "app"], ["cfg", "mon"], ["app", "proxy"], ["mon", "page"], ["proxy", "users"], ["proxy", "other"]],
    verdict: { tone: "ok", title: "Recommended: goal met, rules respected", text: "Every predicted effect is intended. One unknown is flagged for a human instead of guessed. Approval is bound to this exact plan." },
  },
  {
    kicker: "Security change", title: "Require authentication on /orders", goal: "Improve the security of the orders API without breaking the existing client.",
    nodes: [
      { id: "act", label: "Action", sub: "require auth on /orders", x: 90, y: 220, sev: "action" },
      { id: "ep", label: "/orders endpoint", sub: "authentication required", x: 280, y: 220, sev: "ok" },
      { id: "anon", label: "Anonymous calls", sub: "rejected with 401", x: 470, y: 120, sev: "ok" },
      { id: "client", label: "Existing client", sub: "sends no credentials: fails", x: 470, y: 330, sev: "bad" },
      { id: "tests", label: "Test suite", sub: "test_orders: fail → pass", x: 680, y: 120, sev: "ok" },
      { id: "dash", label: "Orders dashboard", sub: "shows no new orders", x: 680, y: 330, sev: "warn" },
      { id: "other", label: "Other clients", sub: "not inspected: unknown", x: 890, y: 330, sev: "unknown" },
    ],
    edges: [["act", "ep"], ["ep", "anon"], ["ep", "client"], ["anon", "tests"], ["client", "dash"], ["dash", "other"]],
    verdict: { tone: "warn", title: "Conditional: update the client first", text: "The security goal is met, but the existing client breaks unless it sends credentials. ACFM proposes a plan that updates it too, then asks a human." },
  },
];

const STEP = 1.15, LEAD = 0.6, HOLD = 5.5, R = 22;
const SYMBOL: Record<Sev, string> = { action: "▶", ok: "✓", warn: "!", bad: "✕", unknown: "?" };
const SEV_WORD: Record<Sev, string> = { action: "action", ok: "intended", warn: "conditional", bad: "harmful", unknown: "unknown" };

interface TEdge { a: CNode; b: CNode; start: number; dur: number }
interface Timeline { edges: TEdge[]; act: Record<string, number>; end: number }

function timeline(s: Scenario): Timeline {
  const byId = Object.fromEntries(s.nodes.map((n) => [n.id, n]));
  const root = s.nodes[0].id;
  const depth: Record<string, number> = { [root]: 0 };
  const queue = [root];
  while (queue.length) {
    const u = queue.shift()!;
    for (const [a, b] of s.edges) if (a === u && depth[b] === undefined) { depth[b] = depth[u] + 1; queue.push(b); }
  }
  const act: Record<string, number> = { [root]: LEAD * 0.4 };
  const edges = s.edges.map(([a, b]) => {
    const start = LEAD + depth[a] * STEP, dur = STEP * 0.86;
    act[b] = start + dur;
    return { a: byId[a], b: byId[b], start, dur };
  });
  return { edges, act, end: Math.max(...Object.values(act)) + 0.5 };
}
const TIMELINES = SCENARIOS.map(timeline);

interface Colors { text: string; faint: string; bg2: string; sev: Record<Sev, string>; neurons: string[] }
function readColors(): Colors {
  const cs = getComputedStyle(document.documentElement);
  const g = (k: string, d: string) => cs.getPropertyValue(k).trim() || d;
  return {
    text: g("--text", "#e9edf3"), faint: g("--text-faint", "rgba(233,237,243,.5)"), bg2: g("--bg-2", "#0f1626"),
    sev: { action: g("--accent", "#34d1c4"), ok: g("--pass", "#3fcf73"), warn: g("--review", "#f5b83d"), bad: g("--fail", "#ff6b6b"), unknown: g("--unknown", "#a8b0c2") },
    neurons: [g("--n1", "#34d1c4"), g("--n2", "#6aa8ff"), g("--n3", "#8fa3c8"), g("--n4", "#f0b44c")],
  };
}

interface Particle { x: number; y: number; vx: number; vy: number; r: number; c: number }
interface Spark { x: number; y: number; vx: number; vy: number; life: number; color: string }

const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const easeIn = (p: number) => p * p;
const easeOut = (p: number) => 1 - (1 - p) * (1 - p);

function wrapText(ctx: CanvasRenderingContext2D, text: string, max: number): string[] {
  const words = text.split(" "), lines: string[] = [];
  let line = "";
  for (const w of words) {
    const next = line ? `${line} ${w}` : w;
    if (ctx.measureText(next).width > max && line) { lines.push(line); line = w; } else line = next;
  }
  if (line) lines.push(line);
  return lines.slice(0, 2);
}

function prefersReduced() {
  try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; }
}

export function ConsequenceCascade() {
  const [reduced] = useState(prefersReduced);
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const [auto, setAuto] = useState(!reduced);
  const [done, setDone] = useState(reduced);
  const [run, setRun] = useState(0);
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const st = useRef({ t: 0, idx: 0, paused: false, auto: !reduced, done: reduced, visible: true, redraw: true });

  useEffect(() => {
    Object.assign(st.current, { t: reduced ? 1e3 : 0, idx, done: reduced, redraw: true });
    setDone(reduced);
  }, [idx, run, reduced]);
  useEffect(() => { st.current.paused = paused; st.current.auto = auto; }, [paused, auto]);

  useEffect(() => {
    const cv = canvas.current, box = wrap.current;
    if (!cv || !box) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    let colors = readColors();
    let W = 1000, H = 440, mobile = false, scale = 1, raf = 0, last = performance.now();
    let particles: Particle[] = [];
    let sparks: Spark[] = [];

    // mobile: transpose the desktop grid so the cascade flows top to bottom
    const pos = (n: CNode) => mobile
      ? { x: 70 + ((n.y - 120) / 210) * 280, y: 50 + ((n.x - 90) / 800) * 740 }
      : { x: n.x, y: n.y };

    const seed = () => {
      const count = Math.min(130, Math.round((W * H) / 3600));
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - 0.5) * 0.25, vy: (Math.random() - 0.5) * 0.25,
        r: 0.8 + Math.random() * 1.8, c: Math.floor(Math.random() * 4),
      }));
    };

    const resize = () => {
      const cw = box.clientWidth || 1000;
      const nextMobile = cw < 620;
      const dimsChanged = nextMobile !== mobile || !particles.length;
      mobile = nextMobile;
      W = mobile ? 420 : 1000; H = mobile ? 880 : 440;
      scale = cw / W;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      cv.style.height = `${H * scale}px`;
      cv.width = Math.round(cw * dpr); cv.height = Math.round(H * scale * dpr);
      ctx.setTransform(dpr * scale, 0, 0, dpr * scale, 0, 0);
      if (dimsChanged) seed();
      st.current.redraw = true;
    };

    const drawField = (dt: number) => {
      const LINK = mobile ? 90 : 110;
      for (const p of particles) {
        if (!reduced) { p.x += p.vx * dt * 60; p.y += p.vy * dt * 60; }
        if (p.x < -10) p.x = W + 10; else if (p.x > W + 10) p.x = -10;
        if (p.y < -10) p.y = H + 10; else if (p.y > H + 10) p.y = -10;
      }
      ctx.lineWidth = 0.6;
      for (let i = 0; i < particles.length; i++) {
        const a = particles[i];
        for (let j = i + 1; j < particles.length; j++) {
          const b = particles[j], dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
          if (d2 < LINK * LINK) {
            ctx.globalAlpha = (1 - Math.sqrt(d2) / LINK) * 0.22;
            ctx.strokeStyle = colors.neurons[a.c];
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
      }
      for (const p of particles) {
        ctx.globalAlpha = 0.55; ctx.fillStyle = colors.neurons[p.c];
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;
    };

    const drawDomino = (x: number, y: number, dir: number, prog: number, color: string, h: number) => {
      const w = 5;
      ctx.save();
      ctx.translate(x + (dir * w) / 2, y + h / 2);
      ctx.rotate(easeIn(prog) * 1.2 * dir);
      ctx.fillStyle = prog > 0 ? color : colors.faint;
      ctx.globalAlpha = prog > 0 ? 0.95 : 0.45;
      if (prog > 0 && prog < 1) { ctx.shadowColor = color; ctx.shadowBlur = 10; }
      ctx.beginPath();
      ctx.roundRect(dir > 0 ? -w : 0, -h, w, h, 1.5);
      ctx.fill();
      ctx.restore();
    };

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const s = st.current;
      if (!s.visible) return;
      if (reduced && !s.redraw) return;
      s.redraw = false;
      const prevT = s.t;
      if (!s.paused && !reduced) s.t += dt;
      const t = s.t;
      const scen = SCENARIOS[s.idx], tl = TIMELINES[s.idx];

      ctx.clearRect(0, 0, W, H);
      drawField(s.paused ? 0 : dt);

      // synapses: a faint track, a coloured trace once crossed, dominoes, then the travelling pulse
      const DH = mobile ? 15 : 17;
      for (const e of tl.edges) {
        const A = pos(e.a), B = pos(e.b);
        const dx = B.x - A.x, dy = B.y - A.y, len = Math.hypot(dx, dy), ux = dx / len, uy = dy / len;
        // labels sit under each node, so a track leaving downwards starts below the label
        const out = R + 8 + (uy > 0.3 ? (mobile ? 46 : 52) : 0);
        const sx = A.x + ux * out, sy = A.y + uy * out, ex = B.x - ux * (R + 8), ey = B.y - uy * (R + 8);
        const span = Math.hypot(ex - sx, ey - sy);
        const q = clamp((t - e.start) / e.dur);
        const color = colors.sev[e.b.sev];
        ctx.lineWidth = 1.2; ctx.globalAlpha = 0.22; ctx.strokeStyle = colors.faint;
        if (e.b.sev === "unknown") ctx.setLineDash([4, 5]);
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(ex, ey); ctx.stroke();
        if (q > 0) {
          ctx.globalAlpha = 0.6; ctx.strokeStyle = color; ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(sx + (ex - sx) * q, sy + (ey - sy) * q); ctx.stroke();
        }
        ctx.setLineDash([]); ctx.globalAlpha = 1;
        const n = Math.max(3, Math.min(9, Math.floor(span / 22)));
        const dir = Math.abs(dx) < 1 ? 1 : Math.sign(dx);
        for (let i = 0; i < n; i++) {
          const f = (i + 1) / (n + 1);
          const fall = e.start + e.dur * f;
          drawDomino(sx + (ex - sx) * f, sy + (ey - sy) * f - DH / 2, dir, clamp((t - fall) / 0.24), color, DH);
        }
        if (q > 0 && q < 1) {
          for (let k = 0; k < 6; k++) {
            const qq = q - k * 0.025;
            if (qq < 0) break;
            ctx.globalAlpha = (1 - k / 6) * 0.9; ctx.fillStyle = color;
            ctx.beginPath(); ctx.arc(sx + (ex - sx) * qq, sy + (ey - sy) * qq, 4.2 - k * 0.55, 0, Math.PI * 2); ctx.fill();
          }
          ctx.globalAlpha = 1;
        }
      }

      // neurons (objects)
      for (const node of scen.nodes) {
        const P = pos(node), at = tl.act[node.id] ?? 0, since = t - at, on = since >= 0;
        const color = colors.sev[node.sev], a = clamp(since / 0.35);
        if (prevT < at && t >= at && !reduced) {
          for (let k = 0; k < 16; k++) {
            const ang = (k / 16) * Math.PI * 2 + Math.random() * 0.3, sp = 40 + Math.random() * 70;
            sparks.push({ x: P.x, y: P.y, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp, life: 1, color });
          }
        }
        if (on && since < 1.6 && !reduced) {
          const p = since / 1.6;
          ctx.globalAlpha = (1 - p) * 0.7; ctx.strokeStyle = color; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(P.x, P.y, R + easeOut(p) * 46, 0, Math.PI * 2); ctx.stroke();
          ctx.globalAlpha = 1;
        }
        ctx.save();
        if (on) { ctx.shadowColor = color; ctx.shadowBlur = 22 * a; }
        const grad = ctx.createRadialGradient(P.x, P.y, 2, P.x, P.y, R);
        grad.addColorStop(0, on ? color : colors.bg2);
        grad.addColorStop(1, colors.bg2);
        ctx.globalAlpha = on ? 0.35 + 0.65 * a : 1;
        ctx.fillStyle = grad;
        ctx.beginPath(); ctx.arc(P.x, P.y, R, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
        ctx.lineWidth = on ? 2 : 1.2; ctx.strokeStyle = on ? color : colors.faint;
        if (node.sev === "unknown") ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.arc(P.x, P.y, R, 0, Math.PI * 2); ctx.stroke();
        ctx.setLineDash([]);
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillStyle = on ? colors.text : colors.faint;
        ctx.font = `700 ${node.sev === "action" ? 14 : 16}px Inter, system-ui, sans-serif`;
        ctx.fillText(on ? SYMBOL[node.sev] : "·", P.x, P.y + 1);
        ctx.textBaseline = "alphabetic";
        ctx.globalAlpha = on ? 1 : 0.6; ctx.fillStyle = colors.text;
        const fl = mobile ? 15 : 13, fs = mobile ? 13.5 : 11.5; // larger on phones, where the canvas is scaled down
        ctx.font = `600 ${fl}px Inter, system-ui, sans-serif`;
        ctx.fillText(node.label, P.x, P.y + R + 18);
        if (on || node.sev === "action") {
          ctx.globalAlpha = node.sev === "action" ? 1 : a;
          ctx.fillStyle = color; ctx.font = `500 ${fs}px Inter, system-ui, sans-serif`;
          wrapText(ctx, node.sub, mobile ? 140 : 170).forEach((ln, i) => ctx.fillText(ln, P.x, P.y + R + 20 + fl + i * (fs + 3)));
        }
        ctx.globalAlpha = 1;
      }

      // sparks
      if (sparks.length) {
        for (const sp of sparks) { sp.x += sp.vx * dt; sp.y += sp.vy * dt; sp.vx *= 0.94; sp.vy *= 0.94; sp.life -= dt * 1.2; }
        sparks = sparks.filter((sp) => sp.life > 0);
        for (const sp of sparks) { ctx.globalAlpha = sp.life * 0.9; ctx.fillStyle = sp.color; ctx.beginPath(); ctx.arc(sp.x, sp.y, 1.8, 0, Math.PI * 2); ctx.fill(); }
        ctx.globalAlpha = 1;
      }

      if (!s.done && t >= tl.end) { s.done = true; setDone(true); }
      if (s.done && s.auto && !s.paused && t >= tl.end + HOLD) { s.t = 0; setIdx((i) => (i + 1) % SCENARIOS.length); }
    };

    const ro = new ResizeObserver(resize);
    ro.observe(box);
    const io = new IntersectionObserver(([en]) => { st.current.visible = en.isIntersecting; st.current.redraw = true; last = performance.now(); });
    io.observe(box);
    const mo = new MutationObserver(() => { colors = readColors(); st.current.redraw = true; });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    resize();
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); mo.disconnect(); };
  }, [reduced]);

  const scen = SCENARIOS[idx];
  const goTo = (i: number) => { setAuto(false); setPaused(false); setIdx((i + SCENARIOS.length) % SCENARIOS.length); setRun((r) => r + 1); };

  return (
    <figure className="cascade" aria-labelledby="cascade-title">
      <div className="cascade-head">
        <div>
          <p className="hud-label accent">Watch ACFM foresee the domino effect · {scen.kicker}</p>
          <p id="cascade-title" className="cascade-title">{scen.title}</p>
          <p className="small dim">Goal: {scen.goal}</p>
        </div>
        <ul className="cascade-legend" aria-label="Legend">
          {(["ok", "warn", "bad", "unknown"] as Sev[]).map((k) => <li key={k} className={`lg-${k}`}><span aria-hidden="true">{SYMBOL[k]}</span>{SEV_WORD[k]}</li>)}
        </ul>
      </div>
      <div ref={wrap} className="cascade-stage">
        <canvas ref={canvas} role="img" aria-label={`Animated prediction for "${scen.title}": one action topples a chain of dominoes through the connected objects.`} />
        <div className={`verdict verdict-${scen.verdict.tone}${done ? " show" : ""}`} aria-live="polite">
          {done && <><strong>{scen.verdict.title}</strong><span>{scen.verdict.text}</span></>}
        </div>
      </div>
      <ol className="sr-only">
        {scen.nodes.map((n) => <li key={n.id}>{n.label}: {n.sub} ({SEV_WORD[n.sev]})</li>)}
      </ol>
      <div className="cascade-bar" role="group" aria-label="Cascade controls">
        <button type="button" className="round-btn" onClick={() => goTo(idx - 1)} aria-label="Previous scenario">‹</button>
        <span className="dots">
          {SCENARIOS.map((s, i) => (
            <button type="button" key={s.title} className="dot" aria-current={i === idx ? "step" : undefined} aria-label={`${s.kicker}: ${s.title}`} onClick={() => goTo(i)} />
          ))}
        </span>
        <button type="button" className="round-btn" onClick={() => goTo(idx + 1)} aria-label="Next scenario">›</button>
        {!reduced && (
          <button type="button" className="round-btn" onClick={() => setPaused((p) => !p)} aria-label={paused ? "Play" : "Pause"} aria-pressed={paused}>
            {paused ? "▶" : "❚❚"}
          </button>
        )}
        <span className="mono small dim">{idx + 1} / {SCENARIOS.length}</span>
        {!reduced && <button type="button" className="pill-btn" onClick={() => { setPaused(false); setRun((r) => r + 1); }}>↻ Replay</button>}
      </div>
    </figure>
  );
}
