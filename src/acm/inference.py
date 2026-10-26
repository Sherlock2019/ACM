"""The inference suite: "what will happen next to ...?", answered by ACM with its reasoning.

For each scenario (context + action) ACM's report is turned into questions and
answers, one per subject the action touches:

    the actor  ·  each impacted person or thing  ·  each other person's goal or action
    ·  each place  ·  each wider layer (neighbours ... earth)  ·  what ACM cannot say

Every answer sentence carries its *why*, built only from what the engine recorded
in ``report.trace`` and the consequence's own source: the concept rule and the role
the subject plays in it (and which MLM role filled that), the impact rule and the
category that triggered it, or the goal comparison. Nothing is paraphrased by a
language model; the text is assembled from the engine's own records.

The sentences are parsed once by MLM's real parser (scripts/make_inference_suite.py)
and frozen in examples/inference_suite.conllu, so the suite rebuilds without a parser.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from acm.engine import ConsequenceEngine
from acm.schema import Consequence, ConsequenceReport, Relation, RelationStatus, Target

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
SUITE_YAML = EXAMPLES / "inference_suite.yaml"
SUITE_CONLLU = EXAMPLES / "inference_suite.conllu"

LAYER_NAMES = {
    Target.NEIGHBOUR: "the neighbours",
    Target.ORGANIZATION: "the organization",
    Target.CITY: "the city",
    Target.COUNTRY: "the country",
    Target.SOCIETY: "society",
    Target.EARTH: "the earth",
}
DIRECTION_WORDS = {"+": "helps", "-": "harms", "0": "changes"}
STATUS_WORDS = {
    RelationStatus.ADVANCED: "moves closer",
    RelationStatus.ENABLED: "becomes possible",
    RelationStatus.BLOCKED: "is blocked",
    RelationStatus.AT_RISK: "is at risk",
    RelationStatus.HINDERED: "becomes harder",
    RelationStatus.UNAFFECTED: "is unaffected",
    RelationStatus.NO_EVIDENCE: "cannot be judged",
}


def load_scenarios() -> list[dict[str, Any]]:
    data = yaml.safe_load(SUITE_YAML.read_text(encoding="utf-8"))
    return [{"id": f"s{i:02d}", **item} for i, item in enumerate(data["scenarios"], start=1)]


def all_sentences(scenarios: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for s in scenarios:
        for text in [*s["context"], s["action"]]:
            seen.setdefault(text, None)
    return list(seen)


def frames_from_conllu(path: Path = SUITE_CONLLU) -> dict[str, Any]:
    """Frames rebuilt with MLM's builder from the frozen parses (no parser needed)."""
    from splm.config import Config
    from splm.language.packs import LanguagePackRegistry
    from splm.linguistic.conllu import parse_conllu
    from splm.linguistic.morphology import MorphologyEngine
    from splm.linguistic.semantic_roles import SemanticRoleEngine
    from splm.phrase.builder import PhraseFrameBuilder

    config = Config.load(apply_env=False, overrides={"app.lexicon.auto_download": False})
    registry = LanguagePackRegistry(config.language_packs_dir)
    builder = PhraseFrameBuilder(registry, morphology=MorphologyEngine(registry),
                                 semantic_roles=SemanticRoleEngine(registry))
    document = parse_conllu(path.read_text(encoding="utf-8"), "en")
    return {s.text.strip(): builder.build(s) for s in document.sentences}


# -- answers ------------------------------------------------------------------------------------

DETERMINERS = {"the", "a", "an", "my", "his", "her", "their", "our", "your", "its", "this", "that", "all"}
#: First-word verb forms in ACM's state phrases, singular -> plural/first person.
AGREE = {"is": "are", "has": "have", "gains": "gain", "loses": "lose", "now": "now", "acts": "act",
         "receives": "receive", "wins": "win", "falls": "fall", "lets": "let", "performs": "perform",
         "collides": "collide", "holds": "hold", "owes": "owe", "knows": "know", "arrives": "arrive",
         "leaves": "leave", "exists": "exist", "does": "do", "no": "no", "loses": "lose"}


def _name(label: str) -> str:
    """How a subject reads in an answer: I for the model itself, 'the' before common nouns."""
    if label == "self":
        return "I"
    words = label.split()
    if words and label[:1].islower() and words[0].lower() not in DETERMINERS:
        return f"the {label}"
    return label


