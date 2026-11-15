"""Generic AFM: every playground runs through the SAME assessment interface; the core holds no domain logic."""
import json
import re
from pathlib import Path

import pytest

from app.domain import conduct
from app.domain.errors import Forbidden

from .conftest import DEMO_GOAL, INV, PLAY, PLAY_GOAL, WEB, WEB_GOAL, approve, plan_of, store

GOALS = {PLAY: PLAY_GOAL, WEB: WEB_GOAL, INV: DEMO_GOAL}
EXPECTED_REC = {PLAY: "P1", WEB: "P3", INV: "P2"}


@pytest.mark.parametrize("env", [PLAY, WEB, INV])
def test_same_generic_workflow_for_every_environment(svc, env):
    """identity & rules → environment → goal → plans → prediction → checks → review → execute → observe."""
    st = store(svc, env)
    before = st.snapshot().to_dict()
    run = svc.assess(env, GOALS[env])
    assert run.environment_id == env and run.status == "awaiting_review" and run.rules_version.startswith("conduct-")
    assert [t.event for t in run.trace][:3] == ["goal", "rules", "pre-check"]  # step 1 goal, then identity/rules judge it
    assert run.goal.intended_benefits and run.goal.potential_negative_effects  # R30
    assert st.snapshot().to_dict() == before  # simulation never touches the original
    for a in run.assessments:
        assert [c.check for c in a.checks] == ["capability", "permission", "rules", "goal", "human_review"]
        assert a.simulation.environment_id == env
    assert run.recommendation.plan_id == EXPECTED_REC[env]
    with pytest.raises(Forbidden):  # execution requires approval, in every environment
        svc.execute(run.run_id, run.recommendation.plan_id, None)
    d = approve(svc, run, run.recommendation.plan_id)
    done = svc.execute(run.run_id, run.recommendation.plan_id, d.approval_id)
    assert done.status == "executed" and done.observation.items
    assert all(i.result != "MISMATCH" for i in done.observation.items)
    assert len(run.llm_rejections) >= 3  # mock LLM's bad proposals rejected everywhere


def test_playground_predicts_chain_and_executes(svc):
    run = svc.assess(PLAY, PLAY_GOAL)
    p = plan_of(run, "P1")
    by = {c.affected_object_id: c for c in p.simulation.consequences}
    assert by["obj-a"].type == "direct" and (by["obj-a"].before, by["obj-a"].predicted_after) == ({"value": 5}, {"value": 10})
    assert by["obj-b"].type == "connected" and by["obj-b"].before["output"] == 10 and by["obj-b"].predicted_after["output"] == 20
    assert by["obj-c"].type == "connected" and (by["obj-c"].before, by["obj-c"].predicted_after) == ({"shown": 10}, {"shown": 20})
    assert by["obj-b"].evidence_rule.startswith("PLAY-2") and by["obj-c"].evidence_rule.startswith("PLAY-3")
    assert store(svc, PLAY).snapshot().objects["obj-b"].state["output"] == 10  # unchanged until approved
    d = approve(svc, run, "P1")
    obs = svc.execute(run.run_id, "P1", d.approval_id).observation
    got = {(i.object_id, i.field): (i.observed, i.result) for i in obs.items}
    assert got[("obj-a", "value")] == (10, "MATCH") and got[("obj-b", "output")] == (20, "MATCH") and got[("obj-c", "shown")] == (20, "MATCH")


def test_playground_refuses_derived_edits(svc):
    g = svc.interpret(PLAY, "Change Object B's output to 50")
    assert not g.supported and "derived" in g.explanation


def test_webapp_identifies_port_mismatch(svc):
    run = svc.assess(WEB, WEB_GOAL)
    p1, p2, p3 = (plan_of(run, x) for x in ("P1", "P2", "P3"))
    cons = {c.affected_object_id: c for c in p1.simulation.consequences if c.type == "connected"}
    assert "still forwards to port 8000" in cons["web-server"].description and cons["web-server"].effect == "warning"
    assert cons["users"].predicted_after == {"can_reach_app": False} and cons["users"].status == "conditional"
    assert "still checks port 8000" in cons["health-monitor"].description
    assert "no direct change" in cons["database"].description
    assert cons["firewall"].status == "unknown"
    assert next(c for c in p1.checks if c.check == "goal").status.value == "FAIL"
    assert next(c for c in p1.checks if c.check == "rules").status.value == "REVIEW REQUIRED"  # W3 flag
    assert p2.meets_goal_and_rules and p2.warnings == 1  # monitor still on 8000: trade-off
    assert p3.meets_goal_and_rules and p3.warnings == 0
    assert "Trade-off" not in run.recommendation.reason and "P2" in run.recommendation.reason


