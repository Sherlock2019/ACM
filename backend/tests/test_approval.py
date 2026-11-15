"""Approval, execution, observation and reset (original spec tests 9–14, 18) on the inventory playground."""
import pytest

from app.domain.errors import Conflict, Forbidden

from .conftest import DEMO_GOAL, INV, approve, plan_of, store


def test_9_cannot_execute_without_approval(svc, demo_run):
    with pytest.raises(Forbidden) as e:
        svc.execute(demo_run.run_id, "P2", None)
    assert e.value.code == "missing_approval"
    with pytest.raises(Forbidden):
        svc.execute(demo_run.run_id, "P2", "ap-forged")
    assert store(svc).snapshot().objects["inv-wh2-widget-a"].state["available"] == 50


def test_9b_rejected_plan_never_executes(svc, demo_run):
    a = plan_of(demo_run, "P1")
    d = svc.decide(demo_run.run_id, "P1", "reject", a.plan_hash, demo_run.environment_version)
    assert d.status == "rejected"
    with pytest.raises(Forbidden):
        svc.execute(demo_run.run_id, "P1", d.approval_id)
    with pytest.raises(Conflict):  # R28: no re-approval in the same run
        svc.decide(demo_run.run_id, "P1", "approve", a.plan_hash, demo_run.environment_version)
    assert store(svc).snapshot().objects["inv-wh1-widget-a"].state["available"] == 100


def test_10_approval_bound_to_exact_plan(svc, demo_run):
    p2 = plan_of(demo_run, "P2")
    with pytest.raises(Conflict) as e:
        svc.decide(demo_run.run_id, "P2", "approve", plan_of(demo_run, "P1").plan_hash, demo_run.environment_version)
    assert e.value.code == "plan_mismatch"
    d = approve(svc, demo_run, "P2")
    with pytest.raises(Forbidden) as e:
        svc.execute(demo_run.run_id, "P1", d.approval_id)
    assert e.value.code == "approval_mismatch"
    tampered = p2.plan.model_dump(mode="json")
    tampered["actions"][0]["parameters"]["quantity"] = 31
    with pytest.raises(Conflict) as e:
        svc.execute(demo_run.run_id, "P2", d.approval_id, plan=tampered)
    assert e.value.code == "plan_mismatch"
    assert store(svc).snapshot().objects["inv-wh2-widget-a"].state["available"] == 50


def test_11_changed_environment_invalidates_approval(svc):
    run1, run2 = svc.assess(INV, DEMO_GOAL), svc.assess(INV, DEMO_GOAL)
    d1, d2 = approve(svc, run1, "P2"), approve(svc, run2, "P2")
    svc.execute(run2.run_id, "P2", d2.approval_id)
    with pytest.raises(Conflict) as e:
        svc.execute(run1.run_id, "P2", d1.approval_id)
    assert e.value.code == "stale_environment"
    r1 = svc.get_run(run1.run_id)
    assert r1.status == "stale" and r1.decisions[0].status == "invalidated"
    with pytest.raises(Forbidden):
        svc.execute(run1.run_id, "P2", d1.approval_id)
    assert store(svc).snapshot().objects["inv-wh2-widget-a"].state["available"] == 20


def test_11b_reset_also_invalidates(svc, demo_run):
    d = approve(svc, demo_run, "P2")
    svc.reset(INV)
    with pytest.raises(Conflict) as e:
        svc.execute(demo_run.run_id, "P2", d.approval_id)
    assert e.value.code == "stale_environment"


def test_12_no_duplicate_execution(svc, demo_run):
    d = approve(svc, demo_run, "P2")
    svc.execute(demo_run.run_id, "P2", d.approval_id)
    with pytest.raises(Conflict) as e:
        svc.execute(demo_run.run_id, "P2", d.approval_id)
    assert e.value.code == "duplicate_execution"
    assert store(svc).snapshot().objects["inv-wh2-widget-a"].state["available"] == 20


def test_13_execution_changes_only_simulated_env_as_predicted(svc, demo_run):
    st = store(svc)
    before, v0 = st.snapshot(), st.version
    other_envs = {e: svc.env(e).store.fingerprint() for e in svc.envs if e != INV}
    d = approve(svc, demo_run, "P2")
    run = svc.execute(demo_run.run_id, "P2", d.approval_id)
    after = st.snapshot()
    assert st.version == v0 + 1
    changed = {oid for oid, o in after.objects.items() if oid not in before.objects or before.objects[oid].state != o.state}
    assert changed == {"inv-wh2-widget-a", "order-a", "dashboard-inventory", "res-1"}
    assert after.objects["inv-wh1-widget-a"].state["available"] == 100
    assert after.objects["order-b"].state == before.objects["order-b"].state
    assert {e: svc.env(e).store.fingerprint() for e in other_envs} == other_envs  # other playgrounds untouched
    assert run.status == "executed" and run.executed_plan_id == "P2"


def test_14_prediction_vs_observation(svc, demo_run):
    d = approve(svc, demo_run, "P2")
    obs = svc.execute(demo_run.run_id, "P2", d.approval_id).observation
    inv = next(i for i in obs.items if i.object_id == "inv-wh2-widget-a" and i.field == "available")
    assert (inv.predicted, inv.observed, inv.result) == (20, 20, "MATCH")
    assert all(i.result in ("MATCH", "NOT VERIFIED") for i in obs.items)
    assert {i.object_id for i in obs.items if i.result == "NOT VERIFIED"} >= {"order-b", "ext-erp-sync"}
    assert "inv-wh1-widget-a" in obs.unchanged_objects


def test_14b_observation_detects_difference(svc, demo_run):
    d = approve(svc, demo_run, "P2")
    st = store(svc)
    real_commit = st.commit

    def faulty_commit(state):
        state.objects["dashboard-inventory"].state["available_by_inventory"]["inv-wh2-widget-a"] = 50
        return real_commit(state)

    st.commit = faulty_commit
    run = svc.execute(demo_run.run_id, "P2", d.approval_id)
    assert next(i for i in run.observation.items if i.object_id == "dashboard-inventory").result == "MISMATCH"


def test_18_reset_restores_demo(svc, demo_run):
    d = approve(svc, demo_run, "P2")
    svc.execute(demo_run.run_id, "P2", d.approval_id)
    st = store(svc)
    v = st.version
    svc.reset(INV)
    assert st.fingerprint() == svc.env(INV).adapter.initial_state().fingerprint() and st.version == v + 1
    s = st.snapshot()
    assert s.objects["inv-wh2-widget-a"].state["available"] == 50 and "res-1" not in s.objects
    assert svc.list_runs()
