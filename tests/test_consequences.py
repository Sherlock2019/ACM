"""What an action changes, and where each change is reported."""

from cam.schema import SELF, Target

SALE = "John will sell his car to Sarah in Paris tomorrow to pay his debt."


def texts(report, target, about=None):
    return [
        c.text for c in report.for_target(target) if about is None or c.about_label == about
    ]


def test_sale_changes_actor_and_buyer(predict):
    report = predict(SALE)
    assert report.concept == "SALE"
    assert report.actor_label == "John"
    assert texts(report, Target.ACTOR) == ["loses his car", "gains money"]
    assert texts(report, Target.IMPACTED, "Sarah") == ["gains his car", "loses money"]


def test_where_is_the_environment(predict):
    report = predict(SALE)
    assert report.places == ["Paris"]
    assert texts(report, Target.ENVIRONMENT) == ["'sell' takes place here"]


def test_future_action_is_less_certain_than_past(predict):
    future = predict(SALE)
    past = predict("John sold his car to Sarah.")
    assert past.certainty == 1.0
    assert future.certainty < past.certainty


def test_condition_lowers_certainty_and_is_reported(predict):
    plain = predict("John sold his car to Sarah.")
    conditional = predict("If the bank refuses, John will sell his car to Sarah.")
    assert conditional.condition == "bank refuses"
    assert conditional.certainty < plain.certainty


def test_negated_action_changes_nothing(predict):
    report = predict("John did not sell his car to Sarah.")
    assert not report.realized
    assert report.consequences == []


def test_object_destroyed_somewhere_changes_that_place(predict):
    report = predict("The engineer deleted the database in production.")
    assert texts(report, Target.IMPACTED, "database") == ["no longer exists"]
    assert "database no longer exists" in texts(report, Target.ENVIRONMENT, "production")


def test_movement_changes_where_the_actor_is(predict):
    report = predict("John flew to London.")
    assert texts(report, Target.ACTOR) == ["is now in London"]
    assert "John arrives" in texts(report, Target.ENVIRONMENT, "London")


def test_pronouns_resolve_to_earlier_entities(predict):
    report = predict("John owns a car.", "He sold it to Sarah.")
    assert report.actor_label == "John"
    assert texts(report, Target.IMPACTED, "Sarah") == ["gains car", "loses money"]


def test_first_person_is_the_model_itself(predict):
    report = predict("I will give my car to Sarah.")
    assert report.self_view
    assert report.actor == SELF
    assert texts(report, Target.ACTOR) == ["loses my car"]
    assert texts(report, Target.IMPACTED, "Sarah") == ["gains my car"]


def test_unknown_verb_is_generic_and_says_so(predict):
    report = predict("John kicked the ball.")
    assert report.concept is None
    assert report.consequences and not any(c.informative for c in report.consequences)
    assert any("no concept for 'kick'" in note for note in report.notes)


def test_state_predicate_changes_nothing(predict):
    report = predict("John is tired.")
    assert report.consequences == []
    assert any("describes a state" in note for note in report.notes)
