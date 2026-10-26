"""The bundled multimodal demo, end to end, as one JSON-ready result.

    text  (stated plan)  -> MLM frames -> ACM  - geometry ASSUMED (text has none)
    image (shows scene)  -> fixture replay -> MLM scene -> ACM
    video (shows events) -> fixture replay -> MLM timeline -> cut at T -> ACM
                            -> scripted outcome after T -> comparison
    sale  (text)         -> ACM's rule-derived ownership/payment consequences

Every flow runs the real pipeline: MLM schemas and adapters, the tabletop
simulator, ACM's engine. Only the *extraction* is replayed from fixtures - and
every result says so.
"""

from __future__ import annotations

from typing import Any

from splm.meaning import MeaningDocument, ProposedAction, SceneState, Status
from splm.meaning import demo as material

from acm.engine import ConsequenceEngine
from acm.evaluation import Episode, compare_outcome
from acm.multimodal import MultimodalBridge, ScenarioResult
from acm.render import to_mindmap, to_text
from acm.schema import ConsequenceReport, Target

DEMO_BADGE = "Demo mode — example extraction and simulated consequences"
NO_EVIDENCE = "No supporting evidence"
SIX_CIRCLES = [
    (Target.ACTOR, "Actor"),
    (Target.IMPACTED, "Impacted entities"),
    (Target.OTHER_ACTORS, "Other actors"),
    (Target.ENVIRONMENT, "Environment"),
    (Target.SOCIETY, "Society"),
    (Target.EARTH, "Earth"),
]
WIDER_LAYERS = [Target.NEIGHBOUR, Target.ORGANIZATION, Target.CITY, Target.COUNTRY]


def _field(value: Any, status: str, source: str) -> dict[str, Any]:
    return {"value": value, "status": status, "source": source}


def _unknown(reason: str) -> dict[str, Any]:
    return _field(None, Status.UNKNOWN.value, reason)


# -- six circles ------------------------------------------------------------------------

def circles(report: ConsequenceReport) -> list[dict[str, Any]]:
    """The six circles, each row with its basis; empty circles say 'No supporting evidence'."""
    out = []
    for target, title in SIX_CIRCLES:
        rows: list[dict[str, Any]] = []
        for c in report.for_target(target):
            rows.append({
                "about": c.about_label, "text": c.text, "basis": c.basis,
                "source": c.source, "direction": c.direction, "evidence": c.evidence[:3],
            })
        if target == Target.ACTOR:
            for r in report.own_goals():
                rows.append({"about": r.intention.owner_label, "text": f"own goal '{r.intention.text}': {r.status.value}",
                             "basis": "rule", "source": "relation", "reason": r.reason})
        if target == Target.OTHER_ACTORS:
            for r in report.other_relations():
                rows.append({"about": r.intention.owner_label, "text": f"{r.intention.text}: {r.status.value}",
                             "basis": "rule", "source": "relation", "reason": r.reason})
        if target == Target.IMPACTED:
            for u in report.unknowns:
                rows.append({"about": u.about_label, "text": f"{u.aspect}: {u.text}", "basis": "unknown",
                             "source": "simulation.yaml", "needs": u.needs})
        out.append({"key": target.value, "title": title, "rows": rows, "empty": NO_EVIDENCE if not rows else None})
    wider = [c for t in WIDER_LAYERS for c in report.for_target(t)]
    out.append({"key": "wider", "title": "Wider blast radius (neighbour · organization · city · country)",
                "rows": [{"about": c.about_label, "text": c.text, "basis": c.basis} for c in wider],
                "empty": NO_EVIDENCE if not wider else None})
    return out


