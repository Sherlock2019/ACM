"""Inventory playground: consequence prediction (original spec tests 1–8, through the generic engine)."""
from app.domain.models import Action, Plan
from app.engine import checks
from app.engine.simulator import simulate

from .conftest import DEMO_GOAL, INV, plan_of, store


def _plan(tool="reserve_stock", op="reserve", target="inv-wh1-widget-a", **params):
    return Plan(plan_id="T", goal_id="g", actions=[Action(action_id="t1", tool=tool, operation=op, target_object_id=target, parameters=params)])


def _sim(svc, plan, state=None):
    rt = svc.env(INV)
    s = state or rt.store.snapshot()
    return simulate(rt.adapter, s, plan, rt.store.version, s.fingerprint())


def _cons(a, oid):
    return [c for c in a.simulation.consequences if c.affected_object_id == oid]


def test_1_reserving_30_from_wh1_predicts_70(svc):
    res, _ = _sim(svc, _plan(order_id="order-a", quantity=30))
    assert res.feasible and res.environment_id == INV
    assert res.predicted_objects["inv-wh1-widget-a"]["available"] == 70
    dash = next(c for c in res.consequences if c.affected_object_id == "dashboard-inventory")
    assert dash.predicted_after == {"inv-wh1-widget-a": 70}


def test_2_simulation_leaves_original_unchanged(svc):
    st = store(svc)
    before, v, fp = st.snapshot().to_dict(), st.version, st.fingerprint()
    svc.assess(INV, DEMO_GOAL)
    assert st.snapshot().to_dict() == before and (st.version, st.fingerprint()) == (v, fp)


def test_3_plan1_identifies_order_b_shortage(demo_run):
    b = _cons(plan_of(demo_run, "P1"), "order-b")[0]
    assert b.type == "connected" and b.status == "conditional" and b.effect == "warning"
    assert b.predicted_after == {"eligible_available": 70, "remaining_need": 80, "sufficient": False}
    assert "Potential shortage" in b.description and "only eligible warehouse" in b.description
    assert next(c for c in plan_of(demo_run, "P1").checks if c.check == "goal").status.value == "FAIL"


def test_4_plan2_preserves_order_b_stock(demo_run):
    p2 = plan_of(demo_run, "P2")
    assert p2.simulation.predicted_objects["inv-wh2-widget-a"]["available"] == 20
    assert "inv-wh1-widget-a" not in p2.simulation.predicted_objects
    b = _cons(p2, "order-b")[0]
    assert b.predicted_after["eligible_available"] == 100 and b.predicted_after["sufficient"] is True
    assert next(c for c in p2.checks if c.check == "goal").status.value == "PASS"


def test_5_demo_recommends_plan2(demo_run):
    assert demo_run.status == "awaiting_review" and demo_run.recommendation.plan_id == "P2"
    assert "configured behavior and known data" in demo_run.recommendation.reason
    for pid in ("P1", "P2"):
        assert next(c for c in plan_of(demo_run, pid).checks if c.check == "human_review").status.value == "REVIEW REQUIRED"


def test_5b_fulfil_without_protection_still_prefers_fewer_warnings(svc):
    run = svc.assess(INV, "Fulfill Order A")
    assert run.recommendation.plan_id == "P2"  # R12: P1 meets the goal but leaves a shortage warning


def test_6_over_reservation_rejected(svc):
    res, _ = _sim(svc, _plan(target="inv-wh2-widget-a", order_id="order-a", quantity=60))
    assert not res.feasible and res.errors[0].code in ("insufficient_inventory", "exceeds_order_need")
    res, _ = _sim(svc, _plan(target="inv-wh2-widget-a", order_id="order-b", quantity=80))
    assert res.errors[0].code == "ineligible_inventory"
    rt = svc.env(INV)
    s = rt.store.snapshot()
    s.objects["inv-wh1-widget-a"].state.update(reserved=30, available=70)
    plan = _plan(order_id="order-b", quantity=80)
    res, pred = simulate(rt.adapter, s, plan, 1, s.fingerprint())
    assert res.errors[0].code == "insufficient_inventory"
    a = checks.assess(rt.adapter, plan, rt.adapter.interpret_goal("Fulfill Order B", s), res, pred)
    assert next(c for c in a.checks if c.check == "rules").status.value == "FAIL" and a.approvable is False


def test_7_invalid_quantities_rejected(svc):
    for q in (0, -5):
        assert _sim(svc, _plan(order_id="order-a", quantity=q))[0].errors[0].code == "invalid_quantity"
    assert _sim(svc, _plan(order_id="order-a", quantity="thirty"))[0].errors[0].code == "invalid_parameters"


def test_8_delete_order_prohibited(svc, client):
    res, _ = _sim(svc, _plan(tool="delete_order", op="delete", target="order-b"))
    assert res.errors[0].code == "prohibited_action"
    r = client.post(f"/api/environments/{INV}/simulate", json={"plan": {"actions": [
        {"action_id": "x", "tool": "delete_order", "operation": "delete", "target_object_id": "order-b"}]}})
    assert r.status_code == 422 and "prohibited" in r.json()["error"]["message"]
    assert "order-b" in store(svc).snapshot().objects


def test_missing_object_unknown_action_and_unknown_dependency(svc):
    assert _sim(svc, _plan(target="inv-nope", order_id="order-a", quantity=5))[0].errors[0].code == "missing_object"
    assert _sim(svc, _plan(tool="teleport_stock", op="move"))[0].errors[0].code == "unknown_action"
    res, _ = _sim(svc, _plan(order_id="order-a", quantity=30))
    unk = [c for c in res.consequences if c.status == "unknown"]
    assert unk and unk[0].affected_object_id == "ext-erp-sync" and unk[0].evidence_rule.startswith("CORE-1")
    assert any("not known" in u for u in res.unknowns)
