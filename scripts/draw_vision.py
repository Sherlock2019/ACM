#!/usr/bin/env python3
"""Draw how ACM sees an action: a radar of worlds around the actor, plus the vector DB.

    python scripts/draw_vision.py            # writes docs/acm-vision.svg

The radar is read from the centre out: the origin actor, its action, then the eight worlds,
each with its own laws, in the same order as the world-layers stack (docs/world-layers.svg):
atomic, physical, perception, human and animal behaviour, digital, business, society and
economy, earth. The other actors stand in the behaviour world; the action reaches them (red)
and their reactions carry the consequence on (blue). The picture is animated with SMIL only,
so it plays inside a README <img>.

Nothing in the picture is hand-placed data. The scenario runs through the real MLM parser
and ACM engine; the heat strips are the actual node vectors, and the similarity scores come
from a real search of a small GraphVectorStore. The rule engine gives each consequence a
ring (how far it reaches), not a world, so WORLD_OF placing it in a world is an explicit
mapping for the picture, and worlds the engine has nothing for say so.
"""

from __future__ import annotations

import math
import sys
from html import escape
from pathlib import Path

from acm.engine import ConsequenceEngine
from acm.render import status_word
from acm.schema import RelationStatus, Target
from acm.store import GraphVectorStore

OUT = Path(__file__).resolve().parents[1] / "docs" / "acm-vision.svg"

CONTEXT = ["Mark wants to buy my car.", "Sarah needs a car."]
ACTION = "I will sell my car to Sarah in Paris tomorrow to pay my debt."
MEMORY = [
    "John flew to London.",
    "The company destroyed the forest.",
    "John sold his car to Sarah.",
    "The engineer deleted the database in production.",
]

W = 1400
CX, CY = 700, 810
CORE_R, ACTION_R = 62, 92
BG, INK, MUTED, LINE = "#0d1117", "#e6edf3", "#8b949e", "#30363d"
ACT, REACT = "#ef4444", "#3b82f6"   # the action vector, and the reaction vectors it triggers

# The eight worlds from the centre out: (id, icon, title, laws, colour). Outer radii are spaced
# evenly from FIRST_R to OUTER_R.
WORLDS = [
    ("atomic", "⚛️", "ATOMIC & MOLECULAR", "atomic and chemical laws", "#a855f7"),
    ("physical", "⚙️", "PHYSICAL", "physical laws: force, motion, gravity, energy", "#3b82f6"),
    ("perception", "👁️", "PERCEPTION", "laws of vibration and signals", "#818cf8"),
    ("behaviour", "🧠", "HUMAN & ANIMAL BEHAVIOUR", "behavioural and psychological laws", "#14b8a6"),
    ("digital", "💻", "DIGITAL SYSTEMS", "digital system laws", "#22c55e"),
    ("business", "🏭", "BUSINESS & INSTITUTIONS", "institutional laws: contracts, accounting", "#f97316"),
    ("society", "🏛️", "SOCIETY & ECONOMY", "economic, legal and social laws", "#eab308"),
    ("earth", "🌍", "EARTH", "earth laws: ecology, climate, resources", "#10b981"),
]
FIRST_R, OUTER_R = 158, 620
STEP = (OUTER_R - FIRST_R) / (len(WORLDS) - 1)
RADIUS = {w[0]: FIRST_R + i * STEP for i, w in enumerate(WORLDS)}
INNER = {w[0]: (ACTION_R if i == 0 else FIRST_R + (i - 1) * STEP) for i, w in enumerate(WORLDS)}
COLOUR = {w[0]: w[4] for w in WORLDS}

#: The world, and so the laws, that judges each kind of engine output in this picture.
WORLD_OF = {
    Target.ENVIRONMENT: "physical",   # where the action takes place
    Target.SOCIETY: "society",
    Target.EARTH: "earth",
}

#: Prediction routing reads the WHERE of the phrase: the world the action itself happens in
#: (throw a ball: physical; post on Facebook: digital; buy, sell: economy; vote: society).
#: An explicit mapping from the engine's action concept, for the picture.
ACTION_WORLD = {"SALE": "society", "PURCHASE": "society", "PAY": "society", "MOVE": "physical",
                "DESTROY": "physical", "SEND": "digital", "POST": "digital", "VOTE": "society"}