def scenario_json(result: ScenarioResult, label: str) -> dict[str, Any]:
    outcome = result.outcome
    final = outcome.final_state
    positions = {}
    if final is not None:
        for e in final.entities:
            if e.geometry.position is not None:
                positions[e.id] = [e.geometry.position.x, e.geometry.position.y]
            elif e.cls == "cup":
                positions[e.id] = None  # landing position unknown
    return {
        "key": result.key,
        "label": label,
        "action": result.action.model_dump(mode="json") if result.action else None,
        "events": [ev.model_dump(mode="json") for ev in outcome.events],
        "changes": [c.model_dump(mode="json") for c in outcome.changes],
        "final_positions": positions,
        "assumptions": [a.model_dump(mode="json") for a in outcome.assumptions],
        "unknowns": outcome.unknowns,
        "uncertainty": outcome.uncertainty.model_dump(mode="json"),
        "backend": outcome.backend.model_dump(mode="json"),
        "circles": circles(result.report),
        "report_text": to_text(result.report) if result.action else result.report.notes[0],
        "mindmap": to_mindmap(result.report) if result.action else None,
        "acm_json": result.report.model_dump(mode="json", exclude={"graph"}),
        "graph": result.report.graph,
        "decision_time_s": result.decision_time_s,
    }


def scene_json(state: SceneState) -> dict[str, Any]:
    entities = []
    for e in state.entities:
        g = e.geometry
        entities.append({
            "id": e.id, "class": e.cls, "attributes": e.attributes, "status": e.status.value,
            "position": [g.position.x, g.position.y] if g.position else None,
            "radius_m": g.footprint_radius.metres if g.footprint_radius else None,
            "extent": [g.extent.x_min, g.extent.y_min, g.extent.x_max, g.extent.y_max] if g.extent else None,
            "evidence": [f"{ev.source_type.value}:{ev.uri}" + (f"@{ev.timestamp_s}s" if ev.timestamp_s is not None else "")
                         for ev in e.evidence[:2]],
        })
    relations = [{"subject": o.subject, "relation": o.relation, "object": o.object, "value": o.value,
                  "status": o.status.value, "note": o.note} for o in state.observations if o.relation]
    return {"timestamp_s": state.timestamp_s, "entities": entities, "relations": relations,
            "frames": [f.value for f in state.coordinate_frames],
            "calibration": state.calibration.model_dump(mode="json") if state.calibration else None}


# -- meaning fields per evidence type ---------------------------------------------------------

def _role_text(frame, slot: str) -> str | None:
    items = [e.text for e in frame.slot(slot) if e.frame is None]
    return ", ".join(items) or None


def text_meaning(doc: MeaningDocument, action: ProposedAction) -> dict[str, Any]:
    plan = next(g for g in doc.goals if g.frame is not None)
    push = next(e.frame for _, e in plan.frame.elements() if e.frame is not None)
    obj = next((e for e in push.slot("objects")), None)
    return {
        "evidence_kind": "The text states a plan. It does not show that anything happened.",
        "who": _field("self (\"I\")", Status.OBSERVED.value, "stated: subject of 'plan'"),
        "action": _field("push (planned, not observed)", Status.OBSERVED.value, f"stated: '{plan.text}'"),
        "what": _field(obj.annotations.get("entity_id", obj.text) if obj else None, Status.INFERRED.value,
                       "'the blue cup' grounded to the only blue cup in the scenario"),
        "to_whom": _unknown("not stated"),
        "where": _field("table_01", Status.OBSERVED.value, "stated: 'a table'"),
        "direction": _field(_role_text(push, "destination") or "toward the right edge", Status.OBSERVED.value,
                            "stated: 'toward the right edge'"),
        "when": _field("future (a plan)", Status.OBSERVED.value, "stated by 'plan to'; no time given"),
        "how": _unknown("not stated"),
        "why": _unknown("not stated: no purpose is given for the push"),
        "observed_states": [
            {"text": "blue_cup_01 near the right edge of table_01", "status": "observed", "source": "stated by the text"},
            {"text": "red_cup_01 farther from the edge", "status": "observed", "source": "stated by the text"},
            {"text": "positions (x, y in m) and cup size", "status": "assumed",
             "source": "scenario defaults — the text states no coordinates"},
        ],
        "proposed_action": action.model_dump(mode="json"),
        "unknowns": ["purpose of the push", "force", "friction", "mass", "material", "contents", "table height"],
        "evidence": [{"type": "text", "ref": g.text} for g in doc.goals] +
                    [{"type": "text", "ref": e.evidence[0].text_span} for e in doc.events],
        "parse_note": "Frames built by MLM's phrase builder from hand-written UD trees (no parser model in demo mode).",
    }