def _plural(label: str, key: str) -> bool:
    """A subject is plural when its surface head is the lemma plus -s ('volunteers' / 'volunteer')."""
    if label == "self":
        return True  # first person agrees like a plural: I gain, I lose
    head = label.split()[-1].lower()
    return head != key.split()[-1] and head in {key + "s", key + "es"}


ADVERBS = {"no", "longer", "now", "not"}


def _agree(phrase: str, plural: bool, first_person: bool = False) -> str:
    """Conjugate the phrase's verb for a plural subject or 'I' (skipping 'no longer', 'now')."""
    if not plural:
        return phrase
    words = phrase.split(" ")
    i = 0
    while i < len(words) and words[i] in ADVERBS:
        i += 1
    if i < len(words):
        w = words[i]
        if first_person and w == "is":
            words[i] = "am"
        elif w in AGREE:
            words[i] = AGREE[w]
        elif w.endswith("s") and not w.endswith("ss"):
            words[i] = w[:-1]
    return " ".join(words)


def _say(label: str, key: str, phrases: list[str]) -> str:
    plural = _plural(label, key)
    return f"{_name(label)} {_join([_agree(p, plural, label == 'self') for p in phrases])}"


NO_ARTICLE = {"production"}


def _place(label: str) -> str:
    """'in Paris' for named places, 'at the museum' for common ones."""
    if label[:1].isupper():
        return f"in {label}"
    return f"at {label}" if label in NO_ARTICLE else f"at {_name(label)}"


def _subject_first(text: str) -> str:
    """Place sentences start with their subject ('self arrives'): make it read 'I arrive'."""
    if text.startswith("self "):
        return "I " + _agree(text[5:], True, True)
    return text


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _join(parts: list[str]) -> str:
    parts = list(dict.fromkeys(p for p in parts if p))
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _lead(report: ConsequenceReport) -> str:
    if report.condition:
        return f"Only if {report.condition}: "
    if report.tense == "past":
        return ""
    return "If it happens: " if report.tense == "future" else ""


def _why(c: Consequence, report: ConsequenceReport) -> str:
    trace = report.trace
    if c.source.startswith("rule:"):
        concept = c.source.split(":", 1)[1]
        roles = [b for b in trace.get("bindings", []) if b["key"] == c.about]
        role = "; ".join(f"{c.about_label} is the {b['concept_role']} (MLM {b['mlm_role'] or 'implied'})" for b in roles)
        fact = str(c.fact) if c.fact else ""
        return f"{concept} rule{(': ' + role) if role else ''} → {fact}"
    if c.source.startswith("impact:"):
        rule = next((r for r in trace.get("rules", []) if r["aspect"] == c.about and r["scope"] == c.target.value), None)
        if rule:
            when = []
            if rule["when_concepts"]:
                when.append(f"{report.concept} is one of {'/'.join(rule['when_concepts'])}")
            if rule["when_categories"]:
                when.append(f"something involved is {'/'.join(rule['when_categories'])}")
            return f"impact rule ({rule['scope']}: {rule['aspect']}) fires when " + " and ".join(when)
    if c.source == "frame":
        return "MLM placed the action here (WHERE)"
    if c.source == "generic":
        return f"ACM has no concept for '{report.predicate}': generic, no verdict"
    return c.source


def _relation_answer(r: Relation) -> dict[str, Any]:
    intention = r.intention
    noun = "plan" if intention.kind == "goal" else "earlier action"
    verb = "wants to" if intention.kind == "goal" else "did:"
    owner = _name(intention.owner_label)
    return {
        "subject": owner,
        "kind": "goal",
        "question": f"What happens to {owner}'s {noun} ({verb} {intention.text.rstrip('.')})?",
        "answer": _cap(f"{owner}'s {noun} {STATUS_WORDS[r.status]}."),
        "status": r.status.value,
        "why": [r.reason],
    }


