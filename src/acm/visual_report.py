"""A self-contained HTML report of the multimodal demo: no scripts, no network.

Sections: input, MLM meaning (with entity ids and evidence), proposed action,
initial vs predicted scene per alternative (with movement arrows), ARM circles,
assumptions and unknowns, and the prediction-vs-outcome comparison. Every value
carries a text label - OBSERVED, INFERRED, ASSUMED, PREDICTED, UNKNOWN - so
nothing depends on colour alone. Future scenes are labelled simulated.
"""

from __future__ import annotations

import html
import json
from typing import Any

STATUS_COLOURS = {
    "observed": "#166534", "inferred": "#1d4ed8", "assumed": "#a16207",
    "predicted": "#7e22ce", "unknown": "#475569", "simulation": "#7e22ce", "rule": "#0f766e",
}
TABLE = (0.0, 0.0, 1.2, 0.8)


def _e(text: Any) -> str:
    return html.escape("" if text is None else str(text))


def chip(status: str) -> str:
    colour = STATUS_COLOURS.get(status, "#334155")
    return f'<span class="chip" style="border-color:{colour};color:{colour}">{_e(status.upper())}</span>'


def scene_svg(scene: dict[str, Any], final: dict[str, Any] | None = None, title: str = "") -> str:
    """Top-down tabletop, world metres -> 300 px per metre. ``final`` overlays predicted positions."""
    s, pad = 300, 30
    W, H = int((TABLE[2] + 0.35) * s) + 2 * pad, int(TABLE[3] * s) + 2 * pad + 20

    def X(x: float) -> float:
        return pad + x * s

    def Y(y: float) -> float:
        return pad + y * s

    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{_e(title)}">',
             f'<rect x="{X(TABLE[2])}" y="{pad}" width="{0.35 * s}" height="{TABLE[3] * s}" fill="#e2e8f0"/>',
             f'<text x="{X(TABLE[2]) + 6}" y="{pad + 14}" font-size="11" fill="#475569">floor_01 (assumed)</text>',
             f'<rect x="{X(0)}" y="{Y(0)}" width="{TABLE[2] * s}" height="{TABLE[3] * s}" fill="#e9d5b0" stroke="#7c5a2a" stroke-width="3"/>',
             f'<text x="{X(0) + 6}" y="{Y(0) + 14}" font-size="11" fill="#5b3f17">table_01</text>']
    colours = {"blue_cup_01": "#2563eb", "red_cup_01": "#dc2626"}
    for ent in scene["entities"]:
        if ent["position"] is None or ent["class"] == "table":
            continue
        x, y = ent["position"]
        r = (ent["radius_m"] or 0.04) * s
        fill = colours.get(ent["id"], "#64748b")
        moved = final is not None and ent["id"] in final and final[ent["id"]] != [x, y]
        style = 'fill-opacity="0.25" stroke-dasharray="4 3"' if moved else ""
        if ent["class"] in {"pusher", "person"}:
            parts.append(f'<rect x="{X(x) - 0.04 * s}" y="{Y(y) - 0.05 * s}" width="{0.08 * s}" height="{0.10 * s}" fill="#334155" {style}/>')
        else:
            parts.append(f'<circle cx="{X(x)}" cy="{Y(y)}" r="{r}" fill="{fill}" stroke="#0f172a" {style}/>')
        parts.append(f'<text x="{X(x)}" y="{Y(y) + r + 12}" font-size="10" text-anchor="middle">{_e(ent["id"])}</text>')
        if moved:
            end = final[ent["id"]]
            if end is None:
                parts.append(f'<line x1="{X(x)}" y1="{Y(y)}" x2="{X(TABLE[2]) + 0.18 * s}" y2="{Y(y)}" stroke="#7e22ce" '
                             'stroke-width="2" marker-end="url(#arr)"/>')
                parts.append(f'<text x="{X(TABLE[2]) + 0.02 * s}" y="{Y(y) + 30}" font-size="10" fill="#7e22ce">'
                             'falls - landing position UNKNOWN</text>')
            else:
                parts.append(f'<line x1="{X(x)}" y1="{Y(y)}" x2="{X(end[0])}" y2="{Y(end[1])}" stroke="#7e22ce" '
                             'stroke-width="2" marker-end="url(#arr)"/>')
                parts.append(f'<circle cx="{X(end[0])}" cy="{Y(end[1])}" r="{r}" fill="{fill}" stroke="#7e22ce" stroke-width="2"/>')
    parts.append('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
                 'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#7e22ce"/></marker></defs>')
    parts.append(f'<text x="{pad}" y="{H - 6}" font-size="11" fill="#334155">{_e(title)}</text></svg>')
    return "".join(parts)


def _meaning_table(meaning: dict[str, Any]) -> str:
    rows = []
    for key in ("who", "action", "what", "to_whom", "where", "direction", "when", "how", "why"):
        field = meaning.get(key)
        if not field:
            continue
        rows.append(f"<tr><th>{_e(key.replace('_', ' ').upper())}</th><td>{_e(field['value'] or '—')}</td>"
                    f"<td>{chip(field['status'])}</td><td>{_e(field['source'])}</td></tr>")
    states = "".join(f"<li>{chip(s['status'])} {_e(s['text'])} <small>({_e(s['source'])})</small></li>"
                     for s in meaning.get("observed_states", []))
    rejected = "".join(f"<li>{chip('unknown')} {_e(r['claim'])} — {_e(r['reason'])}</li>"
                       for r in meaning.get("rejected_claims", []))
    return (f"<p><b>{_e(meaning['evidence_kind'])}</b></p><table>{''.join(rows)}</table>"
            f"<h4>States</h4><ul>{states}</ul>" + (f"<h4>Rejected claims</h4><ul>{rejected}</ul>" if rejected else ""))