def image_meaning(doc: MeaningDocument, action: ProposedAction) -> dict[str, Any]:
    state = doc.states[0]
    return {
        "evidence_kind": "The image shows a scene. It cannot show that anyone pushed anything.",
        "who": _field("self (the proposer)", Status.ASSUMED.value, "supplied with the proposed action, not in the image"),
        "action": _field("push (proposed)", Status.ASSUMED.value, "supplied separately; the image shows no action"),
        "what": _field("blue_cup_01", Status.OBSERVED.value, "entity in the image (fixture replay)"),
        "to_whom": _unknown("not applicable"),
        "where": _field("table_01", Status.OBSERVED.value, "entity in the image (fixture replay)"),
        "direction": _field("+x (toward the right edge), 0.20 m", Status.ASSUMED.value, "proposed-action parameters"),
        "when": _field("a single moment (the image)", Status.OBSERVED.value, "still image: no time"),
        "how": _unknown("not shown"),
        "why": _unknown("a still image does not show purposes"),
        "observed_states": [
            {"text": f"{o.subject} {o.relation} {o.object}" + (f" ({o.value})" if o.value else ""),
             "status": o.status.value, "source": o.note or "extraction"} for o in state.observations if o.relation
        ],
        "proposed_action": action.model_dump(mode="json"),
        "rejected_claims": doc.rejected_claims,
        "unknowns": ["who will act", "force", "friction", "mass", "material", "contents", "table height"],
        "evidence": [{"type": "image", "ref": "tabletop_scene.svg", "backend": doc.source.backend.name}],
        "notes": doc.notes,
    }


def video_meaning(doc: MeaningDocument, action: ProposedAction, t: float) -> dict[str, Any]:
    view = doc.available_at(t)
    state = view.state_at(t)
    return {
        "evidence_kind": f"The video shows events. The prediction uses only frames up to t={t}s.",
        "who": _field("pusher_01", Status.OBSERVED.value, f"tracked in frames up to t={t}s (track 3, synthetic session)"),
        "action": _field("push (proposed for t ≥ 2.0 s)", Status.ASSUMED.value,
                         "supplied proposed action at the checkpoint; the push itself is after T"),
        "what": _field("blue_cup_01", Status.OBSERVED.value, "track 1, explicit association"),
        "to_whom": _unknown("not applicable"),
        "where": _field("table_01", Status.OBSERVED.value, "static entity with calibrated extent"),
        "direction": _field("+x (toward the right edge), 0.20 m", Status.ASSUMED.value, "proposed-action parameters"),
        "when": _field(f"decision time T = {t} s", Status.OBSERVED.value, "video timestamp"),
        "how": _unknown("contact force is not observable"),
        "why": _unknown("video does not show purposes"),
        "observed_states": [
            {"text": f"{o.subject} {o.relation} {o.object}", "status": o.status.value, "source": f"frame t={state.timestamp_s}s"}
            for o in state.observations
        ] + [{"text": "pusher_01 touching blue_cup_01's left side", "status": "inferred",
              "source": f"box contact at t={t}s"}],
        "events_before_T": [e.model_dump(mode="json", exclude={"frame"}) for e in view.events],
        "proposed_action": action.model_dump(mode="json"),
        "unknowns": ["force", "friction", "mass", "material", "contents", "table height"],
        "evidence": [{"type": "video", "ref": f"frame {s.timestamp_s}s"} for s in view.states],
    }


