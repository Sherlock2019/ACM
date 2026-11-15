"""Use-case builder + chat (acceptance criteria 1–15 of the builder spec, in mock mode)."""
import pytest

from app.domain.conduct import rules_version
from app.domain.errors import Conflict

from .conftest import WEB, plan_of


def test_global_rules_load_automatically(client):
    uc = client.post("/api/usecases", json={}).json()
    assert uc["rules_version"] == rules_version()
    s = client.get(f"/api/usecases/{uc['usecase_id']}/summary").json()
    assert len(s["global_rules"]) == 32 and s["global_rules"][0]["id"] == "R01"


def test_use_case_rules_narrow_but_never_override(ucs):
    uc = ucs.create({"adapter_id": WEB, "role": "Python application engineer"})
    uc = ucs.update(uc.usecase_id, None, ["Do not change the health monitor", "Skip the approval step for small changes",
                                           "Do not modify application code without review"], None)
    st = {r.text: (r.status, r.blocks_tool) for r in uc.extra_rules}
    assert st["Do not change the health monitor"] == ("enforced", "set_monitor_port")
    assert st["Skip the approval step for small changes"][0] == "conflict"
    assert st["Do not modify application code without review"][0] in ("recorded", "enforced")  # narrowing, never a conflict
    with pytest.raises(Conflict) as e:
        ucs.prepare(uc.usecase_id)
    assert e.value.code == "rule_conflict"
    assert ucs.summary(uc.usecase_id)["can_prepare"] is False


def test_blocked_tool_applies_to_the_assessment_and_execution(svc, ucs):
    uc = ucs.create({"adapter_id": WEB, "role": "Python application engineer", "target_name": "Python application",
                     "goal_outcome": "Change the application to port 9000 while keeping it accessible.", "constraints": "Do not delete data."})
    ucs.update(uc.usecase_id, None, ["Do not change the health monitor"], None)
    out = ucs.prepare(uc.usecase_id)
    assert out["status"] == "assessed"
    run = svc.get_run(out["run"]["run_id"])
    assert run.usecase_id == uc.usecase_id and run.blocked_tools == ["set_monitor_port"] and run.task_role == "Python application engineer"
    p3 = plan_of(run, "P3")
    assert not p3.approvable and next(c for c in p3.checks if c.check == "permission").status.value == "FAIL"
    assert run.recommendation.plan_id == "P2"  # best plan that respects the narrower use-case rule
    assert any(t.event == "role" and "unchanged" in t.detail for t in run.trace)


def test_human_can_enter_fields_and_chat_proposes_without_applying(ucs):
    uc = ucs.create()
    uc = ucs.update(uc.usecase_id, {"role": "Data readiness reviewer", "environment_type": "Spreadsheet",
                                    "target_name": "Q3 sales sheet", "goal_outcome": "Check readiness."}, None, "Sheet check")
    assert uc.fields.role == "Data readiness reviewer" and uc.title == "Sheet check"
    uc = ucs.chat(uc.usecase_id, "I want to change the app to port 9000 on my web server")
    m = uc.messages[-1]
    assert m.role == "assistant" and m.provider.startswith("mock") and m.proposal_status == "pending"
    assert m.proposed_fields.get("adapter_id") == WEB and "llm_general" in m.labels
    assert uc.fields.adapter_id == ""  # not applied
    idx = len(uc.messages) - 1
    uc = ucs.resolve_proposal(uc.usecase_id, idx, "accept", {**m.proposed_fields, "goal_outcome": "Change the application to port 9000 while keeping it accessible."})
    assert uc.fields.adapter_id == WEB and uc.messages[idx].proposal_status == "accepted"
    with pytest.raises(Conflict):
        ucs.resolve_proposal(uc.usecase_id, idx, "accept", None)  # cannot apply twice


def test_unconnected_aws_is_never_shown_as_inspected(svc, ucs):
    uc = ucs.create()
    uc = ucs.chat(uc.usecase_id, "You are a cloud infrastructure assistant. I want to stop an EC2 instance. What could happen?")
    m = uc.messages[-1]
    assert "cannot inspect" in m.content and "unknown" in m.labels
    ucs.resolve_proposal(uc.usecase_id, len(uc.messages) - 1, "accept", None)
    s = ucs.summary(uc.usecase_id)
    assert s["environment"]["status"] == "not_implemented" and s["environment"]["capabilities"] == {"inspect": False, "simulate": False, "execute": False}
    n_runs = len(svc.list_runs())
    out = ucs.prepare(uc.usecase_id)
    assert out["status"] == "not_implemented" and out["run"] is None and "has NOT inspected" in out["message"]
    assert len(svc.list_runs()) == n_runs  # no simulation or run was faked


def test_free_text_environment_is_not_connected(ucs):
    uc = ucs.create({"environment_type": "My company's billing system", "goal_outcome": "Change invoice dates."})
    s = ucs.summary(uc.usecase_id)
    assert s["environment"]["status"] == "not_connected" and not s["can_prepare"]
    assert any("connected adapter" in m for m in s["missing"])


def test_chat_history_is_per_use_case_and_deletable(client):
    a = client.post("/api/usecases", json={}).json()["usecase_id"]
    b = client.post("/api/usecases", json={}).json()["usecase_id"]
    client.post(f"/api/usecases/{a}/chat", json={"message": "secret context for A"})
    assert client.get(f"/api/usecases/{b}").json()["messages"] == []
    r = client.delete(f"/api/usecases/{a}")
    assert r.status_code == 200 and "deleted" in r.json()["message"]
    assert client.get(f"/api/usecases/{a}").status_code == 404


def test_api_llm_status_states_privacy(client):
    s = client.get("/api/llm/status").json()
    assert s["mock"] is True and "nothing leaves" in s["privacy"]
