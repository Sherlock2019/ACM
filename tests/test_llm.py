"""The LLM layer: its output is validated and clamped; it never decides consequences."""

import pytest

from acm import llm


@pytest.fixture
def reply(monkeypatch):
    def set_reply(data):
        monkeypatch.setattr(llm, "chat_json", lambda system, user: (data, 0.5))

    return set_reply


OBJECTS = [{"id": "blue_cup_01", "cls": "cup"}, {"id": "red_cup_01", "cls": "cup"}]


def test_plan_is_validated_and_clamped(reply):
    reply({"target": "blue_cup_01", "intent": "will_fall", "action": {"kind": "push", "dir": 1, "distance_m": 9}})
    plan = llm.physics_plan("push it 9 m", OBJECTS, "red_cup_01")
    assert plan["target"] == "blue_cup_01" and plan["intent"] == "will_fall"
    assert plan["action"]["kind"] == "push" and plan["action"]["distance_m"] == 1.0


def test_plan_rejects_unknown_target_intent_and_action(reply):
    reply({"target": "the moon", "intent": "dance", "action": {"kind": "teleport"}})
    plan = llm.physics_plan("?", OBJECTS, "red_cup_01")
    assert plan == {**plan, "target": "red_cup_01", "intent": "what_happens", "action": None}


def test_answer_keeps_only_well_formed_phrases(reply):
    reply({"answer": "The neighbours get aircraft noise.",
           "phrases": [{"who": "neighbours", "does": "get noise", "why": "null"}, {"what": "orphan"}, "junk"]})
    out = llm.answer("What happens to the neighbours?", {"x": 1})
    assert out["text"] == "The neighbours get aircraft noise."
    assert out["phrases"] == [{"who": "neighbours", "does": "get noise", "what": None, "where": None,
                               "when": None, "with_whom": None, "why": None}]


def test_empty_answer_is_unavailable(reply):
    reply({"phrases": []})
    with pytest.raises(llm.LLMUnavailable):
        llm.answer("?", {})
