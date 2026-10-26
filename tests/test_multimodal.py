"""Multimodal bridge: simulator, branching, leakage, ACM mapping, evaluation, report."""

from __future__ import annotations

import pytest

from splm.meaning import CoordinateFrame, Point, ProposedAction, Quantity
from splm.meaning import demo as material

from acm.demo import run_demo
from acm.evaluation import Episode, EpisodeStore, compare_outcome
from acm.multimodal import MultimodalBridge
from acm.schema import Target
from acm.visual_report import render_report
from acm.world import (
    BackendUnavailable,
    FutureLeakage,
    PyBulletSimulator,
    SimulationError,
    TabletopSimulator,
    VJEPA2ACPredictor,
)


@pytest.fixture(scope="module")
def bridge():
    return MultimodalBridge()


@pytest.fixture(scope="module")
def image_doc():
    return material.image_document()


def events(outcome):
    return {(e.kind, e.entity_id) for e in outcome.events}


def push(distance=0.20, direction=0, target="blue_cup_01"):
    return ProposedAction(id="p", predicate="push", actor="self", target=target,
                          parameters={"direction_deg": Quantity(value=direction, unit="deg"),
                                      "distance": Quantity(value=distance, unit="m")})


# -- simulator -----------------------------------------------------------------------------------

def test_push_over_the_edge_falls_and_landing_is_unknown(image_doc):
    out = TabletopSimulator().predict(image_doc.states, push(), 2.0)
    assert {("crosses_edge", "blue_cup_01"), ("falls", "blue_cup_01"), ("remains_supported", "red_cup_01")} <= events(out)
    landing = next(c for c in out.changes if c.property == "landing_position")
    assert landing.status.value == "unknown" and landing.after is None
    assert {"applied force", "friction coefficients", "object masses", "materials"} <= set(out.unknowns)
    assert any(a.name == "push displacement" and a.unit == "m" for a in out.assumptions)


def test_short_push_overhangs_but_stays(image_doc):
    out = TabletopSimulator().predict(image_doc.states, push(distance=0.13), 2.0)
    assert ("overhangs_edge", "blue_cup_01") in events(out)
    assert ("falls", "blue_cup_01") not in events(out)


def test_collision_stops_at_contact_and_reports_the_unknown(image_doc):
    out = TabletopSimulator().predict(image_doc.states, push(distance=0.6, direction=180 - 5.71), 2.0)
    hit = next(e for e in out.events if e.kind == "collides")
    assert (hit.entity_id, hit.other_id) == ("blue_cup_01", "red_cup_01")
    assert "how red_cup_01 moves after being hit" in out.unknowns


def test_simulator_refuses_what_it_cannot_know(image_doc):
    sim = TabletopSimulator()
    with pytest.raises(SimulationError, match="is not assumed"):
        sim.predict(image_doc.states, ProposedAction(id="p", predicate="push", target="blue_cup_01"), 2.0)
    with pytest.raises(SimulationError, match="does not model"):
        sim.predict(image_doc.states, ProposedAction(id="p", predicate="throw", target="blue_cup_01"), 2.0)
    pixel_only = material.video_document().states[-1]  # the fallen cup has no calibrated position
    with pytest.raises(SimulationError, match="pixels are not metres"):
        sim.predict([pixel_only], push(), 2.0)


def test_alternatives_branch_from_one_immutable_state(bridge, image_doc):
    before = image_doc.model_dump_json()
    results = bridge.compare(image_doc, material.proposed_actions(actor="self"))
    assert image_doc.model_dump_json() == before
    assert ("falls", "blue_cup_01") in events(results["push_edge"].outcome)
    assert not any(e.kind == "falls" for e in results["none"].outcome.events)
    assert not any(e.kind == "falls" for e in results["move_center"].outcome.events)


def test_future_frames_cannot_reach_a_prediction():
    video = material.video_document()
    action = push().model_copy(update={"issued_at_s": 2.0})
    with pytest.raises(FutureLeakage):
        TabletopSimulator().predict(video.states, action, 2.0)
    result = MultimodalBridge().consequences(video, push(), at_time=2.0)
    assert result.context == []  # the push event ends at 3.0 s: unknown at T
    assert result.action.issued_at_s == 2.0


