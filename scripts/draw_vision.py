#!/usr/bin/env python3
"""Draw how CAM sees an action: concentric circles of consequence + the vector DB.

    python scripts/draw_vision.py            # writes docs/cam-vision.svg

Nothing in the picture is hand-placed data. The scenario runs through the real
MLM parser and CAM engine; each circle shows what the report put there, the
heat strips are the actual node vectors, and the similarity scores come from a
real search of a small GraphVectorStore.
"""

from __future__ import annotations

import math
import sys
from html import escape
from pathlib import Path

from cam.engine import ConsequenceEngine
from cam.render import status_word
from cam.schema import RelationStatus, Target
from cam.store import GraphVectorStore

OUT = Path(__file__).resolve().parents[1] / "docs" / "cam-vision.svg"

CONTEXT = ["Mark wants to buy my car.", "Sarah needs a car."]
ACTION = "I will sell my car to Sarah in Paris tomorrow to pay my debt."
MEMORY = [
    "John flew to London.",
    "The company destroyed the forest.",
    "John sold his car to Sarah.",
    "The engineer deleted the database in production.",
]

W, H = 1480, 1110
CX, CY = 490, 615
BG, INK, MUTED, LINE = "#0d1117", "#e6edf3", "#8b949e", "#30363d"

# (target, title, question, outer radius, colour)
RINGS = [
    (Target.ACTOR, "SELF", "who acts", 78, "#f5b942"),
    (Target.IMPACTED, "IMPACTED", "what · to whom", 160, "#3dd6c6"),
    (Target.OTHER_ACTORS, "OTHER ACTORS", "their goals · their actions", 245, "#a78bfa"),
    (Target.ENVIRONMENT, "ENVIRONMENT", "where", 322, "#bef264"),
    (Target.SOCIETY, "SOCIETY", "economy · law · trust", 392, "#60a5fa"),
    (Target.EARTH, "EARTH", "emissions · biodiversity · resources", 455, "#34d399"),
]
STATUS_COLOUR = {
    RelationStatus.ADVANCED: "#4ade80",
    RelationStatus.ENABLED: "#22d3ee",
    RelationStatus.BLOCKED: "#f87171",
    RelationStatus.AT_RISK: "#fbbf24",
    RelationStatus.HINDERED: "#fb923c",
}
DIRECTION_MARK = {"+": "▲", "-": "▼", "0": "●"}


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

    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        "<defs>",
    ]
    for name, colour in [(r[0].value, r[4]) for r in RINGS] + [(s.value, c) for s, c in STATUS_COLOUR.items()]:
        svg.append(
            f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{colour}"/></marker>'
        )
    svg.append(
        '<radialGradient id="glow"><stop offset="0%" stop-color="#f5b942" stop-opacity="0.35"/>'
        '<stop offset="100%" stop-color="#f5b942" stop-opacity="0"/></radialGradient>'
    )
    svg.append("</defs>")

    # -- title and pipeline ---------------------------------------------------
    svg.append(text(40, 52, "CAM · how the model sees its own action", size=26, anchor="start", weight=700))
    svg.append(
        text(40, 80, "Consequence Action Model, built on the Meaning Language Model. Generated from a real run - nothing hand-placed.",
             size=13, fill=MUTED, anchor="start")
    )
    steps = ["phrase", "MLM Phrase DNA", "action graph", "consequences per circle", "node vectors", "graph vector DB"]
    x = 40
    for i, step in enumerate(steps):
        width = 22 + len(step) * 7.2
        svg.append(f'<rect x="{x}" y="100" width="{width:.0f}" height="28" rx="14" fill="#161b22" stroke="{LINE}"/>')
        svg.append(text(x + width / 2, 119, step, size=12))
        if i < len(steps) - 1:
            svg.append(text(x + width + 13, 119, "→", size=14, fill=MUTED))
        x += width + 26

    # -- concentric circles --------------------------------------------------
    for target, title, question, radius, colour in reversed(RINGS):
        svg.append(
            f'<circle cx="{CX}" cy="{CY}" r="{radius}" fill="{colour}" fill-opacity="0.045" '
            f'stroke="{colour}" stroke-opacity="0.45" stroke-width="1.2"/>'
        )
    svg.append(f'<circle cx="{CX}" cy="{CY}" r="120" fill="url(#glow)"/>')
    previous = 0
    for target, title, question, radius, colour in RINGS:
        if target != Target.ACTOR:
            band_top = CY - radius + 17
            svg.append(text(CX, band_top, title, size=11, fill=colour, weight=700))
            svg.append(text(CX, band_top + 13, question, size=9.5, fill=MUTED))
        previous = radius

    # -- what sits on each circle --------------------------------------------
    def mid(target: Target) -> tuple[float, str]:
        for i, ring in enumerate(RINGS):
            if ring[0] == target:
                inner = RINGS[i - 1][3] if i else 0
                return (inner + ring[3]) / 2 + 4, ring[4]
        raise KeyError(target)

    placed: list[tuple[Target, str, list[str], str, str | None, str]] = []
    for who, texts in _group(report, Target.IMPACTED).items():
        placed.append((Target.IMPACTED, who, texts, "e:" + who.lower(), None, "changes"))
    for relation in report.other_relations():
        verb = "wants to" if relation.intention.kind == "goal" else "did:"
        placed.append(
            (
                Target.OTHER_ACTORS,
                relation.intention.owner_label,
                [f"{verb} {relation.intention.text}", status_word(relation)],
                f"e:{relation.intention.owner}",
                relation.status.value if relation.status in STATUS_COLOUR else None,
                relation.status.value.replace("_", " "),
            )
        )
    for where, texts in _group(report, Target.ENVIRONMENT).items():
        placed.append((Target.ENVIRONMENT, where, texts, "e:" + where.lower(), None, "acts upon"))
    for target in (Target.SOCIETY, Target.EARTH):
        impacts = report.for_target(target)
        for c in impacts:
            placed.append(
                (target, f"{DIRECTION_MARK.get(c.direction or '0', '')} {c.about}", [c.text], f"impact:{target.value}:{c.about}", None, "impacts")
            )
        if not impacts:
            placed.append((target, "no known impact", ["no rule matched - not evidence of none"], "", None, ""))

    angles = {
        Target.IMPACTED: [35, 150, 270],
        Target.OTHER_ACTORS: [-28, 208, 100, 300],
        Target.ENVIRONMENT: [62, 128],
        Target.SOCIETY: [-52, 232, 112],
        Target.EARTH: [24, 156, -96],
    }
    used: dict[Target, int] = {}
    for target, label, lines, node_id, status, edge_label in placed:
        radius, colour = mid(target)
        slot = used.get(target, 0)
        used[target] = slot + 1
        angle = math.radians(angles[target][slot % len(angles[target])])
        nx, ny = CX + radius * math.cos(angle), CY + radius * math.sin(angle)
        edge_colour = STATUS_COLOUR.get(RelationStatus(status), colour) if status else colour
        marker = status if status else target.value
        # edge from the core to the node, stopping short of both circles
        dx, dy = nx - CX, ny - CY
        length = math.hypot(dx, dy)
        sx, sy = CX + dx / length * 66, CY + dy / length * 66
        ex, ey = nx - dx / length * 15, ny - dy / length * 15
        dashed = ' stroke-dasharray="4 4"' if not node_id else ""
        svg.append(
            f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{edge_colour}" '
            f'stroke-width="1.6" stroke-opacity="0.85" marker-end="url(#arrow-{marker})"{dashed}/>'
        )
        if edge_label:
            lx, ly = (sx + ex) / 2, (sy + ey) / 2
            svg.append(f'<rect x="{lx - len(edge_label) * 3.1 - 5:.1f}" y="{ly - 9:.1f}" width="{len(edge_label) * 6.2 + 10:.1f}" height="15" rx="7" fill="{BG}" stroke="{edge_colour}" stroke-opacity="0.5"/>')
            svg.append(text(lx, ly + 2.5, edge_label, size=9.5, fill=edge_colour, family="mono"))
        svg.append(f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="13" fill="{BG}" stroke="{colour}" stroke-width="2"/>')
        svg.append(f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="5" fill="{colour}"/>')
        below = 1 if math.sin(angle) >= -0.2 else -1
        rows = sum(len(wrap(line, 30)) for line in lines)
        ty = ny + (30 if below > 0 else -24 - 13.5 * rows)
        svg.append(text(nx, ty, label, size=12.5, fill=colour, weight=700))
        row = ty
        for line in lines:
            for part in wrap(line, 30):
                row += 13.5
                svg.append(text(nx, row, part, size=10.5, fill=INK if "✅" not in part and "❌" not in part else edge_colour))
        vector = nodes.get(node_id, {}).get("vector")
        if vector:
            # Below the text when the label hangs under the node, above it otherwise.
            strip_y = row + 6 if below > 0 else ty - 22
            svg.append(heat_strip(nx - len(vector) * 0.9, strip_y, vector, cell=1.8, height=6))

    # -- the core: the actor and its action ---------------------------------
    svg.append(f'<circle cx="{CX}" cy="{CY}" r="62" fill="#1c1608" stroke="#f5b942" stroke-width="2.4"/>')
    svg.append(text(CX, CY - 22, "SELF" if report.self_view else (report.actor_label or "?"), size=15, fill="#f5b942", weight=800))
    svg.append(text(CX, CY - 4, f"{report.concept or report.predicate}", size=13, weight=700))
    actor_lines = [c.text for c in report.for_target(Target.ACTOR)]
    for i, line in enumerate(actor_lines[:2]):
        svg.append(text(CX, CY + 13 + i * 13, line, size=10, fill=MUTED))
    for relation in report.own_goals()[:1]:
        svg.append(text(CX, CY - 76, f"own goal: {relation.intention.text} → {status_word(relation)}", size=11, fill="#22d3ee"))

    # -- right panel: the graph vector DB ------------------------------------
    px, pw = 1010, 430
    svg.append(f'<rect x="{px}" y="150" width="{pw}" height="880" rx="14" fill="#11161d" stroke="{LINE}"/>')
    svg.append(text(px + 22, 182, "GRAPH VECTOR DB", size=14, anchor="start", weight=800))
    svg.append(text(px + 22, 200, "every node of every action graph is stored as a vector", size=11, fill=MUTED, anchor="start"))

    svg.append(text(px + 22, 232, "this action's nodes", size=11.5, fill="#f5b942", anchor="start", weight=700))
    ordered = sorted(report.graph["nodes"], key=lambda n: ["action", "self", "entity", "place", "state", "intention", "impact", "scope", "time"].index(n["kind"]))
    y = 250
    for node in ordered[:13]:
        svg.append(text(px + 22, y + 10, node["kind"], size=9.5, fill=MUTED, anchor="start", family="mono"))
        label = node["label"] if len(node["label"]) <= 24 else node["label"][:23] + "…"
        svg.append(text(px + 92, y + 10, label, size=10, anchor="start", family="mono"))
        svg.append(heat_strip(px + 262, y, node["vector"], cell=1.95, height=12))
        y += 20
    dim = len(report.graph["nodes"][0]["vector"])
    svg.append(text(px + 22, y + 14, f"{dim} dims: kind | role | entity type | circle | lemma hash | certainty · polarity · tense", size=9.5, fill=MUTED, anchor="start"))
    svg.append(heat_strip(px + 22, y + 24, [1.0] * 6 + [-1.0] * 6, cell=8, height=8))
    svg.append(text(px + 125, y + 32, "teal = positive   amber = negative", size=9.5, fill=MUTED, anchor="start"))

    y += 64
    svg.append(f'<line x1="{px + 22}" y1="{y}" x2="{px + pw - 22}" y2="{y}" stroke="{LINE}"/>')
    y += 28
    svg.append(text(px + 22, y, "memory: similar_actions(this action)", size=11.5, fill="#3dd6c6", anchor="start", weight=700))
    svg.append(text(px + 22, y + 16, "cosine similarity of action nodes across stored graphs", size=10, fill=MUTED, anchor="start"))
    y += 34
    for hit in hits:
        score = max(hit["score"], 0.0)
        svg.append(f'<rect x="{px + 22}" y="{y}" width="{pw - 44}" height="40" rx="8" fill="#161b22" stroke="{LINE}"/>')
        svg.append(text(px + 34, y + 16, f"#{hit['graph_id']}  {hit['label']}", size=10, fill=MUTED, anchor="start", family="mono"))
        svg.append(text(px + 34, y + 31, hit["text"], size=11, anchor="start"))
        bar = 90 * score
        svg.append(f'<rect x="{px + pw - 134}" y="{y + 10}" width="90" height="7" rx="3.5" fill="{LINE}"/>')
        svg.append(f'<rect x="{px + pw - 134}" y="{y + 10}" width="{bar:.1f}" height="7" rx="3.5" fill="#3dd6c6"/>')
        svg.append(text(px + pw - 34, y + 31, f"{hit['score']:.2f}", size=11, anchor="end", family="mono"))
        y += 48

    y += 16
    svg.append(text(px + 22, y, "vectors are structural, not semantic:", size=10.5, fill=MUTED, anchor="start", weight=700))
    for i, line in enumerate(
        [
            "two nodes are close when they play the same part in",
            "similar actions. A learned embedder can replace the",
            "hashing one behind the same interface.",
        ]
    ):
        svg.append(text(px + 22, y + 15 + i * 14, line, size=10.5, fill=MUTED, anchor="start"))

    # -- footer -------------------------------------------------------------
    svg.append(text(40, H - 18, f"scenario  ·  context: {' '.join(CONTEXT)}  ·  action: {ACTION}", size=11.5, fill=MUTED, anchor="start"))
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