#: One animation cycle: the actor pulses, the action fires, the other actors react, and the
#: wave spreads outward world by world.
DUR = 7.0
T_ACT, T_REACT = 0.10, 0.22

STATUS_COLOUR = {
    RelationStatus.ADVANCED: "#4ade80",
    RelationStatus.ENABLED: "#22d3ee",
    RelationStatus.BLOCKED: "#f87171",
    RelationStatus.AT_RISK: "#fbbf24",
    RelationStatus.HINDERED: "#fb923c",
}
DIRECTION_MARK = {"+": "▲", "-": "▼", "0": "●"}


def mid(world: str) -> float:
    return (INNER[world] + RADIUS[world]) / 2


def wave_t(radius: float) -> float:
    """Fraction of the cycle at which the spreading wave reaches ``radius``."""
    return 0.26 + 0.6 * max(0.0, radius - ACTION_R) / (OUTER_R - ACTION_R)


def flash(attr: str, peak: float, t: float, base: float = 0.0) -> str:
    """An <animate> that holds ``base``, peaks at cycle fraction ``t``, then fades back."""
    t0, t1 = max(t - 0.02, 0.001), min(t + 0.14, 0.999)
    return (f'<animate attributeName="{attr}" dur="{DUR}s" repeatCount="indefinite" '
            f'keyTimes="0;{t0:.3f};{t:.3f};{t1:.3f};1" values="{base};{base};{peak};{base};{base}"/>')


def dummy(x: float, y: float, s: float, colour: str) -> str:
    """A small mannequin centred on (x, y): head, body, arms, legs."""
    w = 3 * s
    return (
        f'<g stroke="{colour}" stroke-width="{w:.1f}" stroke-linecap="round" fill="none">'
        f'<circle cx="{x:.1f}" cy="{y - 17 * s:.1f}" r="{5.5 * s:.1f}" fill="{colour}" stroke="none"/>'
        f'<line x1="{x:.1f}" y1="{y - 10 * s:.1f}" x2="{x:.1f}" y2="{y + 5 * s:.1f}"/>'
        f'<line x1="{x:.1f}" y1="{y - 7 * s:.1f}" x2="{x - 9 * s:.1f}" y2="{y + 1 * s:.1f}"/>'
        f'<line x1="{x:.1f}" y1="{y - 7 * s:.1f}" x2="{x + 9 * s:.1f}" y2="{y + 1 * s:.1f}"/>'
        f'<line x1="{x:.1f}" y1="{y + 5 * s:.1f}" x2="{x - 7 * s:.1f}" y2="{y + 18 * s:.1f}"/>'
        f'<line x1="{x:.1f}" y1="{y + 5 * s:.1f}" x2="{x + 7 * s:.1f}" y2="{y + 18 * s:.1f}"/>'
        f'</g>'
    )


def text(x, y, body, *, size=12, fill=INK, anchor="middle", weight=400, family="sans") -> str:
    font = "ui-monospace, SFMono-Regular, Menlo, monospace" if family == "mono" else "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}">{escape(body)}</text>'
    )


def wrap(body: str, width: int = 24) -> list[str]:
    words, lines, line = body.split(), [], ""
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return [*lines, line] if line else lines


def heat_strip(x: float, y: float, vector: list[float], cell: float = 3.6, height: float = 12) -> str:
    peak = max((abs(v) for v in vector), default=1.0) or 1.0
    cells = []
    for i, value in enumerate(vector):
        strength = abs(value) / peak
        colour = "#3dd6c6" if value >= 0 else "#f5b942"
        opacity = 0.08 + 0.92 * strength if value else 0.06
        cells.append(
            f'<rect x="{x + i * cell:.1f}" y="{y:.1f}" width="{cell - 0.6:.1f}" height="{height}" '
            f'fill="{colour if value else MUTED}" opacity="{opacity:.2f}" rx="0.6"/>'
        )
    return "".join(cells)