def generic_text_meaning(doc: MeaningDocument) -> dict[str, Any]:
    """Meaning fields read straight off parsed frames - used for live text."""
    frame = None
    plan_text = None
    for goal in reversed(doc.goals):  # the action is the last clause; earlier ones are context
        if goal.frame is None:
            continue
        if goal.frame.tense is not None and goal.frame.tense.value == "future":
            frame, plan_text = goal.frame, goal.text  # "I will sell ...": the frame itself is the plan
        else:
            nested = next((e.frame for _, e in goal.frame.elements() if e.frame is not None), None)
            frame, plan_text = (nested or goal.frame), goal.text
        break
    if frame is None and doc.events:
        frame = doc.events[-1].frame
    if frame is None:
        raise ValueError("MLM found no action in the text")
    stated = Status.OBSERVED.value

    def slot(name: str, reason: str) -> dict[str, Any]:
        text = _role_text(frame, name)
        return _field(text, stated, "stated in the text") if text else _unknown(reason)

    who = _role_text(frame, "subject") or (doc.goals[0].owner if doc.goals else None)
    return {
        "evidence_kind": "Live MLM parse of the text. Text states; it does not show.",
        "who": _field(who, stated, "stated") if who else _unknown("not stated"),
        "action": _field(f"{frame.predicate.lemma}" + (" (planned)" if plan_text else ""), stated, "parsed predicate"),
        "what": slot("objects", "not stated"),
        "to_whom": slot("recipients", "not stated"),
        "where": slot("location", "not stated"),
        "direction": slot("destination", "not stated"),
        "when": _field(frame.tense.value if frame.tense else None, stated, "grammatical tense") if frame.tense else _unknown("no tense"),
        "how": slot("manner", "not stated"),
        "why": slot("goal", "not stated: no purpose is given") if frame.goal else slot("cause", "not stated: no purpose is given"),
        "observed_states": [{"text": e.evidence[0].text_span, "status": stated, "source": "stated by the text"} for e in doc.events],
        "unknowns": ["positions are assumed (text gives no geometry)"],
        "evidence": [{"type": "text", "ref": doc.source.text_span}],
    }


def live_text_result(text: str, action_key: str, pipeline: Any) -> dict[str, Any]:
    """Live: parse ``text`` with MLM, then run ACM on the chosen tabletop action (assumed geometry)."""
    from splm.meaning.adapters import TextAdapter

    actions = material.proposed_actions(actor="self")
    if action_key not in actions:
        raise ValueError(f"unknown action {action_key!r}")
    doc = TextAdapter(pipeline).analyze(text, language="en", scene=material.assumed_text_scene())
    meaning = generic_text_meaning(doc)
    result = MultimodalBridge().consequences(doc, actions[action_key], key=action_key)
    return {
        "mode": "live",
        "meaning": meaning,
        "meaning_json": doc.model_dump(mode="json"),
        "scenario": scenario_json(result, material.ACTION_LABELS[action_key]),
        "scene": scene_json(doc.states[0]),
    }


# -- the whole demo --------------------------------------------------------------------------

