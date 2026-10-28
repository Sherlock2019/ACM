"""Ask ARM: questions about an action answered in Phrase DNA, from the engine's report."""

import re

import pytest

from acm.ask import ask, suggestions
from acm.engine import ConsequenceEngine
from acm.inference import SUITE_CONLLU, frames_from_conllu


class FrozenPipeline:
    """Stands in for MLM's parser: frames from the frozen suite parses; questions fail to parse."""

    def __init__(self, frames):
        self.frames = frames

    def analyze(self, text, language=None, detect_style=False):
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        if not all(s in self.frames for s in sentences):
            raise RuntimeError("not in the frozen parses")
        return type("Analysis", (), {"frames": [self.frames[s] for s in sentences], "language": "en", "warnings": []})()


@pytest.fixture(scope="module")
def run():
    if not SUITE_CONLLU.is_file():
        pytest.skip("run scripts/make_inference_suite.py (needs MLM's parser)")
    pipeline = FrozenPipeline(frames_from_conllu())
    engine = ConsequenceEngine(pipeline=pipeline)

    def go(text, question, context=()):
        return ask(text, list(context), question, pipeline, engine=engine)

    return go


SALE = ("John sold his car to Sarah.", ["Mark wants to buy John's car.", "Sarah needs a car."])


def test_subject_question_answers_in_phrase_dna(run):
    out = run(SALE[0], "What happens next to Sarah?", SALE[1])
    assert out["intent"] == "subject"
    assert out["answer"] == "Sarah gains his car and loses money. Sarah's plan moves closer."
    assert out["action"]["who"] == "John" and out["action"]["does"] == "sell"
    assert out["chains"] and all(ch["subject"] == "Sarah" for ch in out["chains"])
    row = out["chains"][0]
    assert row["dna"]["who"] == "Sarah" and row["dna"]["why"] == "because: John sold his car to Sarah"
    assert "rule" in row["dna"]["rule"]
    # the question did not parse (frozen parses only), so ARM matched on its words and says so
    assert out["question"]["parsed"] is False and out["question"]["note"]


def test_other_actors_goal(run):
    out = run(SALE[0], "What happens to Mark?", SALE[1])
    goal = next(ch for ch in out["chains"] if ch["kind"] == "goal")
    assert goal["status"] == "blocked" and goal["ring"] == "other_actors"
    assert "blocked" in out["answer"]


def test_who_is_harmed_filters_by_direction(run):
    out = run(SALE[0], "Who is harmed?", SALE[1])
    assert out["intent"] == "who"
    assert any(ch["kind"] == "goal" and ch["subject"] == "Mark" for ch in out["chains"])
    assert not any(ch["kind"] == "goal" and ch["status"] == "advanced" for ch in out["chains"])


def test_layer_question_reaches_the_ring(run):
    out = run("John flew to London.", "What happens to the neighbours?")
    assert out["chains"] and all(ch["ring"] == "neighbour" for ch in out["chains"])
    assert "aircraft noise" in out["answer"].lower()


def test_why_says_unknown_when_the_sentence_gives_no_reason(run):
    out = run("John flew to London.", "Why?")
    assert out["intent"] == "why" and "UNKNOWN" in out["answer"]
    stated = run("John will sell his car to Sarah in Paris tomorrow to pay his debt.", "Why?",
                 ["Mark wants to buy John's car."])
    assert "pay his debt" in stated["answer"]


def test_what_if_reruns_acm_and_diffs(run):
    out = run(SALE[0], "What if John did not sell his car to Sarah?", SALE[1])
    assert out["intent"] == "what_if"
    cf = out["counterfactual"]
    assert cf["action"]["negated"] is True and cf["removed"]
    assert not any(ch["kind"] in {"status", "impact"} for ch in cf["added"])
    assert "nothing follows" in out["answer"].lower()


def test_unmatched_subject_is_no_evidence(run):
    out = run("John flew to London.", "What happens to the bakery?")
    assert out["chains"] == [] and "no evidence" in out["answer"]


def test_suggestions(run):
    pipeline = FrozenPipeline(frames_from_conllu())
    report = ConsequenceEngine(pipeline=pipeline).analyze(SALE[0], context=SALE[1])
    qs = suggestions(report)
    assert "What happens next to Sarah?" in qs and "What if John did not sell?" in qs
