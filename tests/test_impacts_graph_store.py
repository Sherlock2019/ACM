"""Society and earth impacts, the vector graph, the store, and rendering."""

import pytest

from acm.graph import cosine
from acm.packs import ConsequencePacks
from acm.render import NO_IMPACT, to_flowchart, to_mindmap, to_text
from acm.schema import Target
from acm.store import GraphVectorStore

SALE = "John will sell his car to Sarah in Paris tomorrow to pay his debt."


def aspects(report, target):
    return [(c.about, c.direction) for c in report.for_target(target)]


def test_flying_emits_and_the_train_does_not(predict):
    assert ("emissions", "-") in aspects(predict("John flew to London."), Target.EARTH)
    assert ("emissions", "+") in aspects(predict("John traveled to Paris by train."), Target.EARTH)


def test_destroying_a_forest_harms_biodiversity(predict):
    assert ("biodiversity", "-") in aspects(predict("The company destroyed the forest."), Target.EARTH)


def test_sale_touches_the_economy(predict):
    assert ("economy", "0") in aspects(predict(SALE), Target.SOCIETY)


def test_no_rule_means_no_evidence_not_no_impact(predict):
    report = predict("John kicked the ball.")
    assert report.for_target(Target.EARTH) == []
    assert NO_IMPACT in to_text(report)


def test_packs_validate(tmp_path):
    # Loading the shipped packs runs the validator; a broken concept must fail loudly.
    ConsequencePacks()
    universal = tmp_path / "universal"
    universal.mkdir()
    (universal / "states.yaml").write_text("states:\n  has: {args: [owner, thing]}\n")
    (universal / "concepts.yaml").write_text(
        "concepts:\n  X:\n    roles: {a: [AGENT]}\n    effects: [{state: nope, args: [a]}]\n"
    )
    with pytest.raises(ValueError, match="unknown state"):
        ConsequencePacks(tmp_path)


def test_graph_links_action_entities_states_and_intentions(predict):
    report = predict("Mark wants to buy John's car.", SALE)
    nodes = {n["id"]: n for n in report.graph["nodes"]}
    edges = {(e["source"], e["relation"], e["target"]) for e in report.graph["edges"]}
    assert ("action", "AGENT", "e:john") in edges
    assert ("e:mark", "wants", "i0") in edges
    assert ("action", "blocked", "i0") in edges
    assert {n["kind"] for n in nodes.values()} >= {"action", "entity", "place", "state", "impact", "scope", "intention"}
    dims = {len(n["vector"]) for n in nodes.values()}
    assert len(dims) == 1


def test_similar_structure_gives_similar_vectors(predict):
    def action_vector(report):
        return next(n["vector"] for n in report.graph["nodes"] if n["id"] == "action")

    sale_a = action_vector(predict("John sold his car to Sarah."))
    sale_b = action_vector(predict("He sold it to Sarah."))
    flight = action_vector(predict("John flew to London."))
    assert cosine(sale_a, sale_b) > cosine(sale_a, flight)


def test_store_finds_the_closest_action(predict):
    store = GraphVectorStore()
    store.add(predict("John flew to London."))
    store.add(predict("The company destroyed the forest."))
    store.add(predict("John sold his car to Sarah."))
    hits = store.similar_actions(predict("He sold it to Sarah."), k=1)
    assert hits[0]["text"] == "John sold his car to Sarah."
    assert any("Sarah" in row["label"] or "sarah" in row["label"] for row in store.history("sarah"))
    assert store.stats()["graphs"] == 3


def test_mindmap_has_every_circle(predict):
    mindmap = to_mindmap(predict("Mark wants to buy John's car.", SALE))
    for heading in (
        "Actor: John",
        "Impacted",
        "Other actors",
        "Local environment: Paris",
        "Neighbour environment: Boulogne-Billancourt",
        "Organization: Paris city council",
        "City: Paris",
        "Country: France",
        "Society",
        "Earth",
    ):
        assert heading in mindmap
    assert "BLOCKED" in mindmap
    body = mindmap.splitlines()[2:]
    assert not any(ch in line for line in body for ch in "()[]{}")


def test_flowchart_renders_every_node(predict):
    report = predict(SALE)
    chart = to_flowchart(report.graph)
    assert chart.startswith("flowchart LR")
    assert chart.count("\n") >= len(report.graph["nodes"])