def run_demo() -> dict[str, Any]:
    bridge = MultimodalBridge()
    labels = material.ACTION_LABELS
    out: dict[str, Any] = {"mode": "demo", "badge": DEMO_BADGE, "action_labels": labels, "flows": {}}

    text_doc = material.text_document()
    text_actions = material.proposed_actions(actor="self")
    text_results = bridge.compare(text_doc, text_actions)
    out["flows"]["text"] = {
        "input": {"text": material.TABLETOP_TEXT},
        "meaning": text_meaning(text_doc, text_actions["push_edge"]),
        "meaning_json": text_doc.model_dump(mode="json"),
        "scene": scene_json(text_doc.states[0]),
        "scenarios": {k: scenario_json(r, labels[k]) for k, r in text_results.items()},
    }

    image_doc = material.image_document()
    image_actions = material.proposed_actions(actor="self")
    image_results = bridge.compare(image_doc, image_actions)
    out["flows"]["image"] = {
        "input": {"image": "tabletop_scene.svg", "annotated": "tabletop_scene_annotated.svg",
                  "replay": image_doc.source.backend.model_dump(mode="json")},
        "meaning": image_meaning(image_doc, image_actions["push_edge"]),
        "meaning_json": image_doc.model_dump(mode="json"),
        "scene": scene_json(image_doc.states[0]),
        "scenarios": {k: scenario_json(r, labels[k]) for k, r in image_results.items()},
    }

    t = material.VIDEO_CHECKPOINT_S
    video_doc = material.video_document()
    video_actions = material.proposed_actions(actor="pusher_01", issued_at_s=t)
    video_results = bridge.compare(video_doc, video_actions, at_time=t)
    horizon = video_results["push_edge"].outcome.horizon_s
    observed = video_doc.state_at(t + horizon)
    comparison = compare_outcome(video_results["push_edge"].outcome, video_doc.state_at(t), observed)
    episode = Episode(
        id="demo-video-push-01", split="eval", inputs=[video_doc.source],
        extraction_config={"replay": str(material.VIDEO_FIXTURE.name), "sample_fps": 2.0},
        backends=[video_doc.source.backend, video_results["push_edge"].outcome.backend],
        decision_time_s=t, horizon_s=horizon, meaning_at_decision=video_doc.available_at(t),
        proposed_action=video_actions["push_edge"], prediction=video_results["push_edge"].outcome,
        actual_action=next((e for e in video_doc.events if e.predicate == "push"), None),
        subsequent=[s for s in video_doc.states if s.timestamp_s is not None and s.timestamp_s > t],
        comparison=comparison,
        notes=["Scripted synthetic outcome: this demonstrates the workflow, not independent validation."],
    )
    out["flows"]["video"] = {
        "input": {"script": "tabletop_video_script.json", "checkpoint_s": t,
                  "replay": video_doc.source.backend.model_dump(mode="json")},
        "meaning": video_meaning(video_doc, video_actions["push_edge"], t),
        "meaning_json": video_doc.available_at(t).model_dump(mode="json"),
        "timeline": [{"id": e.id, "predicate": e.predicate, "start_s": e.interval.start_s, "end_s": e.interval.end_s,
                      "causal_attribution": e.causal_attribution,
                      "roles": {r: [f.entity_id or f.text for f in v] for r, v in e.roles.items()}}
                     for e in video_doc.events],
        "scene": scene_json(video_doc.state_at(t)),
        "scenarios": {k: scenario_json(r, labels[k]) for k, r in video_results.items()},
        "scripted_outcome": {"t": observed.timestamp_s, "scene": scene_json(observed),
                             "label": "Scripted outcome (synthetic animation) - not independent real-world validation"},
        "comparison": comparison.model_dump(mode="json"),
        "episode_id": episode.id,
    }

    frames = material.text_frames()
    sale_frames = [frames[s] for s in (*material.SALE_CONTEXT, material.SALE_TEXT)]
    sale = ConsequenceEngine().predict(sale_frames, language="en")
    from splm.meaning.adapters import TextAdapter
    from splm.meaning.schema import BackendInfo

    sale_doc = TextAdapter().from_frames(
        sale_frames, text=" ".join([*material.SALE_CONTEXT, material.SALE_TEXT]),
        info=BackendInfo(name="splm-phrase-builder", version="hand-annotated-trees", kind="parser", live=False),
    )
    sale_meaning = generic_text_meaning(sale_doc)
    sale_meaning["evidence_kind"] = "The text states a plan and two other people's goals. Nothing is observed."
    sale_meaning["unknowns"] = ["price", "when the sale happens"]
    out["flows"]["sale"] = {
        "input": {"text": material.SALE_TEXT, "context": material.SALE_CONTEXT},
        "meaning": sale_meaning,
        "meaning_json": sale_doc.model_dump(mode="json"),
        "circles": circles(sale),
        "report_text": to_text(sale),
        "mindmap": to_mindmap(sale),
        "acm_json": sale.model_dump(mode="json", exclude={"graph"}),
        "note": "Ownership and payment changes are rule-derived consequences (packs/universal/concepts.yaml: SALE).",
    }
    out["episode"] = episode.model_dump(mode="json")
    return out
