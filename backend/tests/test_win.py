"""16-step workflow + step-16 AFM Win evaluation (prediction accuracy · task goal · rule compliance)."""
import pytest

from app.domain.errors import Conflict, Forbidden

from .conftest import DEMO_GOAL, INV, PLAY, PLAY_GOAL, WEB, WEB_GOAL, plan_of, store

WEB_GOAL_SHORT = "Change the application to port 9000 while keeping it accessible. Do not delete data."


def run_and_execute(svc, env, goal, plan_id, agree=True, **kw):
    run = svc.assess(env, goal, **kw)
    a = plan_of(run, plan_id)
    d = svc.decide(run.run_id, plan_id, "approve", a.plan_hash, run.environment_version, criteria_agreed=agree)
    return svc.execute(run.run_id, plan_id, d.approval_id)


def cond(run, name):
    return next(c for c in run.win.conditions if c.condition == name)


def test_1_task_goal_first_and_rules_active_from_the_start(svc):
    run = svc.assess(WEB, WEB_GOAL)
    events = [t.event for t in run.trace]
    assert events[0] == "goal" and events[1] == "rules" and events.index("rules") < events.index("inspect")
    assert run.rules_version.startswith("conduct-") and run.policy_version.startswith("policy-")


def test_2_consequences_predicted_separately_for_each_permitted_plan(svc):
    run = svc.assess(WEB, WEB_GOAL)
    for a in run.assessments:
        assert a.simulation.plan_id == a.plan.plan_id and a.simulation.consequences and not a.rejected_before_prediction
    p1, p3 = plan_of(run, "P1"), plan_of(run, "P3")
    assert p1.simulation.consequences != p3.simulation.consequences


def test_3_prohibited_plans_rejected_before_prediction_and_never_executed(svc):
    run = svc.assess(WEB, WEB_GOAL, blocked_tools=["set_monitor_port"])
    p3 = plan_of(run, "P3")
    assert p3.rejected_before_prediction and not p3.simulation.consequences and not p3.approvable
    assert p3.simulation.errors[0].code == "rejected_before_prediction"
    with pytest.raises(Forbidden):
        svc.decide(run.run_id, "P3", "approve", p3.plan_hash, run.environment_version)
    assert store(svc, WEB).snapshot().objects["health-monitor"].state["target_port"] == 8000


def test_4_and_5_simulation_isolated_and_approval_required(svc):
    st = store(svc, PLAY)
    before = st.snapshot().to_dict()
    run = svc.assess(PLAY, PLAY_GOAL)
    assert st.snapshot().to_dict() == before
    with pytest.raises(Forbidden):
        svc.execute(run.run_id, "P1", None)
    assert run.win is None and run.execution_status == "not_attempted"


def test_6_policy_change_invalidates_approval(svc):
    run = svc.assess(WEB, WEB_GOAL)
    a = plan_of(run, "P3")
    d = svc.decide(run.run_id, "P3", "approve", a.plan_hash, run.environment_version, criteria_agreed=True)
    rt = svc.env(WEB)
    rt.adapter._scenario["rules"] = rt.adapter._scenario["rules"] + [{"id": "W6", "text": "Freeze all port changes.", "enforcement": "enforced", "how": "admin"}]
    with pytest.raises(Conflict) as e:
        svc.execute(run.run_id, "P3", d.approval_id)
    assert e.value.code == "policy_changed"
    r = svc.get_run(run.run_id)
    assert r.execution_status == "failed" and r.decisions[0].status == "invalidated" and r.win is None


@pytest.mark.parametrize("env,goal,plan", [(PLAY, PLAY_GOAL, "P1"), (WEB, WEB_GOAL, "P3"), (INV, DEMO_GOAL, "P2")])
def test_7_and_16_match_plus_goal_plus_rules_is_a_win_in_every_use_case(svc, env, goal, plan):
    run = run_and_execute(svc, env, goal, plan)
    assert [c.status for c in run.win.conditions] == ["PASS", "PASS", "PASS"] and run.win.overall == "WIN"
    assert run.execution_status == "executed"


def test_8_prediction_mismatch_is_not_a_win(svc):
    run = svc.assess(INV, DEMO_GOAL)
    a = plan_of(run, "P2")
    d = svc.decide(run.run_id, "P2", "approve", a.plan_hash, run.environment_version, criteria_agreed=True)
    st = store(svc, INV)
    real = st.commit

    def faulty(state):  # the world does not behave as predicted: the dashboard is not refreshed
        state.objects["dashboard-inventory"].state["available_by_inventory"]["inv-wh2-widget-a"] = 50
        return real(state)

    st.commit = faulty
    done = svc.execute(run.run_id, "P2", d.approval_id)
    assert cond(done, "prediction_accuracy").status == "FAIL"
    assert cond(done, "task_goal").status == "PASS" and cond(done, "rule_compliance").status == "PASS"
    assert done.win.overall == "NOT A WIN"


