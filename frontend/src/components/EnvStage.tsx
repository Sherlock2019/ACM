// A tiny 2D canvas engine that animates AFM's reasoning on the environment:
// the agent sends each planned action to its target object, then consequence waves travel along
// relationships to every affected object (green = benefit, amber = warning, grey "?" = unknown).
// Phases: idle (no plan) → predicted (awaiting review) → approved → executed (observed values ✓).
import { useEffect, useMemo, useRef, useState } from "react";
import type { EnvironmentView, Observation, PlanAssessment } from "../types/afm";
import { predictedDeltas } from "./PlanParts";

export type StagePhase = "idle" | "predicted" | "approved" | "executed" | "unsupported";

type V = { x: number; y: number };
interface Ev { kind: "action" | "wave" | "unknown"; from: string; to: string; t0: number; dur: number; effect: string; label?: string; step?: number }

const NODE_W = 150, NODE_H = 46, AGENT = "__agent__";
const ease = (t: number) => (t < 0 ? 0 : t > 1 ? 1 : 1 - Math.pow(1 - t, 3));

function cssVar(name: string, fallback: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function buildTimeline(a: PlanAssessment | null): { events: Ev[]; end: number } {
  if (!a) return { events: [], end: 0 };
  const events: Ev[] = [];
  let t = 0.5;
  const deltas = predictedDeltas(a);
  a.plan.actions.forEach((act, i) => {
    events.push({ kind: "action", from: AGENT, to: act.target_object_id, t0: t, dur: 0.9, effect: "action", label: `${i + 1}. ${act.tool}`, step: i + 1 });
    t += 1.0;
    const stepCons = a.simulation.consequences.filter((c) => c.step === i + 1 && c.affected_object_id !== act.target_object_id);
    stepCons.forEach((c, k) => {
      events.push({ kind: c.status === "unknown" ? "unknown" : "wave", from: act.target_object_id, to: c.affected_object_id, t0: t + k * 0.35, dur: 0.75,
        effect: c.status === "unknown" ? "unknown" : c.effect, label: deltas[c.affected_object_id] });
    });
    t += 0.4 + stepCons.length * 0.35;
  });
  return { events, end: t + 0.6 };
}

export function EnvStage({ view, assessment, phase, observation, envName, plans, selected, onSelect }: {
  view?: EnvironmentView; assessment: PlanAssessment | null; phase: StagePhase; observation?: Observation | null; envName: string;
  plans: { id: string; title: string }[]; selected: string | null; onSelect: (id: string) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [replayKey, setReplayKey] = useState(0);
  const timeline = useMemo(() => buildTimeline(phase === "idle" || phase === "unsupported" ? null : assessment), [assessment, phase]);
  const deltas = useMemo(() => (assessment ? predictedDeltas(assessment) : {}), [assessment]);
  const effectOf = useMemo(() => {
    const m: Record<string, string> = {};
    for (const c of assessment?.simulation.consequences ?? []) {
      const prev = m[c.affected_object_id];
      const e = c.status === "unknown" ? "unknown" : c.effect;
      if (!prev || e === "warning" || (e === "benefit" && prev !== "warning")) m[c.affected_object_id] = e;
    }
    return m;
  }, [assessment]);

  useEffect(() => {
    const canvas = canvasRef.current, wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext("2d")!;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const col = {
      bg: cssVar("--bg-2", "#0f1626"), text: cssVar("--text", "#e9edf3"), dim: "rgba(233,237,243,.55)", border: "rgba(255,255,255,.18)",
      accent: cssVar("--accent", "#34d1c4"), pass: cssVar("--pass", "#3fcf73"), warn: cssVar("--review", "#f5b83d"), fail: cssVar("--fail", "#ff6b6b"),
      unknown: cssVar("--unknown", "#a8b0c2"), blue: cssVar("--blue", "#6aa8ff"),
    };
    const effColor = (e?: string) => (e === "benefit" ? col.pass : e === "warning" ? col.warn : e === "unknown" ? col.unknown : e === "action" ? col.accent : col.blue);
    let W = 0, H = 0, raf = 0, NW = NODE_W;
    const objs = view?.objects ?? [];
    const lay = view?.layout ?? {};
    const xs = objs.map((o, i) => lay[o.id]?.[0] ?? 150 + (i % 4) * 220), ys = objs.map((o, i) => lay[o.id]?.[1] ?? 120 + Math.floor(i / 4) * 140);
    const minX = Math.min(...xs, 100), maxX = Math.max(...xs, 860), minY = Math.min(...ys, 50), maxY = Math.max(...ys, 200);
    const pos: Record<string, V> = {};
    const place = () => {
      const r = wrap.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      W = r.width; H = Math.max(300, Math.min(440, r.width * 0.62));
      canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.width = `${W}px`; canvas.style.height = `${H}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const cols = Math.max(1, new Set(xs.map((x) => Math.round(x / 40))).size);
      NW = Math.max(84, Math.min(NODE_W, (W - 28) / cols - 12)); // nodes shrink to fit narrow panels
      const padX = NW / 2 + 14, top = 108, bottom = H - NODE_H / 2 - 30;
      objs.forEach((o, i) => {
        const nx = maxX === minX ? 0.5 : (xs[i] - minX) / (maxX - minX), ny = maxY === minY ? 0.5 : (ys[i] - minY) / (maxY - minY);
        pos[o.id] = { x: padX + nx * (W - 2 * padX), y: top + ny * Math.max(0, bottom - top) };
      });
      pos[AGENT] = { x: 34, y: 44 };
    };
    place();
    const ro = new ResizeObserver(() => place());
    ro.observe(wrap);

    const roundRect = (x: number, y: number, w: number, h: number, r: number) => { ctx.beginPath(); ctx.roundRect(x, y, w, h, r); };
    const label = (txt: string, x: number, y: number, color: string, size = 11, weight = "600", align: CanvasTextAlign = "center") => {
      ctx.font = `${weight} ${size}px "JetBrains Mono", ui-monospace, monospace`; ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = "middle"; ctx.fillText(txt, x, y);
    };
    const short = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
    const obsByObj: Record<string, string> = {};
    for (const i of observation?.items ?? []) if (i.result !== "NOT VERIFIED" && !obsByObj[i.object_id]) obsByObj[i.object_id] = i.result;

    const start = performance.now();
    const frame = (now: number) => {
      const t = reduced ? timeline.end + 10 : (now - start) / 1000;
      ctx.clearRect(0, 0, W, H);
      // environment frame
      roundRect(6, 86, W - 12, H - 92, 14); ctx.fillStyle = "rgba(255,255,255,.025)"; ctx.fill(); ctx.strokeStyle = col.border; ctx.setLineDash([6, 5]); ctx.lineWidth = 1; ctx.stroke(); ctx.setLineDash([]);
      label(`${envName} · simulated`, 18, 100, col.dim, 10, "600", "left");
      if (phase === "unsupported" || !objs.length) {
        label("No adapter: AFM cannot see or draw this environment.", W / 2, H / 2 + 20, col.unknown, 12, "600");
        label("Nothing is inspected, simulated or executed here.", W / 2, H / 2 + 40, col.dim, 11, "400");
      }
      // relationships
      for (const r of view?.relationships ?? []) {
        const a = pos[r.source], b = pos[r.target];
        if (!a || !b) continue;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = r.evidence === "unknown" ? "rgba(168,176,194,.35)" : "rgba(255,255,255,.16)"; ctx.setLineDash(r.evidence === "unknown" ? [4, 5] : []); ctx.lineWidth = 1.2; ctx.stroke(); ctx.setLineDash([]);
      }
      // events: beams & waves
      const arrived: Record<string, { effect: string; label?: string; at: number }> = {};
      for (const e of timeline.events) {
        const a = pos[e.from], b = pos[e.to];
        if (!a || !b || t < e.t0) continue;
        const p = ease((t - e.t0) / e.dur);
        const c = effColor(e.effect);
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(a.x + (b.x - a.x) * p, a.y + (b.y - a.y) * p);
        ctx.strokeStyle = c; ctx.globalAlpha = phase === "predicted" ? 0.9 : 0.75; ctx.lineWidth = e.kind === "action" ? 3 : 2; ctx.setLineDash(e.kind === "unknown" ? [3, 5] : e.kind === "action" && phase === "predicted" ? [8, 6] : []);
        ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1;
        if (p < 1) { // travelling particle
          const px = a.x + (b.x - a.x) * p, py = a.y + (b.y - a.y) * p;
          ctx.beginPath(); ctx.arc(px, py, e.kind === "action" ? 6 : 4.5, 0, Math.PI * 2); ctx.fillStyle = c; ctx.shadowColor = c; ctx.shadowBlur = 14; ctx.fill(); ctx.shadowBlur = 0;
          if (e.kind === "action" && e.label) label(e.label, (a.x + px) / 2 + 8, (a.y + py) / 2 - 10, col.accent, 10, "700", "left");
        } else {
          const since = t - e.t0 - e.dur;
          if (since < 0.9 && !reduced) { // arrival ripple
            ctx.beginPath(); ctx.arc(b.x, b.y, 18 + since * 60, 0, Math.PI * 2); ctx.strokeStyle = c; ctx.globalAlpha = 1 - since / 0.9; ctx.lineWidth = 2; ctx.stroke(); ctx.globalAlpha = 1;
          }
          const prev = arrived[e.to];
          if (!prev || e.effect === "warning" || (e.kind === "action" && !prev)) arrived[e.to] = { effect: e.kind === "action" ? (effectOf[e.to] ?? "action") : e.effect, label: e.label, at: e.t0 + e.dur };
        }
      }
      // objects
      for (const o of objs) {
        const v = pos[o.id]; if (!v) continue;
        const hit = arrived[o.id];
        const done = phase === "executed";
        const eff = hit ? (hit.effect === "action" ? effectOf[o.id] ?? "action" : hit.effect) : undefined;
        const stroke = done && obsByObj[o.id] ? (obsByObj[o.id] === "MATCH" ? col.pass : col.fail) : eff ? effColor(eff) : o.evidence === "unknown" ? "rgba(168,176,194,.5)" : col.border;
        roundRect(v.x - NW / 2, v.y - NODE_H / 2, NW, NODE_H, 10);
        ctx.fillStyle = col.bg; ctx.fill(); ctx.lineWidth = eff || done ? 2.2 : 1.2; ctx.strokeStyle = stroke; ctx.setLineDash(o.evidence === "unknown" ? [5, 4] : []); ctx.stroke(); ctx.setLineDash([]);
        const fs = NW < 120 ? 10 : 11.5;
        label(short(o.name, Math.floor(NW / (fs * 0.62))), v.x, v.y - 8, col.text, fs, "700");
        const scalar = Object.entries(o.state).find(([, x]) => typeof x !== "object");
        const base = o.evidence === "unknown" ? "unknown · not simulated" : scalar ? `${scalar[0].replace(/_/g, " ")}: ${String(scalar[1])}` : o.type.replace(/_/g, " ");
        const showDelta = hit && (deltas[o.id] || hit.effect === "unknown");
        label(short(showDelta ? (hit.effect === "unknown" ? "? unknown effect" : deltas[o.id]) : base, Math.floor(NW / 6.2)), v.x, v.y + 10, showDelta ? effColor(eff) : col.dim, 9.5, showDelta ? "700" : "500");
        if (done && obsByObj[o.id]) label(obsByObj[o.id] === "MATCH" ? "✓ observed" : "✕ differs", v.x, v.y + NODE_H / 2 + 11, obsByObj[o.id] === "MATCH" ? col.pass : col.fail, 10, "700");
      }
      // agent
      const ag = pos[AGENT];
      const bob = reduced ? 0 : Math.sin(now / 500) * 2;
      ctx.beginPath(); ctx.arc(ag.x, ag.y + bob, 22, 0, Math.PI * 2); ctx.fillStyle = "rgba(52,209,196,.14)"; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = col.accent; ctx.stroke();
      ctx.beginPath(); ctx.arc(ag.x, ag.y + bob, 6, 0, Math.PI * 2); ctx.fillStyle = col.text; ctx.fill();
      label("AFM agent", ag.x + 34, ag.y + bob - 6, col.accent, 11, "700", "left");
      const finished = t > timeline.end;
      const status = phase === "idle" ? "no plan yet: run the simulation" : phase === "unsupported" ? "not connected"
        : phase === "predicted" ? (finished ? "prediction ready · ⏸ awaiting your approval" : "simulating on a copy…") : phase === "approved" ? "approved · ready to execute once" : "executed in simulation · observed";
      label(short(status, Math.floor((W - ag.x - 44) / 6.2)), ag.x + 34, ag.y + bob + 10, phase === "predicted" && finished ? col.warn : col.dim, 10, "600", "left");
      if (!reduced) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, [view, timeline, phase, observation, envName, deltas, effectOf, replayKey]);

  const nm = (id: string) => view?.objects.find((o) => o.id === id)?.name ?? id;
  const narration = timeline.events.map((e) => e.kind === "action" ? `AFM applies ${e.label} to ${nm(e.to)}.` : `${e.kind === "unknown" ? "Unknown effect on" : "Consequence reaches"} ${nm(e.to)}${e.label ? `: ${e.label}` : ""} (${e.effect}).`);
  return (
    <section className="glass panel stage" aria-label="Environment animation">
      <div className="row between">
        <h2 className="hud-label accent">Environment · live 2D view</h2>
        <div className="row" style={{ gap: 6 }} role="group" aria-label="Plan to animate">
          {plans.map((p) => <button key={p.id} className="chip" style={{ cursor: "pointer", ...(p.id === selected ? { borderColor: "var(--accent)", color: "var(--accent)" } : {}) }} aria-pressed={p.id === selected} onClick={() => onSelect(p.id)} title={p.title}>{p.id}</button>)}
          {timeline.events.length > 0 && <button className="chip" style={{ cursor: "pointer" }} onClick={() => setReplayKey((k) => k + 1)}>↻ replay</button>}
        </div>
      </div>
      <div ref={wrapRef} className="mt-s"><canvas ref={canvasRef} role="img" aria-label={`Animated view of ${envName}: ${phase === "idle" ? "current state, no plan yet" : narration.join(" ")}`} /></div>
      <div className="row tiny mt-s" style={{ gap: 12 }} aria-hidden="true">
        <span><span style={{ color: "var(--accent)" }}>●</span> AFM action</span><span><span style={{ color: "var(--pass)" }}>●</span> benefit</span>
        <span><span style={{ color: "var(--review)" }}>●</span> warning</span><span><span style={{ color: "var(--blue)" }}>●</span> neutral change</span><span><span style={{ color: "var(--unknown)" }}>●</span> unknown</span>
      </div>
      {narration.length > 0 && <details className="mt-s"><summary className="tiny dim" style={{ cursor: "pointer" }}>Animation as text</summary><ol className="bullets tiny mt-s">{narration.map((n, i) => <li key={i}>{n}</li>)}</ol></details>}
    </section>
  );
}