def _circles(circles: list[dict[str, Any]]) -> str:
    cards = []
    for circle in circles:
        rows = "".join(f"<li>{chip(r.get('basis', 'rule'))} <b>{_e(r['about'])}</b>: {_e(r['text'])}</li>" for r in circle["rows"])
        body = f"<ul>{rows}</ul>" if rows else f"<p class='empty'>{_e(circle['empty'])}</p>"
        cards.append(f"<div class='card'><h4>{_e(circle['title'])}</h4>{body}</div>")
    return f"<div class='grid'>{''.join(cards)}</div>"


def render_report(demo: dict[str, Any]) -> str:
    sections = []
    for flow in ("text", "image", "video"):
        data = demo["flows"][flow]
        scene = data["scene"]
        alt = "".join(
            f"<div class='card'><h4>{_e(sc['label'])}</h4>"
            f"{scene_svg(scene, sc['final_positions'], 'SIMULATED / PREDICTED - illustrative simulation')}"
            f"<p>{' '.join(chip('predicted') + ' ' + _e(ev['kind']) + ':' + _e(ev['entity_id']) for ev in sc['events'])}</p></div>"
            for sc in data["scenarios"].values()
        )
        push = data["scenarios"]["push_edge"]
        assumptions = "".join(f"<li>{chip('assumed')} {_e(a['name'])}"
                              + (f" = {_e(a['value'])} {_e(a['unit'] or '')}" if a.get("value") is not None else "")
                              + f" — {_e(a['reason'])}</li>" for a in push["assumptions"])
        unknowns = "".join(f"<li>{chip('unknown')} {_e(u)}</li>" for u in push["unknowns"])
        extra = ""
        if flow == "video":
            metrics = data["comparison"]["metrics"]
            extra = (f"<h3>10. Prediction vs scripted outcome (t={data['scripted_outcome']['t']}s)</h3>"
                     f"<div class='grid2'><div>{scene_svg(scene, push['final_positions'], 'PREDICTED at T=2.0 s')}</div>"
                     f"<div>{scene_svg(data['scripted_outcome']['scene'], None, 'SCRIPTED OUTCOME (synthetic)')}</div></div>"
                     f"<pre>{_e(json.dumps({k: v for k, v in metrics.items() if k != 'per_entity'}, indent=1))}</pre>"
                     f"<p class='warn'>{_e(data['scripted_outcome']['label'])}</p>")
        sections.append(
            f"<section><h2>{flow.upper()} → MLM → ARM</h2>"
            f"<h3>1–3. Input, MLM meaning, entity ids and evidence</h3>{_meaning_table(data['meaning'])}"
            f"<h3>4. Proposed action</h3><pre>{_e(json.dumps(push['action'], indent=1))}</pre>"
            f"<h3>5–7. Initial vs predicted, per alternative (same initial state)</h3>"
            f"<div class='card'>{scene_svg(scene, None, 'INITIAL - ' + ('observed' if flow != 'text' else 'assumed positions'))}</div>"
            f"<div class='grid'>{alt}</div>"
            f"<h3>8. ARM consequences — push toward the edge</h3>{_circles(push['circles'])}"
            f"<h3>9. Assumptions and unknowns</h3><ul>{assumptions}{unknowns}</ul>{extra}</section>"
        )
    sale = demo["flows"]["sale"]
    sections.append(f"<section><h2>TEXT → MLM → ARM: the sale (rule-derived consequences)</h2>"
                    f"<p>{_e(sale['note'])}</p>{_circles(sale['circles'])}</section>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ARM Multimodal Report</title><style>
body{{font-family:system-ui,sans-serif;margin:0;padding:16px;background:#f8fafc;color:#0f172a;max-width:1200px;margin:auto}}
.badge{{position:sticky;top:0;background:#7e22ce;color:#fff;padding:8px 12px;border-radius:8px;font-weight:600;z-index:2}}
section{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:16px 0}}
table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #e2e8f0;padding:4px 6px;text-align:left;font-size:14px}}
.chip{{border:1.5px solid;border-radius:999px;padding:0 6px;font-size:11px;font-weight:700;letter-spacing:.03em}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}}.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.card{{border:1px solid #e2e8f0;border-radius:10px;padding:10px}}.empty{{color:#64748b;font-style:italic}}
.warn{{color:#92400e}}pre{{background:#f1f5f9;padding:8px;border-radius:8px;overflow:auto;font-size:12px}}
@media (max-width:700px){{.grid2{{grid-template-columns:1fr}}}}
</style></head><body><div class="badge">{_e(demo['badge'])}</div>
<p>Extraction is replayed from fixtures (not live model inference). Future scenes are simulated by a constrained
tabletop simulator; a generated picture is not evidence that a prediction is correct. ARM certainty scores are
not calibrated probabilities.</p>{''.join(sections)}</body></html>"""
