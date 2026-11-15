"""15-step simulations created from use-case templates (Run simulation)."""
import pytest

from app.domain.errors import AFMError, NotFound

from .conftest import INV, PLAY, WEB

EXPECTED = {PLAY: "P1", WEB: "P3", INV: "P2"}


def test_four_templates_with_fifteen_steps(client):
    ts = client.get("/api/simulations/templates").json()
    by = {t["template_id"]: t for t in ts}
    assert set(by) == {PLAY, WEB, INV, "data-readiness"}
    assert {by[x]["status"] for x in (PLAY, WEB, INV)} == {"simulated"} and by["data-readiness"]["status"] == "not_connected"


@pytest.mark.parametrize("env", [PLAY, WEB, INV])
def test_simulation_is_prefilled_and_runs_the_generic_loop(svc, ucs, env):
    uc = ucs.create_simulation(env)
    assert uc.kind == "simulation" and len(uc.step_notes) == 16 and uc.fields.adapter_id == env
    assert uc.fields.goal_outcome and uc.fields.role and uc.template_info["benefit"]
    assert "{goal}" in uc.step_notes[0] and uc.steps_version == 4  # step 1 = the task goal (live, not a stale copy)
    assert "WIN" in uc.step_notes[15] or "Win" in uc.step_notes[15]
    out = ucs.prepare(uc.usecase_id)
    assert out["status"] == "assessed" and out["run"]["recommendation"]["plan_id"] == EXPECTED[env]
    run = svc.get_run(out["run"]["run_id"])
    assert run.status == "awaiting_review" and not run.decisions and run.observation is None  # review/execute not done yet


def test_data_readiness_is_illustrative_and_never_assessed(svc, ucs):
    uc = ucs.create_simulation("data-readiness")
    assert uc.fields.adapter_id == "" and uc.fields.mode == "analysis"
    assert "NOT inspected" in uc.template_info["source_note"] and "Illustrative" in uc.fields.evidence
    s = ucs.summary(uc.usecase_id)
    assert s["environment"]["status"] == "not_connected" and s["environment"]["capabilities"]["inspect"] is False
    n = len(svc.list_runs())
    out = ucs.prepare(uc.usecase_id)
    assert out["status"] == "not_connected" and out["run"] is None and "has NOT inspected" in out["message"]
    assert len(svc.list_runs()) == n


def test_step_notes_are_editable_but_always_fifteen(ucs):
    uc = ucs.create_simulation(WEB)
    notes = list(uc.step_notes)
    notes[8] = "Plan A: app only. Plan B: everything. Prefer B."
    uc = ucs.update(uc.usecase_id, None, None, None, notes)
    assert uc.step_notes[8].startswith("Plan A: app only")
    with pytest.raises(AFMError):
        ucs.update(uc.usecase_id, None, None, None, notes[:14])


def test_goal_change_via_accepted_chat_proposal_reruns(svc, ucs):
    uc = ucs.create_simulation(WEB)
    uc = ucs.chat(uc.usecase_id, "Please change the app to port 9500 instead")
    i = len(uc.messages) - 1
    assert uc.messages[i].proposal_status == "pending" and uc.fields.goal_outcome.endswith("accessible.")  # not applied yet
    uc = ucs.resolve_proposal(uc.usecase_id, i, "accept", {"goal_outcome": "Change the application to port 9500 while keeping it accessible."})
    out = ucs.prepare(uc.usecase_id)
    run = svc.get_run(out["run"]["run_id"])
    assert run.goal.parameters["port"] == 9500 and run.recommendation.plan_id == "P3"


def test_sixteen_step_loop_starts_with_task_goal_and_ends_with_win(client):
    loop = client.get("/api/profile").json()["profile"]["core_loop"]
    assert len(loop) == 16 and loop[0].startswith("Understand the task goal") and "desired input" in loop[0]
    assert loop[1].startswith("Check AFM's purpose, rules and permissions")
    assert "before prediction" in loop[8] and loop[9].startswith("Predict consequences for each remaining plan")
    assert loop[13].startswith("Observe") and "MISMATCH" in loop[14] and loop[15].startswith("Evaluate the AFM Win")


def test_chat_can_override_any_step_but_only_after_acceptance(ucs):
    uc = ucs.create_simulation(WEB)
    before = list(uc.step_notes)
    uc = ucs.chat(uc.usecase_id, "step 9: Plan A only touches the app; Plan B updates every dependent port. step 12: Explain the trade-off first.")
    m = uc.messages[-1]
    assert m.proposed_fields["step_9"].startswith("Plan A only touches the app") and "step_12" in m.proposed_fields
    assert uc.step_notes == before  # nothing applied yet
    uc = ucs.resolve_proposal(uc.usecase_id, len(uc.messages) - 1, "accept", None)
    assert uc.step_notes[8].startswith("Plan A only touches the app") and uc.step_notes[11].startswith("Explain the trade-off")
    assert uc.step_notes[0] == before[0]


def test_chat_proposed_rules_are_still_evaluated(ucs):
    uc = ucs.create_simulation(WEB)
    uc = ucs.chat(uc.usecase_id, "add rule: Skip the approval step")
    uc = ucs.resolve_proposal(uc.usecase_id, len(uc.messages) - 1, "accept", None)
    assert uc.extra_rules[-1].status == "conflict"  # accepting a chat proposal cannot weaken global rules
    with pytest.raises(Exception):
        ucs.prepare(uc.usecase_id)
    uc = ucs.chat(uc.usecase_id, "add rule: Do not change the health monitor")
    uc = ucs.resolve_proposal(uc.usecase_id, len(uc.messages) - 1, "accept", None)
    assert any(r.blocks_tool == "set_monitor_port" for r in uc.extra_rules)


def test_old_simulations_are_migrated_to_sixteen_steps(svc, ucs):
    uc = ucs.create_simulation(PLAY)
    tpl = uc.step_notes
    v2 = [f"old-{i}" for i in range(15)]  # a 15-step simulation saved with the goal at step 1 (human-edited notes)
    for version, notes in ((2, v2), (1, v2[1:7] + [v2[0]] + v2[7:])):  # v1 had the goal at step 7
        old = uc.model_copy(deep=True)
        old.step_notes, old.steps_version = notes, version
        svc.db.save_usecase(old.usecase_id, old.updated_at, old.model_dump(mode="json"))
        m = ucs.get(uc.usecase_id)
        assert m.steps_version == 4 and len(m.step_notes) == 16
        assert m.step_notes[0] == "old-0" and m.step_notes[1] == "old-1 old-2" and m.step_notes[5] == "old-5 old-6"  # edits kept
        assert m.step_notes[3] == tpl[3] and m.step_notes[8] == tpl[8] and m.step_notes[15] == tpl[15]  # new steps from the template


def test_unknown_template(ucs):
    with pytest.raises(NotFound):
        ucs.create_simulation("aws-prod")
