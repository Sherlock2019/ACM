"""The environment layers: local, neighbour, connected, city, country, society, earth."""

import pytest

from acm.engine import ConsequenceEngine
from acm.packs import ConsequencePacks
from acm.render import to_text
from acm.schema import Target

SALE = "John will sell his car to Sarah in Paris tomorrow to pay his debt."


def aspects(report, target):
    return [(c.about, c.direction) for c in report.for_target(target)]


def test_paris_resolves_to_its_neighbours_city_and_country(predict):
    report = predict(SALE)
    assert report.scopes["city"] == ["Paris"]
    assert report.scopes["country"] == ["France"]
    assert "Saint-Denis" in report.scopes["neighbour"]
    assert "Île-de-France region" in report.scopes["connected"]


def test_sale_reaches_connected_businesses_and_the_country(predict):
    report = predict(SALE)
    assert ("registration", "0") in aspects(report, Target.CONNECTED)
    assert ("national economy", "0") in aspects(report, Target.COUNTRY)
    assert report.for_target(Target.CITY) == []  # no rule: reported as no known impact


def test_flight_is_heard_next_door_and_counted_nationally(predict):
    report = predict("John flew to London.")
    assert report.scopes["country"] == ["United Kingdom"]
    assert ("noise", "-") in aspects(report, Target.NEIGHBOUR)
    assert ("emissions inventory", "-") in aspects(report, Target.COUNTRY)


def test_train_helps_the_city(predict):
    assert ("traffic", "+") in aspects(predict("John traveled to Paris by train."), Target.CITY)


def test_production_is_connected_to_its_enterprise(predict):
    report = predict("The engineer deleted the database in production.")
    assert "the enterprise that runs it" in report.scopes["connected"]
    assert report.scopes["city"] == []  # a system has no city of its own
    assert ("dependent systems", "-") in aspects(report, Target.CONNECTED)
    assert "CITY  not known" in to_text(report)


def test_rules_fire_without_a_place_and_say_so(predict):
    report = predict("The company destroyed the forest.")
    assert report.places == []
    assert ("landscape", "-") in aspects(report, Target.ENVIRONMENT)
    assert ("protection", "-") in aspects(report, Target.NEIGHBOUR)
    assert "NEIGHBOUR ENVIRONMENT  no place stated" in to_text(report)


def test_place_missing_from_gazetteer_is_unknown_not_guessed(frame_for):
    packs = ConsequencePacks()
    packs._place_index.pop("paris")
    report = ConsequenceEngine(packs).predict([frame_for(SALE)], language="en")
    assert report.scopes["city"] == [] and report.scopes["country"] == []
    assert any("'Paris' is not in the place gazetteer" in note for note in report.notes)


def test_negated_action_changes_no_layer(predict):
    report = predict("John did not sell his car to Sarah.")
    assert "COUNTRY  no place stated\n  nothing changes" in to_text(report)


def test_graph_links_place_to_its_layers(predict):
    report = predict(SALE)
    nodes = {n["id"]: n for n in report.graph["nodes"]}
    edges = {(e["source"], e["relation"], e["target"]) for e in report.graph["edges"]}
    assert ("e:paris", "in_country", "scope:country") in edges
    assert ("e:paris", "next_to", "scope:neighbour") in edges
    assert nodes["scope:country"]["label"] == "country: France"
    assert ("impact:country:national economy", "within", "scope:country") in edges


def test_gazetteer_and_scopes_validate(tmp_path):
    universal = tmp_path / "universal"
    universal.mkdir()
    (universal / "places.yaml").write_text("places:\n  lyon: {kind: city, country: atlantis}\n")
    with pytest.raises(ValueError, match="not a country"):
        ConsequencePacks(tmp_path)
    (universal / "places.yaml").write_text("")
    (universal / "impacts.yaml").write_text(
        "rules:\n  - impact: {scope: galaxy, aspect: x, effect: y}\n"
    )
    with pytest.raises(ValueError, match="unknown scope"):
        ConsequencePacks(tmp_path)
