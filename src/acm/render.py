"""Render a consequence report: Mermaid mind map, Mermaid graph, or plain text."""

from __future__ import annotations

import re
from typing import Any

from acm.schema import GEO_LAYERS, LAYERS, ConsequenceReport, Relation, RelationStatus, Target

GOAL_WORDS = {
    RelationStatus.ADVANCED: "ADVANCED ✅",
    RelationStatus.ENABLED: "ENABLED ➕",
    RelationStatus.BLOCKED: "BLOCKED ❌",
    RelationStatus.AT_RISK: "AT RISK ⚠️",
    RelationStatus.HINDERED: "HINDERED ➖",
    RelationStatus.UNAFFECTED: "unaffected",
    RelationStatus.NO_EVIDENCE: "no evidence ❔",
}
ACTION_WORDS = {
    RelationStatus.ADVANCED: "REINFORCES ✅",
    RelationStatus.ENABLED: "SUPPORTS ➕",
    RelationStatus.BLOCKED: "UNDOES ❌",
    RelationStatus.AT_RISK: "MAY UNDO ⚠️",
    RelationStatus.HINDERED: "UNDERMINES ➖",
    RelationStatus.UNAFFECTED: "unrelated",
    RelationStatus.NO_EVIDENCE: "no evidence ❔",
}
DIRECTION = {"+": "▲ helps", "-": "▼ harms", "0": "● changes"}
NO_IMPACT = "no known impact - no rule matched, which is not evidence of none"
LAYER_TITLES = {
    Target.ENVIRONMENT: "Local environment",
    Target.NEIGHBOUR: "Neighbour environment",
    Target.ORGANIZATION: "Organization",
    Target.CITY: "City",
    Target.COUNTRY: "Country",
    Target.SOCIETY: "Society",
    Target.EARTH: "Earth",
}


def status_word(relation: Relation) -> str:
    words = GOAL_WORDS if relation.intention.kind == "goal" else ACTION_WORDS
    return words[relation.status]


def relation_line(relation: Relation) -> str:
    verb = "wants to" if relation.intention.kind == "goal" else "did:"
    return f"{relation.intention.owner_label} {verb} {relation.intention.text} - {status_word(relation)}"


def _grouped(report: ConsequenceReport, target: Target) -> dict[str, list[str]]:
    """State changes under a target, by the entity they are about."""
    groups: dict[str, list[str]] = {}
    for consequence in report.for_target(target):
        if consequence.fact is not None:
            groups.setdefault(consequence.about_label, []).append(consequence.text)
    return groups


def _impact_lines(report: ConsequenceReport, target: Target) -> list[str]:
    return [
        f"{c.about}: {c.text} ({DIRECTION.get(c.direction or '0', '')})"
        for c in report.for_target(target)
        if c.fact is None
    ]


def layer_extent(report: ConsequenceReport, target: Target) -> str | None:
    """What a layer is for this action: the place, its city, its country, ..."""
    if target == Target.ENVIRONMENT:
        return ", ".join(report.places) or "no place stated"
    if target in GEO_LAYERS:
        names = report.scopes.get(target.value, [])
        return ", ".join(names) or ("not known" if report.places else "no place stated")
    return None


def _empty_layer(report: ConsequenceReport) -> list[str]:
    return [NO_IMPACT] if report.realized else ["nothing changes"]


# -- Mermaid mind map -------------------------------------------------------


def _clean(text: str) -> str:
    """Mind map node text cannot contain shape brackets or quotes."""
    text = re.sub(r"[()\[\]{}\"`]", "", text)
    return re.sub(r"\s+", " ", text).strip() or "?"