def main() -> int:
    engine = ConsequenceEngine()
    report = engine.analyze(ACTION, context=CONTEXT)
    nodes = {n["id"]: n for n in report.graph["nodes"]}

    store = GraphVectorStore()
    for sentence in MEMORY:
        store.add(engine.analyze(sentence))
    hits = store.similar_actions(report, k=4)

    PY = CY + OUTER_R + 150          # top of the vector DB panels, below the radar
    H = PY + 420

    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
        f'<title>ACM: how the model sees its own action</title>',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        "<defs>",
    ]
    for wid, colour in COLOUR.items():
        svg.append(
            f'<marker id="arrow-{wid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{colour}"/></marker>'
        )
    for name, colour in (("act", ACT), ("react", REACT), ("ripple", "#4ade80")):
        svg.append(
            f'<marker id="vec-{name}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{colour}"/></marker>'
        )
    svg.append(
        f'<radialGradient id="glow"><stop offset="0%" stop-color="{ACT}" stop-opacity="0.30"/>'
        f'<stop offset="100%" stop-color="{ACT}" stop-opacity="0"/></radialGradient>'
    )
    svg.append("</defs>")

    # -- title and pipeline ---------------------------------------------------
    svg.append(text(40, 52, "ACM · how the model sees its own action", size=26, anchor="start", weight=700))
    svg.append(
        text(40, 80, "Action–Consequence Model, built on the Meaning Language Model. One action, many worlds, each with its own laws. "
                     "Generated from a real run - nothing hand-placed.", size=13, fill=MUTED, anchor="start")
    )
    steps = ["origin actor", "action → red vector", "other actors react → blue vectors",
             "impact spreads world by world, by proximity", "vs desired outcome", "graph vector DB"]
    x = 40
    for i, step in enumerate(steps):
        width = 18 + len(step) * 6.3
        svg.append(f'<rect x="{x}" y="100" width="{width:.0f}" height="28" rx="14" fill="#161b22" stroke="{LINE}"/>')
        svg.append(text(x + width / 2, 119, step, size=11))
        if i < len(steps) - 1:
            svg.append(text(x + width + 9, 119, "→", size=13, fill=MUTED))
        x += width + 18

    # -- the eight world rings, outermost first --------------------------------
    for wid, icon, title, laws, colour in reversed(WORLDS):
        svg.append(
            f'<circle cx="{CX}" cy="{CY}" r="{RADIUS[wid]:.1f}" fill="{colour}" fill-opacity="0.04" '
            f'stroke="{colour}" stroke-opacity="0.5" stroke-width="1.3"/>'
        )
    svg.append(f'<circle cx="{CX}" cy="{CY}" r="150" fill="url(#glow)"/>')

    # what the engine has for each world, decided before drawing the labels
    people: dict[str, dict] = {}
    for consequence in report.for_target(Target.IMPACTED):
        p = people.setdefault(consequence.about_label, {"lines": [], "direct": False, "status": None, "reaction": None})
        p["lines"].append(consequence.text)
        p["direct"] = True
    for relation in report.other_relations():
        verb = "wants to" if relation.intention.kind == "goal" else "did:"
        p = people.setdefault(relation.intention.owner_label, {"lines": [], "direct": False, "status": None, "reaction": None})
        p["lines"].append(f"{verb} {relation.intention.text}")
        p["status"] = relation.status
        p["reaction"] = f"reaction: {status_word(relation)}"

    # (world, label, lines, node id, edge label)
    placed: list[tuple[str, str, list[str], str, str]] = []
    for where, texts in _group(report, Target.ENVIRONMENT).items():
        placed.append((WORLD_OF[Target.ENVIRONMENT], where, texts, "e:" + where.lower(), "acts upon"))
    states = [n["label"] for n in report.graph["nodes"] if n["kind"] == "state" and n["label"].startswith(("has(", "not has("))]
    if states:
        # ownership and money changing hands: judged by contracts and accounting
        placed.append(("business", "▲ ownership & money", states[:4], "", "changes"))
    for target in (Target.SOCIETY, Target.EARTH):
        for c in report.for_target(target):
            placed.append((WORLD_OF[target], f"{DIRECTION_MARK.get(c.direction or '0', '')} {c.about}", [c.text],
                           f"impact:{target.value}:{c.about}", "impacts"))
    has_data = {w for w, *_ in placed} | ({"behaviour"} if people else set())

    for wid, icon, title, laws, colour in WORLDS:
        top = CY - RADIUS[wid] + 18
        svg.append(text(CX, top, f"{icon} {title}", size=11.5, fill=colour, weight=800))
        note = laws if wid in has_data else f"{laws} · nothing predicted in this run"
        svg.append(text(CX, top + 13, note, size=9.5, fill=MUTED))

    # -- animation: the wave leaving the actor, each world lighting as it arrives ----------
    t_end = wave_t(OUTER_R)
    for lag in (0.0, 0.12):
        svg.append(
            f'<circle cx="{CX}" cy="{CY}" r="{ACTION_R}" fill="none" stroke="{ACT}" stroke-width="3" stroke-opacity="0">'
            f'<animate attributeName="r" dur="{DUR}s" begin="{lag * DUR:.2f}s" repeatCount="indefinite" '
            f'keyTimes="0;0.24;{t_end:.3f};1" values="{ACTION_R};{ACTION_R};{OUTER_R};{OUTER_R}"/>'
            f'<animate attributeName="stroke-opacity" dur="{DUR}s" begin="{lag * DUR:.2f}s" repeatCount="indefinite" '
            f'keyTimes="0;0.24;{t_end:.3f};1" values="0;{0.85 - lag * 3:.2f};0.12;0"/></circle>'
        )
    for wid, *_rest in WORLDS:
        colour = COLOUR[wid]
        t = wave_t(RADIUS[wid])
        svg.append(
            f'<circle cx="{CX}" cy="{CY}" r="{RADIUS[wid]:.1f}" fill="{colour}" fill-opacity="0" stroke="{colour}" '
            f'stroke-width="3.5" stroke-opacity="0">{flash("stroke-opacity", 0.95, t)}{flash("fill-opacity", 0.06, t)}</circle>'
        )

    # -- proximity: the impact passes outward to the next world --------------------------------
    for i in range(len(WORLDS) - 1):
        boundary = RADIUS[WORLDS[i][0]]
        for base in (0, 180):
            a = math.radians(base)
            x1, y1 = CX + (boundary - 12) * math.cos(a), CY + (boundary - 12) * math.sin(a)
            x2, y2 = CX + (boundary + 12) * math.cos(a), CY + (boundary + 12) * math.sin(a)
            svg.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#4ade80" '
                       f'stroke-width="2.2" stroke-linecap="round" marker-end="url(#vec-ripple)"/>')

    # -- the action ring around the actor --------------------------------------------------
    svg.append(f'<circle cx="{CX}" cy="{CY}" r="{ACTION_R}" fill="none" stroke="{ACT}" stroke-width="1.8" '
               f'stroke-dasharray="5 4" stroke-opacity="0.85">{flash("stroke-width", 4, T_ACT, 1.8)}</circle>')
    concept = report.concept or report.predicate
    origin = ACTION_WORLD.get(str(concept).upper())
    action_label = f"action · {concept}"
    if origin:
        o_icon, o_title = next((w[1], w[2]) for w in WORLDS if w[0] == origin)
        action_label += f" · WHERE: {o_title.split(' & ')[-1].lower()} world"
        # the action's own world, highlighted: this is where prediction routing starts
        svg.append(f'<circle cx="{CX}" cy="{CY}" r="{RADIUS[origin]:.1f}" fill="none" stroke="{COLOUR[origin]}" '
                   f'stroke-width="4" stroke-dasharray="14 6" stroke-opacity="0.9">{flash("stroke-width", 8, T_ACT, 4)}</circle>')
        tag = f"★ the action happens here: {o_icon} {o_title.lower()} (the WHERE of the phrase)"
        tag_y = CY + RADIUS[origin] - 10
        svg.append(f'<rect x="{CX - len(tag) * 3.2 - 10:.1f}" y="{tag_y - 13:.1f}" width="{len(tag) * 6.4 + 20:.1f}" height="19" '
                   f'rx="9" fill="{BG}" stroke="{COLOUR[origin]}"/>')
        svg.append(text(CX, tag_y + 1, tag, size=10.5, fill=COLOUR[origin], weight=700))
    bw = len(action_label) * 6.6 + 18
    svg.append(f'<rect x="{CX - bw / 2:.1f}" y="{CY + ACTION_R - 9}" width="{bw:.1f}" height="18" rx="9" fill="{BG}" stroke="{ACT}"/>')
    svg.append(text(CX, CY + ACTION_R + 4, action_label, size=10.5, fill="#fca5a5", weight=700))

    # -- consequences placed in their worlds ------------------------------------------------
    angles = {"physical": [162, 110], "business": [35, 60], "society": [-52, 232], "earth": [-10, 160, -100]}
    used: dict[str, int] = {}
    for wid, label, lines, node_id, edge_label in placed:
        radius, colour = mid(wid), COLOUR[wid]
        slot = used.get(wid, 0)
        used[wid] = slot + 1
        options = angles.get(wid, [45, 135, 225, 315])
        angle = math.radians(options[slot % len(options)])
        nx, ny = CX + radius * math.cos(angle), CY + radius * math.sin(angle)
        ux, uy = math.cos(angle), math.sin(angle)
        sx, sy = CX + ux * (ACTION_R + 4), CY + uy * (ACTION_R + 4)
        ex, ey = nx - ux * 15, ny - uy * 15
        svg.append(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{colour}" '
                   f'stroke-width="1.6" stroke-opacity="0.85" marker-end="url(#arrow-{wid})"/>')
        svg.append(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{colour}" stroke-width="3" '
                   f'stroke-linecap="round" stroke-dasharray="3 13" stroke-opacity="0.9">'
                   f'<animate attributeName="stroke-dashoffset" from="16" to="0" dur="0.8s" repeatCount="indefinite"/></line>')
        if edge_label:
            lx, ly = sx + (ex - sx) * 0.55, sy + (ey - sy) * 0.55
            svg.append(f'<rect x="{lx - len(edge_label) * 3.1 - 5:.1f}" y="{ly - 9:.1f}" width="{len(edge_label) * 6.2 + 10:.1f}" '
                       f'height="15" rx="7" fill="{BG}" stroke="{colour}" stroke-opacity="0.5"/>')
            svg.append(text(lx, ly + 2.5, edge_label, size=9.5, fill=colour, family="mono"))
        t_node = wave_t(radius)
        svg.append(f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="13" fill="none" stroke="{colour}" stroke-width="2.5" stroke-opacity="0">'
                   f'{flash("r", 26, t_node, 13)}{flash("stroke-opacity", 0.9, t_node)}</circle>')
        svg.append(f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="13" fill="{BG}" stroke="{colour}" stroke-width="2"/>')
        svg.append(f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="5" fill="{colour}"/>')
        below = 1 if uy >= -0.2 else -1
        rows = sum(len(wrap(line, 30)) for line in lines)
        ty = ny + (30 if below > 0 else -24 - 13.5 * rows)
        svg.append(text(nx, ty, label, size=12.5, fill=colour, weight=700))
        row = ty
        for line in lines:
            for part in wrap(line, 30):
                row += 13.5
                svg.append(text(nx, row, part, size=10.5, family="mono" if "(" in part else "sans"))
        vector = nodes.get(node_id, {}).get("vector")
        if vector:
            strip_y = row + 6 if below > 0 else ty - 22
            svg.append(heat_strip(nx - len(vector) * 0.9, strip_y, vector, cell=1.8, height=6))

    # -- the other actors, standing in the behaviour world: action red, reactions blue ------------
    person_angles = [215, -35, 125, 305]
    r_p = mid("behaviour")
    for i, (who, p) in enumerate(people.items()):
        ang = math.radians(person_angles[i % len(person_angles)])
        ux, uy = math.cos(ang), math.sin(ang)
        px_, py_ = CX + r_p * ux, CY + r_p * uy
        sx, sy = CX + ux * (CORE_R + 2), CY + uy * (CORE_R + 2)
        ex, ey = px_ - ux * 30, py_ - uy * 30
        dash = "" if p["direct"] else ' stroke-dasharray="7 5"'
        svg.append(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{ACT}" stroke-width="3.2" '
                   f'marker-end="url(#vec-act)"{dash}>{flash("stroke-width", 6, T_ACT, 3.2)}</line>')
        svg.append(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#fecaca" stroke-width="2" '
                   f'stroke-linecap="round" stroke-dasharray="2 14"><animate attributeName="stroke-dashoffset" '
                   f'from="16" to="0" dur="0.7s" repeatCount="indefinite"/></line>')
        if i == 0:
            mx, my = sx + (ex - sx) * 0.55, sy + (ey - sy) * 0.55
            act_txt = f"action: {report.concept or report.predicate}"
            svg.append(f'<rect x="{mx - len(act_txt) * 3.3 - 6:.1f}" y="{my - 10:.1f}" width="{len(act_txt) * 6.6 + 12:.1f}" '
                       f'height="17" rx="8" fill="{BG}" stroke="{ACT}"/>')
            svg.append(text(mx, my + 3, act_txt, size=10.5, fill="#fca5a5", weight=700, family="mono"))
        colour = STATUS_COLOUR.get(p["status"], REACT) if p["status"] else REACT
        svg.append(f'<circle cx="{px_:.1f}" cy="{py_:.1f}" r="24" fill="none" stroke="{ACT}" stroke-width="2.5" '
                   f'stroke-opacity="0">{flash("r", 38, T_ACT + 0.03, 24)}{flash("stroke-opacity", 0.9, T_ACT + 0.03)}</circle>')
        svg.append(dummy(px_, py_, 1.0, REACT))
        bx0, by0 = px_ + ux * 28, py_ + uy * 28
        bx1, by1 = px_ + ux * 100, py_ + uy * 100
        svg.append(f'<line x1="{bx0:.1f}" y1="{by0:.1f}" x2="{bx1:.1f}" y2="{by1:.1f}" stroke="{REACT}" stroke-width="3.2" '
                   f'marker-end="url(#vec-react)">{flash("stroke-width", 6, T_REACT, 3.2)}</line>')
        svg.append(f'<circle cx="{px_:.1f}" cy="{py_:.1f}" r="24" fill="none" stroke="{REACT}" stroke-width="2.5" '
                   f'stroke-opacity="0">{flash("r", 40, T_REACT, 24)}{flash("stroke-opacity", 0.9, T_REACT)}</circle>')
        lab_y = py_ + 42
        svg.append(text(px_, lab_y, who, size=12.5, fill="#93c5fd", weight=700))
        for j, line in enumerate(p["lines"]):
            svg.append(text(px_, lab_y + 14 + j * 13, line, size=10.5))
        if p["reaction"]:
            tip_x, tip_y = bx1 + ux * 10, by1 + uy * 10
            anchor = "start" if ux > 0.2 else ("end" if ux < -0.2 else "middle")
            svg.append(text(tip_x, tip_y - 4, p["reaction"], size=11, fill=colour, anchor=anchor, weight=700))

    # -- the core: the origin actor, a small red dummy ---------------------------------------
    svg.append(f'<circle cx="{CX}" cy="{CY}" r="{CORE_R}" fill="none" stroke="{ACT}" stroke-width="3" stroke-opacity="0">'
               f'{flash("r", 84, 0.03, CORE_R)}{flash("stroke-opacity", 1, 0.03)}</circle>')
    svg.append(f'<circle cx="{CX}" cy="{CY}" r="{CORE_R}" fill="#1f0b0b" stroke="{ACT}" stroke-width="2.4"/>')
    svg.append(dummy(CX, CY - 12, 1.0, ACT))
    svg.append(text(CX, CY + 28, ("SELF" if report.self_view else (report.actor_label or "?")) + " · origin actor",
                    size=11, fill="#fca5a5", weight=800))
    actor_lines = [c.text for c in report.for_target(Target.ACTOR)]
    svg.append(text(CX, CY + 42, " · ".join(actor_lines[:2]), size=9, fill=MUTED))
    for relation in report.own_goals()[:1]:
        svg.append(text(CX + 20, CY + ACTION_R + 26, f"desired outcome: {relation.intention.text} → {status_word(relation)}",
                        size=11, fill="#22d3ee"))

    # -- legend --------------------------------------------------------------------------
    ly = CY + OUTER_R + 44
    svg.append(text(40, ly, "red dummy = the origin actor · red vector = its action (dashed: reaches that actor only through its consequences)   ·   "
                            "blue dummies = the other actors · blue vectors = their reactions", size=11, fill="#cbd5e1", anchor="start"))
    svg.append(text(40, ly + 19, "A reaction is the consequence for that actor's goal, computed by the engine; what they do next is not predicted here.",
                    size=10.5, fill=MUTED, anchor="start"))
    svg.append(text(40, ly + 40, "→ proximity: the impact spreads outward world by world, and a consequence can also flow back   ·   "
                                 "∿ synchronicity: worlds change together, down to the quantum level (correlation, not cause)   ·   both concepts, not yet modelled",
                    size=11, fill="#f5d0fe", anchor="start"))
    svg.append(text(40, ly + 59, "World placement: the rule engine says how far each consequence reaches, not which world it is in; "
                                 "the world shown is an explicit mapping for this picture, and empty worlds say so.",
                    size=10.5, fill=MUTED, anchor="start"))

    # -- the graph vector DB, below the radar ------------------------------------------------
    lx0, rx0, pw = 40, 720, 640
    for x0 in (lx0, rx0):
        svg.append(f'<rect x="{x0}" y="{PY}" width="{pw}" height="370" rx="14" fill="#11161d" stroke="{LINE}"/>')
    svg.append(text(lx0 + 22, PY + 32, "GRAPH VECTOR DB", size=14, anchor="start", weight=800))
    svg.append(text(lx0 + 22, PY + 50, "every node of every action graph is stored as a vector", size=11, fill=MUTED, anchor="start"))
    svg.append(text(lx0 + 22, PY + 76, "this action's nodes", size=11.5, fill="#f5b942", anchor="start", weight=700))
    order = ["action", "self", "entity", "place", "state", "intention", "impact", "scope", "time"]
    ordered = sorted(report.graph["nodes"], key=lambda n: order.index(n["kind"]) if n["kind"] in order else len(order))
    y = PY + 90
    for node in ordered[:11]:
        svg.append(text(lx0 + 22, y + 10, node["kind"], size=9.5, fill=MUTED, anchor="start", family="mono"))
        label = node["label"] if len(node["label"]) <= 28 else node["label"][:27] + "…"
        svg.append(text(lx0 + 92, y + 10, label, size=10, anchor="start", family="mono"))
        svg.append(heat_strip(lx0 + 300, y, node["vector"], cell=3.4, height=12))
        y += 20
    dim = len(report.graph["nodes"][0]["vector"])
    svg.append(text(lx0 + 22, y + 16, f"{dim} dims: kind | role | entity type | circle | lemma hash | certainty · polarity · tense",
                    size=9.5, fill=MUTED, anchor="start"))
    svg.append(heat_strip(lx0 + 22, y + 26, [1.0] * 6 + [-1.0] * 6, cell=8, height=8))
    svg.append(text(lx0 + 125, y + 34, "teal = positive   amber = negative", size=9.5, fill=MUTED, anchor="start"))

    svg.append(text(rx0 + 22, PY + 32, "memory: similar_actions(this action)", size=13, fill="#3dd6c6", anchor="start", weight=800))
    svg.append(text(rx0 + 22, PY + 50, "cosine similarity of action nodes across stored graphs", size=11, fill=MUTED, anchor="start"))
    y = PY + 70
    for hit in hits:
        score = max(hit["score"], 0.0)
        svg.append(f'<rect x="{rx0 + 22}" y="{y}" width="{pw - 44}" height="42" rx="8" fill="#161b22" stroke="{LINE}"/>')
        svg.append(text(rx0 + 34, y + 17, f"#{hit['graph_id']}  {hit['label']}", size=10, fill=MUTED, anchor="start", family="mono"))
        svg.append(text(rx0 + 34, y + 33, hit["text"], size=11.5, anchor="start"))
        svg.append(f'<rect x="{rx0 + pw - 160}" y="{y + 11}" width="100" height="7" rx="3.5" fill="{LINE}"/>')
        svg.append(f'<rect x="{rx0 + pw - 160}" y="{y + 11}" width="{100 * score:.1f}" height="7" rx="3.5" fill="#3dd6c6"/>')
        svg.append(text(rx0 + pw - 34, y + 33, f"{hit['score']:.2f}", size=11, anchor="end", family="mono"))
        y += 50
    svg.append(text(rx0 + 22, y + 18, "vectors are structural, not semantic: two nodes are close when they play the same part",
                    size=10.5, fill=MUTED, anchor="start"))
    svg.append(text(rx0 + 22, y + 33, "in similar actions. A learned embedder can replace the hashing one behind the same interface.",
                    size=10.5, fill=MUTED, anchor="start"))

    # -- footer -------------------------------------------------------------------------
    svg.append(text(40, H - 18, f"scenario  ·  context: {' '.join(CONTEXT)}  ·  action: {ACTION}", size=11.5, fill=MUTED, anchor="start"))
    svg.append(text(W - 40, H - 18, "© 2026 Dzoan Nguyen Tran · github.com/Sherlock2019/ACM", size=11.5, fill=MUTED, anchor="end"))
    svg.append("</svg>")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(svg), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


def _group(report, target):
    groups: dict[str, list[str]] = {}
    for consequence in report.for_target(target):
        groups.setdefault(consequence.about_label, []).append(consequence.text)
    return groups


if __name__ == "__main__":
    sys.exit(main())