def answers(report: ConsequenceReport) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    lead = _lead(report)

    if report.predicate is None:
        return [{"subject": "-", "kind": "none", "question": "What happens next?",
                 "answer": "ACM found no action to evaluate.", "why": report.notes}]
    if not report.realized:
        return [{"subject": report.actor_label or "-", "kind": "negated", "question": "What happens next?",
                 "answer": f"Nothing. The sentence says {report.actor_label} does not {report.predicate}, so none of the "
                           "consequences follow — for anyone.",
                 "why": ["negation in MLM's frame cancels every state change and every effect on goals"]}]
    if report.trace.get("concept") is None and not report.consequences:
        return [{"subject": report.actor_label or "-", "kind": "state", "question": "What happens next?",
                 "answer": "Nothing changes: the sentence describes a state, not an action.", "why": report.notes}]

    def group(target: Target) -> dict[str, list[Consequence]]:
        groups: dict[str, list[Consequence]] = {}
        for c in report.for_target(target):
            if c.fact is not None:
                groups.setdefault(c.about_label, []).append(c)
        return groups

    actor = report.actor_label
    actor_rows = group(Target.ACTOR).get(actor or "", [])
    own = report.own_goals()
    if actor:
        key = report.actor or actor
        question = "What happens next to me (the model, judging its own plan)?" if report.self_view else \
            f"What happens next to {_name(actor)}?"
        if actor_rows:
            text = _cap(f"{lead}{_say(actor, key, [c.text for c in actor_rows])}.")
        else:
            text = f"{_cap(_name(actor))} {'act' if _plural(actor, key) else 'acts'}; ACM's rules record no change to " \
                   f"{'me' if report.self_view else _name(actor)} as a result."
        why = [_why(c, report) for c in actor_rows]
        for r in own:
            text += f" {'My' if report.self_view else 'Their'} own aim ('{r.intention.text}') {STATUS_WORDS[r.status]}."
            why.append(r.reason)
        out.append({"subject": _name(actor), "kind": "actor", "question": question, "answer": text, "why": why})

    for who, rows in group(Target.IMPACTED).items():
        generic = all(not c.informative for c in rows)
        text = _cap(f"{lead}{_say(who, rows[0].about, [c.text for c in rows])}.")
        if generic:
            text += " (Generic: ACM knows no concept for this verb, so it gives no verdict.)"
        out.append({"subject": _name(who), "kind": "impacted", "question": f"What happens next to {_name(who)}?",
                    "answer": text, "why": [_why(c, report) for c in rows]})

    for r in report.other_relations():
        out.append(_relation_answer(r))

    for where, rows in group(Target.ENVIRONMENT).items():
        texts = [_subject_first(c.text) for c in rows]
        out.append({"subject": _name(where), "kind": "place", "question": f"What happens {_place(where)}?",
                    "answer": _cap(f"{lead}{_place(where)}: {_join(texts)}."), "why": [_why(c, report) for c in rows]})

    from acm.render import layer_extent

    for target, name in LAYER_NAMES.items():
        rows = [c for c in report.for_target(target) if c.fact is None]
        if not rows:
            continue
        extent = layer_extent(report, target)
        label = f"{name} ({extent})" if extent and extent not in {"not known", "no place stated"} else name
        parts = [f"{c.text} ({DIRECTION_WORDS.get(c.direction or '0')})" for c in rows]
        out.append({"subject": label, "kind": "layer", "question": f"What happens to {label}?",
                    "answer": _cap(f"{lead}{_join(parts)}."), "why": [_why(c, report) for c in rows], "layer": target.value})

    silent = [name for target, name in LAYER_NAMES.items() if not report.for_target(target)]
    unknown_bits = [f"{u.about_label}: {u.text}" for u in report.unknowns]
    if silent or unknown_bits or report.notes:
        text_parts = []
        if silent:
            text_parts.append(f"No rule speaks about {_join(silent)} — that is no evidence, not 'no impact'")
        text_parts += unknown_bits
        out.append({"subject": "limits", "kind": "limits", "question": "What can't ACM tell here?",
                    "answer": ". ".join(text_parts) + ".", "why": report.notes})
    return out


