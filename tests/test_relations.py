"""How the action bears on other actors' goals and actions, and on the actor's own goal."""

from acm.schema import RelationStatus

GOAL = "Mark wants to buy John's car."
SALE = "John will sell his car to Sarah in Paris tomorrow to pay his debt."


def relation_of(report, owner_label):
    matches = [r for r in report.relations if r.intention.owner_label == owner_label]
    assert len(matches) == 1, [r.intention.text for r in report.relations]
    return matches[0]


def test_selling_to_someone_else_blocks_the_rival_buyer(predict):
    mark = relation_of(predict(GOAL, SALE), "Mark")
    assert mark.intention.kind == "goal"
    assert mark.status == RelationStatus.BLOCKED
    assert "Sarah has his car" in mark.reason


def test_unknown_buyer_puts_the_goal_at_risk(predict):
    mark = relation_of(predict(GOAL, "John sold his car."), "Mark")
    assert mark.status == RelationStatus.AT_RISK


def test_negated_sale_leaves_the_goal_alone(predict):
    mark = relation_of(predict(GOAL, "John did not sell his car to Sarah."), "Mark")
    assert mark.status == RelationStatus.UNAFFECTED


def test_receiving_what_you_need_advances_the_goal(predict):
    sarah = relation_of(predict("Sarah needs a car.", "John sold his car to Sarah."), "Sarah")
    assert sarah.status == RelationStatus.ADVANCED


def test_own_purpose_is_enabled_by_the_money(predict):
    report = predict(SALE)
    [goal] = report.own_goals()
    assert goal.intention.text == "pay his debt"
    assert goal.status == RelationStatus.ENABLED
    assert goal.via is not None and goal.via.args == ["john", "money"]


def test_winning_blocks_a_rival_who_hoped_to_win(predict):
    mark = relation_of(predict("Mark hopes to win the race.", "Sarah won the race."), "Mark")
    assert mark.status == RelationStatus.BLOCKED


def test_stealing_undoes_another_actors_purchase(predict):
    mark = relation_of(predict("Mark bought a car.", "John stole the car."), "Mark")
    assert mark.intention.kind == "action"
    assert mark.status == RelationStatus.BLOCKED


def test_unknown_verb_gives_no_verdict(predict):
    mark = relation_of(predict(GOAL, "John kicked the ball."), "Mark")
    assert mark.status == RelationStatus.NO_EVIDENCE


def test_french_goal_and_action_reach_the_same_relation(predict):
    report = predict(
        "Marc veut acheter la voiture de John.", "John vendra sa voiture demain.", language="fr"
    )
    assert report.concept == "SALE"
    assert relation_of(report, "Marc").status == RelationStatus.AT_RISK