def test_unintegrated_backends_fail_instead_of_substituting(image_doc):
    for backend in (PyBulletSimulator(), VJEPA2ACPredictor()):
        with pytest.raises(BackendUnavailable):
            backend.predict(image_doc.states, push(), 2.0)


# -- ACM mapping ------------------------------------------------------------------------------------

def test_simulated_fall_maps_to_acm_with_its_basis(bridge, image_doc):
    report = bridge.consequences(image_doc, push()).report
    impacted = {(c.about, c.text, c.basis) for c in report.for_target(Target.IMPACTED)}
    assert ("blue_cup_01", "falls", "simulation") in impacted
    assert ("blue_cup_01", "is moved from where it was", "rule") in impacted
    assert not any(c.about == "red_cup_01" for c in report.consequences)  # same class, different object
    assert {u.aspect for u in report.unknowns} == {"damage", "spill"}
    assert report.for_target(Target.SOCIETY) == [] and report.for_target(Target.EARTH) == []
    assert any("not calibrated" in n for n in report.notes)


def test_text_plan_is_the_actors_own_goal(bridge):
    result = bridge.consequences(material.text_document(), material.proposed_actions()["push_edge"])
    own = result.report.own_goals()
    assert own and own[0].status.value == "advanced"


def test_text_and_video_give_compatible_consequences(bridge):
    text = bridge.consequences(material.text_document(), push()).report
    video = bridge.consequences(material.video_document(), push().model_copy(update={"actor": "pusher_01"}), at_time=2.0).report
    falls = lambda r: {c.about for c in r.for_target(Target.IMPACTED) if c.text == "falls"}  # noqa: E731
    assert text.concept == video.concept == "PUSH"
    assert falls(text) == falls(video) == {"blue_cup_01"}
    assert text.actor == "self" and video.actor == "pusher_01"  # different evidence, kept different


# -- evaluation and report -----------------------------------------------------------------------------

def test_prediction_vs_scripted_outcome(tmp_path):
    video = material.video_document()
    outcome = MultimodalBridge().consequences(video, push(), at_time=2.0).outcome
    comparison = compare_outcome(outcome, video.state_at(2.0), video.state_at(4.0))
    m = comparison.metrics
    assert m["fall_events"] == {"tp": 1, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0}
    assert m["position_error_m"]["unit"] == "m" and m["position_error_m"]["n"] == 1
    assert m["abstentions"] == {"count": 1, "consistent_with_observation": 1}

    store = EpisodeStore(tmp_path)
    episode = Episode(id="e1", split="eval", inputs=[video.source], decision_time_s=2.0, horizon_s=2.0,
                      meaning_at_decision=video.available_at(2.0), proposed_action=push(), prediction=outcome,
                      comparison=comparison)
    store.add(episode)
    assert [e.id for e in store.load("eval")] == ["e1"] and store.load("train") == []
    with pytest.raises(ValueError, match="already stored"):
        store.add(episode.model_copy(update={"split": "train"}))


def test_demo_bundle_and_visual_report():
    demo = run_demo()
    assert set(demo["flows"]) == {"text", "image", "video", "sale"}
    html = render_report(demo)
    for label in ("OBSERVED", "ASSUMED", "PREDICTED", "UNKNOWN", "Demo mode", "SIMULATED / PREDICTED", "SCRIPTED OUTCOME"):
        assert label in html
    assert "<script" not in html


def test_world_destination_must_be_calibrated(image_doc):
    move = ProposedAction(id="m", predicate="move", target="blue_cup_01",
                          destination=Point(frame=CoordinateFrame.WORLD, unit="m", x=0.8, y=0.4, calibration_id="other"))
    with pytest.raises(SimulationError, match="calibration"):
        TabletopSimulator().predict(image_doc.states, move, 2.0)