def test_9_and_14_correct_prediction_of_a_bad_outcome_passes_accuracy_but_fails_goal(svc):
    run = run_and_execute(svc, WEB, WEB_GOAL, "P1")  # change only the app port: AFM predicted users would lose access
    users = next(i for i in run.observation.items if i.object_id == "users" and i.field == "can_reach_app")
    assert (users.predicted, users.observed, users.result) == (False, False, "MATCH")
    assert cond(run, "prediction_accuracy").status == "PASS" and cond(run, "task_goal").status == "FAIL"
    assert run.win.overall == "NOT A WIN"


def test_10_rule_violation_is_not_a_win_and_cannot_be_overridden(svc):
    run = run_and_execute(svc, PLAY, PLAY_GOAL, "P1")
    assert run.win.overall == "WIN"
    run = svc.verify(run.run_id, "rule", "R04", "FAIL", "Reviewer found an unnecessary disruption.", "auditor")
    assert cond(run, "rule_compliance").status == "FAIL" and run.win.overall == "NOT A WIN"
    run = svc.verify(run.run_id, "rule", "R04", "PASS", "Second opinion.", "someone else")
    assert run.win.overall == "NOT A WIN"  # a recorded FAIL stays visible


def test_11_unverified_criteria_prevent_a_win(svc):
    run = run_and_execute(svc, WEB, WEB_GOAL, "P3", agree=False)  # human never agreed the success criteria
    assert cond(run, "task_goal").status == "NOT VERIFIED" and run.win.overall == "NOT VERIFIED"
    run = run_and_execute(svc, PLAY, PLAY_GOAL, "P1", human_criteria=["The class understands the propagation"])
    assert cond(run, "task_goal").status == "NOT VERIFIED" and run.win.overall == "NOT VERIFIED"
    run = svc.verify(run.run_id, "criterion", "h1", "PASS", "Students explained B and C correctly.", "teacher")
    assert run.win.overall == "WIN"


def test_12_known_failure_beats_unverified(svc):
    run = svc.assess(INV, DEMO_GOAL)
    a = plan_of(run, "P2")
    d = svc.decide(run.run_id, "P2", "approve", a.plan_hash, run.environment_version, criteria_agreed=False)
    st = store(svc, INV)
    real = st.commit
    st.commit = lambda s: (s.objects["dashboard-inventory"].state["available_by_inventory"].update({"inv-wh2-widget-a": 1}), real(s))[1]
    done = svc.execute(run.run_id, "P2", d.approval_id)
    assert cond(done, "prediction_accuracy").status == "FAIL" and cond(done, "task_goal").status == "NOT VERIFIED"
    assert done.win.overall == "NOT A WIN" and "Still not verified: task goal" in done.win.explanation


def test_13_rejected_or_unexecuted_plans_get_no_observation_and_no_win(svc):
    run = svc.assess(INV, DEMO_GOAL)
    for pid in ("P1", "P2"):
        svc.decide(run.run_id, pid, "reject", plan_of(run, pid).plan_hash, run.environment_version)
    r = svc.get_run(run.run_id)
    assert r.execution_status == "rejected" and r.observation is None and r.win is None
    with pytest.raises(Conflict) as e:
        svc.verify(run.run_id, "rule", "R04", "PASS", "x", "y")
    assert e.value.code == "not_executed"


def test_15_simulated_results_are_labelled(svc):
    run = run_and_execute(svc, WEB, WEB_GOAL_SHORT, "P3")
    assert run.observation.simulated and run.observation.source == "simulation" and "after execution" in run.observation.method
    assert run.win.simulated and "simulation" in run.win.explanation


def test_api_task_goal_name_and_legacy_goal_text(client):
    new = client.post("/api/assessments", json={"environment_id": PLAY, "task_goal": PLAY_GOAL, "desired_output": "C shows 20",
                                                 "success_criteria": ["C shows 20"]}).json()
    old = client.post("/api/assessments", json={"environment_id": PLAY, "goal_text": PLAY_GOAL}).json()
    assert new["goal"]["supported"] and old["goal"]["supported"] and new["goal"]["desired_output"] == "C shows 20"
    assert any(c["source"] == "human" and c["kind"] == "manual" for c in new["goal"]["success_criteria"])
    assert all(c["source"] == "adapter_proposed" for c in old["goal"]["success_criteria"])