def to_mindmap(report: ConsequenceReport) -> str:
    lines = ["mindmap"]

    def node(depth: int, text: str) -> None:
        lines.append("  " * depth + _clean(text))

    title = report.actor_label or "?"
    action = report.predicate or "?"
    if not report.realized:
        action = f"NOT {action}"
    lines.append(f"  root(({_clean(f'{title} · {action}')}))")

    actor_heading = "Self" if report.self_view else f"Actor: {report.actor_label or '?'}"
    node(2, actor_heading)
    for text in _grouped(report, Target.ACTOR).get(report.actor_label or "", []):
        node(3, text)
    for relation in report.own_goals():
        node(3, f"own goal {relation.intention.text}: {status_word(relation)}")

    impacted = _grouped(report, Target.IMPACTED)
    if impacted:
        node(2, "Impacted")
        for subject, texts in impacted.items():
            node(3, subject)
            for text in texts:
                node(4, text)

    others = report.other_relations()
    if others:
        node(2, "Other actors")
        for relation in others:
            node(3, relation_line(relation))

    for target in LAYERS:
        extent = layer_extent(report, target)
        node(2, LAYER_TITLES[target] + (f": {extent}" if extent else ""))
        changes = _grouped(report, target)
        rows = [
            f"{where}: {text}" if len(changes) > 1 else text
            for where, texts in changes.items()
            for text in texts
        ]
        for text in rows + _impact_lines(report, target) or _empty_layer(report):
            node(3, text)
    return "\n".join(lines)


# -- Mermaid flowchart of the vector graph ----------------------------------

SHAPES = {
    "action": ('(["', '"])'),
    "self": ('(("', '"))'),
    "entity": ('["', '"]'),
    "place": ('[/"', '"/]'),
    "time": ('["', '"]'),
    "state": ('{{"', '"}}'),
    "impact": ('>"', '"]'),
    "scope": ('(("', '"))'),
    "intention": ('[["', '"]]'),
}


def to_flowchart(graph: dict[str, Any]) -> str:
    ids = {node["id"]: f"n{i}" for i, node in enumerate(graph.get("nodes", []))}
    lines = ["flowchart LR"]
    for node in graph.get("nodes", []):
        left, right = SHAPES.get(node["kind"], ('["', '"]'))
        label = str(node["label"]).replace('"', "#quot;")
        lines.append(f"  {ids[node['id']]}{left}{label}{right}")
    for edge in graph.get("edges", []):
        if edge["source"] in ids and edge["target"] in ids:
            relation = edge["relation"].replace('"', "")
            lines.append(f'  {ids[edge["source"]]} -->|"{relation}"| {ids[edge["target"]]}')
    return "\n".join(lines)


# -- plain text --------------------------------------------------------------


def to_text(report: ConsequenceReport) -> str:
    out: list[str] = []
    head = f"ACTION  {report.action_text}"
    out.append(head)
    facts = [
        f"concept={report.concept or 'unknown'}",
        f"tense={report.tense or '?'}",
        f"certainty={report.certainty:.2f}",
    ]
    if report.self_view:
        facts.append("SELF-VIEW")
    if not report.realized:
        facts.append("NEGATED")
    out.append("        " + "  ".join(facts))

    def section(title: str, rows: list[str]) -> None:
        out.append("")
        out.append(title)
        out.extend(f"  {row}" for row in rows or ["-"])

    actor_rows = list(_grouped(report, Target.ACTOR).get(report.actor_label or "", []))
    actor_rows += [f"own goal '{r.intention.text}': {status_word(r)} - {r.reason}" for r in report.own_goals()]
    section(f"ACTOR  {'(self) ' if report.self_view else ''}{report.actor_label or '?'}", actor_rows)
    section(
        "IMPACTED",
        [f"{who}: {'; '.join(texts)}" for who, texts in _grouped(report, Target.IMPACTED).items()],
    )
    section("OTHER ACTORS", [f"{relation_line(r)}  ({r.reason})" for r in report.other_relations()])
    for target in LAYERS:
        extent = layer_extent(report, target)
        rows = [f"{where}: {'; '.join(texts)}" for where, texts in _grouped(report, target).items()]
        section(
            LAYER_TITLES[target].upper() + (f"  {extent}" if extent else ""),
            rows + _impact_lines(report, target) or _empty_layer(report),
        )
    if report.notes:
        section("NOTES", report.notes)
    return "\n".join(out)