def test_webapp_port_goal_without_port_asks(svc):
    g = svc.interpret(WEB, "Change the application port")
    assert not g.supported and "Which port" in g.clarification_needed and g.missing_information


def test_webapp_invalid_and_prohibited(svc, client):
    r = client.post(f"/api/environments/{WEB}/simulate", json={"plan": {"actions": [
        {"action_id": "a", "tool": "set_app_port", "operation": "configure", "target_object_id": "python-app", "parameters": {"port": 80}}]}})
    a = r.json()
    assert not a["simulation"]["feasible"] and a["simulation"]["errors"][0]["code"] == "invalid_port" and not a["approvable"]
    r = client.post(f"/api/environments/{WEB}/simulate", json={"plan": {"actions": [
        {"action_id": "a", "tool": "delete_database_records", "operation": "delete", "target_object_id": "database"}]}})
    assert r.status_code == 422 and "prohibited" in r.json()["error"]["message"]


def test_switching_environments_changes_objects_actions_rules(client):
    seen = {}
    for env in (PLAY, WEB, INV):
        d = client.get(f"/api/environments/{env}").json()
        v = client.get(f"/api/environments/{env}/view").json()
        seen[env] = ({o["id"] for o in v["objects"]}, {t["name"] for t in d["tools"]}, {r["id"] for r in d["rules"]})
        assert d["kind"] == "simulated" and d["capabilities"] == {"inspect": True, "simulate": True, "execute": True}
        assert d["limitations"] and d["demo_goals"]
    for i, a in enumerate((PLAY, WEB, INV)):
        for b in (PLAY, WEB, INV)[i + 1:]:
            assert not (seen[a][0] & seen[b][0]) and not (seen[a][1] & seen[b][1]) and not (seen[a][2] & seen[b][2])
    prof = client.get("/api/profile").json()
    assert prof["profile"]["name"] == "AFM — Action–Consequence Foresight Model"
    assert len(prof["conduct"]["rules"]) == 32 and prof["conduct"]["permanent"] is True


def test_cross_environment_goals_are_not_substituted(svc):
    assert not svc.interpret(WEB, "Fulfill Order A").supported
    assert not svc.interpret(INV, "Change the application to port 9000").supported
    assert not svc.interpret(PLAY, "Fulfill Order A").supported


def test_generic_core_has_no_domain_logic():
    core = Path(__file__).resolve().parents[1] / "app" / "engine"
    banned = r"warehouse|inventory|order_id|reserve_stock|listening_port|web-server|obj-a|eligible_available"
    for f in ("simulator.py", "checks.py", "planner.py", "service.py", "environment.py"):
        src = (core / f).read_text(encoding="utf-8")
        assert not re.search(banned, src, re.IGNORECASE), f"domain term found in engine/{f}"
    profile = (Path(__file__).resolve().parents[1] / "app" / "config" / "afm_profile.json").read_text(encoding="utf-8").lower()
    assert "inventory" not in profile and "warehouse" not in profile


def test_conduct_rules_are_permanent_and_tamper_evident(tmp_path, monkeypatch):
    c = conduct.load_conduct()
    assert [r.id for r in c.rules] == [f"R{i:02d}" for i in range(1, 33)]
    assert all(r.enforcement in ("enforced", "partial") and r.how for r in c.rules)
    assert next(r for r in c.rules if r.id == "R02").enforcement == "partial"  # "do not steal" is not claimed as fully enforced
    data = json.loads(conduct.CONDUCT_PATH.read_text(encoding="utf-8"))
    data["rules"][7]["text"] = "Present a plan for review when convenient."  # weaken R08
    fake = tmp_path / "conduct_rules.json"
    fake.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(conduct, "CONDUCT_PATH", fake)
    conduct.load_conduct.cache_clear()
    try:
        with pytest.raises(conduct.ConductIntegrityError):
            conduct.load_conduct()
        data["rules"] = data["rules"][:31]
        fake.write_text(json.dumps(data), encoding="utf-8")
        conduct.load_conduct.cache_clear()
        with pytest.raises(conduct.ConductIntegrityError):
            conduct.load_conduct()
    finally:
        monkeypatch.undo()
        conduct.load_conduct.cache_clear()
        conduct.load_conduct()


def test_future_adapters_are_labelled_not_working(client):
    fut = client.get("/api/environments").json()["future"]
    names = {f["name"] for f in fut}
    assert {"AWS infrastructure", "SAP", "Spreadsheet"} <= names
    assert all(f["status"] in ("not_implemented", "not_connected") for f in fut)
    assert client.get("/api/environments/aws/view").status_code == 404
