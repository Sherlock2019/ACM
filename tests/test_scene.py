"""ACM scene engine: validation, state, demo content, branches, export and provider failures."""

from __future__ import annotations

import copy
import json

import pytest
import yaml

from acm import llm
from acm.scene import (
    DIRECTIONS_SCHEMA, SCENES_DIR, DemoProvider, ModelProvider, ProviderError, Scene, SceneError, Source, Status,
    bundle, check_directions, directions, final_state, generate_branches, load_scene, select_branch, timeline,
    validate_scene,
)
from acm.scene.providers import parse_generated


@pytest.fixture(scope="module")
def raw() -> dict:
    return yaml.safe_load((SCENES_DIR / "car_sale.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def scene() -> Scene:
    return load_scene("car_sale")


def _invalid(raw: dict, mutate) -> list[str]:
    data = copy.deepcopy(raw)
    mutate(data)
    with pytest.raises(SceneError) as info:
        validate_scene(Scene.model_validate(data))
    return info.value.problems


# --- validation -------------------------------------------------------------------------

def test_rejects_unknown_actor_in_event(raw):
    problems = _invalid(raw, lambda d: d["events"][1].update(actor="john"))
    assert any("unknown actor 'john'" in p for p in problems)


def test_rejects_unknown_object_and_target(raw):
    def mutate(d):
        d["events"][2]["object"] = "bicycle"
        d["events"][2]["target"] = "nobody"
    problems = _invalid(raw, mutate)
    assert any("unknown object 'bicycle'" in p for p in problems)
    assert any("unknown target 'nobody'" in p for p in problems)


def test_rejects_effect_on_unknown_subject_and_holder(raw):
    problems = _invalid(raw, lambda d: d["events"][6]["effects"].extend(
        [{"subject": "boat", "attribute": "x", "value": 1}, {"subject": "keys", "attribute": "holder", "value": "john"}]))
    assert any("unknown subject 'boat'" in p for p in problems)
    assert any("unknown actor 'john'" in p for p in problems)


def test_rejects_out_of_order_events_and_unknown_verb(raw):
    def mutate(d):
        d["events"][3]["order"] = 1
        d["events"][4]["verb"] = "teleport"
    problems = _invalid(raw, mutate)
    assert any("strictly increasing" in p for p in problems)
    assert any("'teleport'" in p for p in problems)


def test_rejects_unknown_evidence_and_stated_without_evidence(raw):
    def mutate(d):
        d["demo"]["consequences"][0]["evidence"] = ["e99"]
        d["demo"]["consequences"][2]["evidence"] = []
    problems = _invalid(raw, mutate)
    assert any("unknown event 'e99'" in p for p in problems)
    assert any("must cite the events" in p for p in problems)


def test_inference_cannot_be_stated(raw):
    data = copy.deepcopy(raw)
    data["actors"][1]["inferences"][1]["status"] = "stated"
    with pytest.raises(ValueError):
        Scene.model_validate(data)


def test_branch_with_unknown_actor_is_rejected(raw):
    problems = _invalid(raw, lambda d: d["demo"]["branches"][0]["events"][1].update(actor="john"))
    assert any("branch A" in p and "unknown actor 'john'" in p for p in problems)


# --- the demo scene ---------------------------------------------------------------------

def test_demo_preserves_objection_and_unresolved_handover(scene):
    end = final_state(scene)
    assert end["scene"]["sale"] == "disputed"
    assert end["scene"]["sarah_consent"] == "refused"
    assert end["scene"]["handover_completed"] is False
    assert end["car"]["owner"] == "sarah"          # ownership never transfers
    assert end["keys"]["holder"] == "mark"         # the keys stay with Mark
    assert end["keys"]["offered_to"] is None
    assert end["debt"]["status"] == "unpaid"
    assert scene.status == "Disputed; handover not completed"


def test_timeline_has_a_state_per_event(scene):
    steps = timeline(scene)
    assert [s["event"] for s in steps] == [None] + [e.id for e in scene.events]
    after_offer = next(s for s in steps if s["event"] == "e3")
    assert after_offer["state"]["keys"]["offered_to"] == "florence"
    assert "keys.offered_to" in after_offer["changed"]


def test_inferences_are_never_facts(scene):
    for actor in scene.actors:
        assert actor.inferences, actor.id
        assert all(i.status == Status.POSSIBLE for i in actor.inferences)


def test_analysis_covers_all_eight_scopes(scene):
    analysis = DemoProvider().analyze(scene)
    assert analysis.source == Source.AUTHORED_DEMO
    scopes = {c.scope for c in analysis.consequences}
    assert scopes == {s.id for s in scene.scopes} and len(scene.scopes) == 8
    outer = [c for c in analysis.consequences if c.scope in {"society", "economy", "world"}]
    assert outer and all(c.status == Status.NOT_IDENTIFIED for c in outer)
    assert not any("settled" in c.description and c.status == Status.STATED for c in analysis.consequences)


# --- branches -----------------------------------------------------------------------------

@pytest.mark.parametrize("bid,title,assumption", [
    ("A", "A repayment plan", "Mark accepts Sarah's objection."),
    ("B", "Florence steps back", "Florence will not take the car without Sarah's agreement."),
    ("C", "The argument escalates", "Mark insists on the sale."),
    ("D", "Sarah considers an offer", "Sarah is willing to discuss terms."),
])
def test_select_each_branch(scene, bid, title, assumption):
    result = select_branch(scene, bid)
    branch = result["branch"]
    assert branch.title == title and assumption in branch.assumptions
    assert branch.source == Source.AUTHORED_DEMO and branch.parent == scene.id
    assert branch.events and branch.plausibility
    assert result["timeline"][0]["state"] == final_state(scene)   # continues from scene 1
    assert result["directions"]["branch"] == bid


def test_branch_a_moves_the_keys_to_the_shelf(scene):
    end = select_branch(scene, "A")["timeline"][-1]["state"]
    assert end["keys"]["holder"] is None and end["keys"]["position"] == "shelf"
    assert end["notebook"]["holder"] == "mark"
    assert end["car"]["owner"] == "sarah"


def test_unknown_branch(scene):
    with pytest.raises(KeyError):
        select_branch(scene, "Z")


# --- export -------------------------------------------------------------------------------

def test_export_preserves_order_and_validates(scene):
    out = directions(scene)
    assert out["schema"] == DIRECTIONS_SCHEMA
    assert [a["event"] for a in out["actions"]] == [e.id for e in scene.events]
    assert [a["order"] for a in out["actions"]] == sorted(a["order"] for a in out["actions"])
    assert out["unsupported"] == []
    speak = [a for a in out["actions"] if a["verb"] == "speak"]
    assert speak and all(a["dialogue"] for a in speak)
    check_directions(json.loads(json.dumps(out)), scene)   # survives a JSON round trip


def test_export_rejects_tampered_order(scene):
    out = directions(scene)
    out["actions"][0], out["actions"][1] = out["actions"][1], out["actions"][0]
    with pytest.raises(SceneError):
        check_directions(out, scene)


def test_export_flags_unsupported_action(scene):
    branch = copy.deepcopy(select_branch(scene, "B")["branch"])
    branch.events[2].verb = None
    branch.events[2].type = branch.events[2].type.__class__("action")
    out = directions(scene, branch)
    assert out["unsupported"] and out["unsupported"][0]["event"] == branch.events[2].id


def test_bundle_is_json(scene):
    data = json.loads(json.dumps(bundle(scene), ensure_ascii=False))
    assert data["scene"]["id"] == "car_sale" and "demo" not in data["scene"]
    assert len(data["branches"]) == 4 and all(b["source"] == "authored_demo" for b in data["branches"])


# --- providers ----------------------------------------------------------------------------

def test_model_unavailable_falls_back_honestly(scene, monkeypatch):
    monkeypatch.setattr(llm, "status", lambda: (False, "no LLM server (test)"))
    with pytest.raises(ProviderError):
        ModelProvider().branches(scene)
    result = generate_branches(scene, "model")
    assert result["provider"] == "demo" and "no LLM server" in result["fallback"]
    assert all(b.source == Source.AUTHORED_DEMO for b in result["branches"])
    with pytest.raises(ProviderError):
        generate_branches(scene, "model", fallback=False)


def test_model_timeout_is_a_provider_error(scene, monkeypatch):
    monkeypatch.setattr(llm, "status", lambda: (True, "test-model"))

    def boom(*_a, **_k):
        raise llm.LLMUnavailable("timed out")
    monkeypatch.setattr(llm, "chat_json", boom)
    with pytest.raises(ProviderError, match="timed out"):
        ModelProvider().branches(scene)


@pytest.mark.parametrize("reply", [{}, {"branches": "nope"}, {"branches": []},
                                   {"branches": [{"title": "x", "assumptions": ["a"], "events": [{"actor": "john", "type": "dialogue", "dialogue": "hi"}]}]}])
def test_malformed_or_empty_model_output(scene, reply):
    with pytest.raises(ProviderError):
        parse_generated(reply, scene)


def test_valid_model_output_is_labelled_generated(scene):
    reply = {"branches": [{
        "title": "Florence asks for time", "assumptions": ["Florence wants to think"], "summary": "s",
        "events": [{"actor": "florence", "type": "dialogue", "verb": "speak", "target": "mark", "description": "asks for time",
                    "dialogue": "Let me think about it."}, {"actor": "mark", "type": "action", "verb": "fly", "description": "?"}],
        "goal_changes": [{"actor": "mark", "change": "waits", "effect": "negative"}],
        "inferences": {"sarah": [{"kind": "feeling", "text": "relieved"}]}, "plausibility": "she paused"}]}
    branches, rejected = parse_generated(reply, scene)
    assert rejected == [] and len(branches) == 1
    b = branches[0]
    assert b.source == Source.GENERATED_INFERENCE and b.parent == scene.id
    assert b.events[1].verb is None                     # out-of-vocabulary verb dropped, event kept
    assert all(e.source == Source.GENERATED_INFERENCE and not e.effects for e in b.events)
    assert b.inferences["sarah"][0].status == Status.POSSIBLE