def reasoning(report: ConsequenceReport) -> list[dict[str, Any]]:
    """The chain ACM followed, step by step, for the visual trace."""
    t = report.trace
    frame = t.get("frame", {})
    roles = []
    for slot, label in (("subject", "WHO"), ("objects", "WHAT"), ("recipients", "TO WHOM"), ("destination", "WHERE TO"),
                        ("source", "FROM WHERE"), ("location", "WHERE"), ("time", "WHEN"), ("manner", "HOW"),
                        ("instrument", "USING"), ("goal", "WHY / GOAL"), ("condition", "IF")):
        for e in frame.get(slot, []):
            roles.append(f"{label}={e['text']} ({e['role']})")
    by_target: dict[str, int] = {}
    for c in report.consequences:
        by_target[c.target.value] = by_target.get(c.target.value, 0) + 1
    return [
        {"step": "1. MLM reads the meaning",
         "detail": f"predicate '{report.predicate}' · " + (" · ".join(roles) or "no roles") +
                   f" · tense={report.tense or '?'}" + (" · NEGATED" if not report.realized else "")},
        {"step": "2. Concept", "detail": f"'{report.predicate}' → {t.get('concept') or 'no concept (generic)'}"},
        {"step": "3. Roles bound",
         "detail": " · ".join(f"{b['concept_role']} = {b['entity']} ({b['mlm_role'] or 'implied'})" for b in t.get("bindings", []))
                   + (f" · unfilled: {', '.join(t.get('unfilled_roles', []))}" if t.get("unfilled_roles") else "") or "—"},
        {"step": "4. State changes",
         "detail": " · ".join(f"{f['fact']}{' ★' if f['primary'] else ''}" for f in t.get("facts", [])) or "none"},
        {"step": "5. Who each change lands on",
         "detail": " · ".join(f"{k}: {v}" for k, v in by_target.items() if k in {"actor", "impacted", "environment"}) or "nobody"},
        {"step": "6. Other people's goals compared",
         "detail": " · ".join(f"{r.intention.owner_label} → {r.status.value}" for r in report.relations) or "no goals in context"},
        {"step": "7. Layer rules",
         "detail": (f"categories: {', '.join(t.get('categories', [])) or 'none'} · fired: "
                    + (", ".join(f"{r['scope']}/{r['aspect']}" for r in t.get("rules", [])) or "none"))},
        {"step": "8. Certainty", "detail": f"{report.certainty:.2f} (rule weight from tense/modality/condition — not a probability)"},
    ]


def entity_graph(report: ConsequenceReport) -> dict[str, Any]:
    """Subjects around the action, each edge labelled with what happens to it."""
    nodes = [{"id": "action", "label": report.predicate or "?", "kind": "action", "concept": report.concept}]
    edges = []
    seen: dict[str, str] = {}

    def node(key: str, label: str, kind: str) -> str:
        if key not in seen:
            seen[key] = f"n{len(seen)}"
            nodes.append({"id": seen[key], "label": label, "kind": kind})
        return seen[key]

    for c in report.consequences:
        if c.fact is None:
            nid = node(f"layer:{c.target.value}", c.target.value, "layer")
            edges.append({"from": "action", "to": nid, "label": c.about, "basis": c.basis, "direction": c.direction})
        elif c.target in {Target.ACTOR, Target.IMPACTED, Target.ENVIRONMENT}:
            nid = node(c.about, c.about_label, c.target.value)
            edges.append({"from": "action", "to": nid, "label": c.text, "basis": c.basis})
    for r in report.relations:
        nid = node(f"goal:{r.intention.owner}:{r.intention.text}", f"{r.intention.owner_label}: {r.intention.text}", "goal")
        edges.append({"from": "action", "to": nid, "label": r.status.value, "basis": "relation", "status": r.status.value})
    return {"nodes": nodes, "edges": edges}


def run_suite(frames: dict[str, Any] | None = None) -> dict[str, Any]:
    from acm.demo import blast_radius, report_summary
    from acm.render import to_mindmap, to_text

    scenarios = load_scenarios()
    frames = frames if frames is not None else frames_from_conllu()
    engine = ConsequenceEngine()
    items, missing = [], []
    for s in scenarios:
        texts = [*s["context"], s["action"]]
        if not all(t in frames for t in texts):
            missing.append(s["action"])
            continue
        report = engine.predict([frames[t] for t in texts], language="en")
        qa = answers(report)
        items.append({
            "id": s["id"], "theme": s["theme"], "shows": s["shows"],
            "context": s["context"], "action": s["action"],
            "summary": report_summary(report),
            "answers": qa,
            "reasoning": reasoning(report),
            "trace": report.trace,
            "graph": entity_graph(report),
            "rings": blast_radius(report),
            "report_text": to_text(report),
            "mindmap": to_mindmap(report),
        })
    themes: dict[str, int] = {}
    for item in items:
        themes[item["theme"]] = themes.get(item["theme"], 0) + 1
    stats = {
        "scenarios": len(items),
        "questions": sum(len(i["answers"]) for i in items),
        "themes": themes,
        "concepts": sorted({i["summary"]["concept"] or "generic" for i in items}),
        "relations": _count(r["status"] for i in items for r in i["answers"] if r["kind"] == "goal"),
        "layers_reached": _count(a["layer"] for i in items for a in i["answers"] if a.get("layer")),
    }
    return {"stats": stats, "items": items, "missing": missing,
            "parse": "frozen MLM (Stanza) parses in examples/inference_suite.conllu; frames rebuilt by MLM's builder"}


def _count(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
