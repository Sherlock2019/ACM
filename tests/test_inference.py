"""The inference suite: 'what will happen next to ...?' answered from ACM's own trace."""

import pytest

from acm.inference import SUITE_CONLLU, answers, frames_from_conllu, load_scenarios, run_suite


@pytest.fixture(scope="module")
def suite():
    if not SUITE_CONLLU.is_file():
        pytest.skip("run scripts/make_inference_suite.py (needs MLM's parser)")
    return run_suite(frames_from_conllu())


def by_action(suite, action):
    return next(i for i in suite["items"] if i["action"] == action)


def answer(item, question_start):
    return next(a for a in item["answers"] if a["question"].startswith(question_start))


def test_every_scenario_is_answered(suite):
    assert len(load_scenarios()) >= 50
    assert suite["missing"] == []
    assert suite["stats"]["scenarios"] >= 50
    assert all(item["answers"] for item in suite["items"])
    assert all(len(item["reasoning"]) == 8 for item in suite["items"])


def test_answers_name_each_subject_with_a_reason(suite):
    sale = by_action(suite, "John sold his car to Sarah.")
    assert answer(sale, "What happens next to Sarah?")["answer"] == "Sarah gains his car and loses money."
    assert any("buyer" in why for why in answer(sale, "What happens next to Sarah?")["why"])
    mark = answer(sale, "What happens to Mark's plan")
    assert mark["status"] == "blocked" and "cannot hold" in mark["why"][0]


def test_relations_cover_every_kind(suite):
    statuses = set(suite["stats"]["relations"])
    assert {"blocked", "advanced", "at_risk", "hindered", "unaffected"} <= statuses


def test_layers_name_their_places(suite):
    flight = by_action(suite, "John flew to London.")
    neighbours = answer(flight, "What happens to the neighbours")
    assert "Croydon" in neighbours["question"] and "aircraft noise" in neighbours["answer"]
    assert any("aircraft" in why for why in neighbours["why"])


def test_honesty_cases(suite):
    assert "none of the consequences follow" in by_action(suite, "John did not sell his car to Sarah.")["answers"][0]["answer"]
    assert "describes a state" in by_action(suite, "John is tired.")["answers"][0]["answer"]
    kick = by_action(suite, "John kicked the ball.")
    assert any("no verdict" in a["answer"] for a in kick["answers"])
    limits = answer(by_action(suite, "Mark broke the window."), "What can't ACM tell")
    assert "not 'no impact'" in limits["answer"]


def test_self_view_reads_in_the_first_person(suite):
    item = by_action(suite, "I will pay the bank my debt.")
    me = answer(item, "What happens next to me")
    assert me["answer"] == "If it happens: I no longer owe my debt and lose money."


def test_answers_function_handles_empty_report():
    from acm.schema import ConsequenceReport

    assert answers(ConsequenceReport(action_text="", language="en"))[0]["answer"] == "ACM found no action to evaluate."
