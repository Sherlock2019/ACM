import type { EnvObject, Relationship } from "../types/afm";

const W = 180, H = 50;

function layout(objects: EnvObject[], fixed: Record<string, [number, number]>) {
  const pos: Record<string, [number, number]> = {};
  let extra = 0;
  for (const o of objects) pos[o.id] = fixed[o.id] ?? [150 + (extra++ % 4) * 220, 460];
  return pos;
}

function clip([cx, cy]: [number, number], [px, py]: [number, number]): [number, number] {
  const dx = px - cx, dy = py - cy;
  if (!dx && !dy) return [cx, cy];
  const s = Math.min(Math.abs((W / 2 + 4) / (dx || 1e-9)), Math.abs((H / 2 + 4) / (dy || 1e-9)));
  return [cx + dx * s, cy + dy * s];
}

/** Readable graph for small environments. `deltas` shows a predicted change under a node and highlights it. */
export function RelationshipGraph({ objects, relationships, layout: fixed, selected, onSelect, deltas = {}, warn = [] }: {
  objects: EnvObject[]; relationships: Relationship[]; layout: Record<string, [number, number]>; selected?: string | null;
  onSelect?: (id: string) => void; deltas?: Record<string, string>; warn?: string[];
}) {
  const pos = layout(objects, fixed);
  const ys = Object.values(pos).map((p) => p[1]);
  const height = Math.max(...ys, 100) + H / 2 + (Object.keys(deltas).length ? 40 : 20);
  const ids = new Set(objects.map((o) => o.id));
  return (
    <figure className="graph" style={{ margin: 0 }}>
      <svg viewBox={`0 0 960 ${height}`} role="img" aria-label="Relationship graph of known objects. The same information is in the list next to it.">
        <defs>
          <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="rgba(255,255,255,.45)" /></marker>
          <marker id="arr-hi" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--accent)" /></marker>
        </defs>
        {relationships.filter((r) => ids.has(r.source) && ids.has(r.target)).map((r) => {
          const a = pos[r.source], b = pos[r.target];
          const [x1, y1] = clip(a, b), [x2, y2] = clip(b, a);
          const hi = (selected != null && (r.source === selected || r.target === selected)) || (deltas[r.source] && deltas[r.target]);
          return (
            <g key={r.id}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} className={`edge ${r.evidence === "unknown" ? "unknown" : ""} ${hi ? "hi" : ""}`} markerEnd={`url(#${hi ? "arr-hi" : "arr"})`} />
              <text x={x1 + (x2 - x1) * 0.5} y={Math.abs(y2 - y1) < 10 ? y1 - H / 2 - 8 : y1 + (y2 - y1) * 0.5 - 6} textAnchor="middle" className="elabel">{r.type.replace(/_/g, " ")}</text>
            </g>
          );
        })}
        {objects.map((o) => {
          const [x, y] = pos[o.id];
          const sel = o.id === selected;
          const d = deltas[o.id];
          const w = warn.includes(o.id);
          return (
            <g key={o.id} className={`node ${sel ? "sel" : ""} ${d ? "changed" : ""}`} transform={`translate(${x - W / 2},${y - H / 2})`}
              tabIndex={onSelect ? 0 : -1} role={onSelect ? "button" : undefined} aria-pressed={onSelect ? sel : undefined}
              aria-label={`${o.name}, ${o.type.replace(/_/g, " ")}, evidence ${o.evidence}${d ? `, predicted ${d}` : ""}`}
              onClick={() => onSelect?.(o.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect?.(o.id); } }}
              style={{ cursor: onSelect ? "pointer" : "default" }}>
              <rect width={W} height={H} rx={10} strokeDasharray={o.evidence === "unknown" ? "5 4" : undefined}
                style={w ? { stroke: "var(--review)", strokeWidth: 2.2 } : d ? { stroke: "var(--accent)", strokeWidth: 2.2 } : undefined} />
              <text x={12} y={21} style={{ fontWeight: 600 }}>{o.name.length > 23 ? o.name.slice(0, 22) + "…" : o.name}</text>
              <text x={12} y={38} className="elabel" style={{ fontSize: 10 }}>{o.type.replace(/_/g, " ")} · {o.evidence}</text>
              {d && <text x={W / 2} y={H + 18} textAnchor="middle" className="delta-label" style={w ? { fill: "var(--review)" } : undefined}>{w ? "⚠ " : ""}{d}</text>}
            </g>
          );
        })}
      </svg>
      <figcaption className="faint tiny mt-s">Arrows point from source to target. Dashed means unknown, not verified.{Object.keys(deltas).length ? " Highlighted objects change in the prediction (amber = warning)." : ""}</figcaption>
    </figure>
  );
}
