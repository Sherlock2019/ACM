"""Real-project flow: connect → inspect → task goal + plan + predictions (saved first) → pre-check →
human review (bound to commit, patch, commands, predictions, policy) → recheck → baseline tests →
apply patch → same tests → compare → three-condition Win.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable

from ..domain.conduct import rules_version
from ..domain.errors import AFMError, NotFound
from ..domain.models import WinCheck, WinCondition, WinEvaluation, now_iso
from ..engine.win import FAIL, NV, PASS, combine
from ..storage.db import Database
from . import inspect as insp
from . import runner, workspace
from .models import (ChatMessage, Check, CommandResult, ComparisonRow, Criterion, Decision, LogEntry, PrecheckItem, Prediction,
                     ProjectTest, Verification)

SOURCE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".c", ".cpp", ".swift", ".sh"}

PROJECT_POLICY = {"timeout_s": runner.TIMEOUT_S, "shells": False, "env": list(runner.KEEP_ENV), "forbidden": sorted(runner.FORBIDDEN_FIRST),
                  "isolation": "workspace copy, reduced environment, not a sandbox"}


def policy_version() -> str:
    raw = json.dumps({"conduct": rules_version(), "project": PROJECT_POLICY}, sort_keys=True)
    return "proj-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def _describe(c: Check, commands: list[list[str]]) -> str:
    cmd = " ".join(commands[c.command]) if c.command < len(commands) else f"command {c.command + 1}"
    return {"command_exit": f"`{cmd}` exits {'with 0' if c.expect == '0' else 'non-zero'}",
            "test_outcome": f"{c.test} {c.expect} (via `{cmd}`)",
            "no_other_changes": f"no other test changes outcome between baseline and after (via `{cmd}`)",
            "manual": "checked by a human"}[c.type]


class ProjectService:
    def __init__(self, db: Database, llm: Callable[[], Any]):
        self.db = db
        self._llm = llm

    # ------------------------------------------------------------------ storage
    def _save(self, p: ProjectTest) -> ProjectTest:
        p.updated_at = now_iso()
        self.db.save_project(p.id, p.updated_at, p.model_dump(mode="json"))
        return p

    def get(self, pid: str) -> ProjectTest:
        d = self.db.get_project(pid)
        if not d:
            raise NotFound(f"Project test {pid} not found.")
        return ProjectTest.model_validate(d)

    def list(self) -> list[dict[str, Any]]:
        out = []
        for d in self.db.list_projects():
            out.append({k: d.get(k) for k in ("id", "name", "source", "origin", "status", "updated_at", "commit")}
                       | {"win": (d.get("win") or {}).get("overall")})
        return out

    @staticmethod
    def _log(p: ProjectTest, step: int, text: str) -> None:
        p.log.append(LogEntry(at=now_iso(), step=step, text=text))

    # ------------------------------------------------------------------ steps 2-7: connect + inspect
    def create(self, source: str, path: str = "", url: str = "", ref: str = "") -> ProjectTest:
        info = workspace.create_from_local(path) if source == "local" else workspace.create_from_github(url, ref)
        inspection = insp.inspect(info["workspace"], info.get("uncommitted", 0))
        now = now_iso()
        p = ProjectTest(id="prj-" + uuid.uuid4().hex[:10], created_at=now, updated_at=now, name=info["name"], source=source,
                        origin=info["origin"], ref=ref, workspace=info["workspace"], workspace_kind=info["workspace_kind"],
                        commit=info["commit"], origin_fingerprint=info["origin_fingerprint"], inspection=inspection)
        how = {"git_clone": "git clone of your folder at its current commit", "folder_copy": "file copy of your folder + local baseline commit",
               "github_clone": "shallow clone from GitHub"}[p.workspace_kind]
        self._log(p, 2, "Rules loaded: 32 permanent rules of conduct + real-project policy (no shells, no push, approved commands only).")
        self._log(p, 3, f"ACFM test workspace created ({how}): {p.workspace} @ {p.commit[:12]}. Nothing installed, no scripts run.")
        self._log(p, 4, f"Read-only inspection: {inspection['file_count']} files, {inspection['test_count']} test file(s), "
                        f"{len(inspection['suggested_commands'])} suggested test command(s) (not run).")
        return self._save(p)

    # ------------------------------------------------------------------ steps 1, 8-11: goal + plan + predictions + pre-check
    def _hash(self, p: ProjectTest) -> str:
        raw = json.dumps({"commit": p.commit, "goal": p.goal, "criteria": [c.model_dump() for c in p.criteria], "patch": p.patch,
                          "commands": p.commands, "predictions": [x.model_dump() for x in p.predictions]}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def save_plan(self, pid: str, data: dict[str, Any]) -> ProjectTest:
        p = self.get(pid)
        if p.status in ("executed", "failed"):
            raise AFMError("conflict", "This test already ran. Start a new project test to try another plan.", 409)
        p.goal = data.get("goal", "").strip()
        p.desired_input = data.get("desired_input", "").strip()
        p.desired_output = data.get("desired_output", "").strip()
        p.patch = data.get("patch", "")
        p.commands = [list(a) for a in data.get("commands", [])]
        p.assumptions = list(data.get("assumptions", []))
        p.unknowns = list(data.get("unknowns", []))
        p.plan_source = data.get("plan_source", "human")
        p.criteria = [Criterion(id=f"C{i + 1}", text=c["text"], check=Check(**c["check"]), source=c.get("source", "human"))
                      for i, c in enumerate(data.get("criteria", []))]
        p.predictions = [Prediction(id=f"P{i + 1}", statement=x["statement"], check=Check(**x["check"]), required=x.get("required", True))
                         for i, x in enumerate(data.get("predictions", []))]
        if not p.goal:
            raise AFMError("invalid_input", "Describe the Task Goal first (step 1).", 400)
        for item in [*p.predictions, *p.criteria]:
            if item.check.type != "manual" and item.check.command >= len(p.commands):
                raise AFMError("invalid_input", f"{item.id} refers to command {item.check.command + 1}, which does not exist.", 400)
            if item.check.type == "test_outcome" and (not item.check.test or item.check.expect not in ("passed", "failed")):
                raise AFMError("invalid_input", f"{item.id}: a test outcome needs a test id and 'passed' or 'failed'.", 400)
            if item.check.type == "command_exit" and item.check.expect not in ("0", "nonzero"):
                raise AFMError("invalid_input", f"{item.id}: a command result must expect '0' or 'nonzero'.", 400)
        new_hash = self._hash(p)
        if p.decision and p.decision.status == "approved" and p.decision.plan_hash != new_hash:
            p.decision.status = "invalidated"
            self._log(p, 12, "The plan changed after approval: the approval was cancelled (R13).")
        p.plan_hash = new_hash
        p.predictions_saved_at = now_iso()
        p.precheck = runner.check_patch(p.workspace, p.patch) + runner.check_commands(p.commands)
        if not p.predictions:
            p.precheck.append(PrecheckItem(name="Testable predictions", status="FAIL", detail="Add at least one prediction to compare with the test results."))
        p.status = "planned" if not (p.decision and p.decision.status == "approved") else p.status
        fails = [i for i in p.precheck if i.status == "FAIL"]
        self._log(p, 1, f"Task Goal: {p.goal[:200]}")
        self._log(p, 10, f"{len(p.predictions)} prediction(s) saved before anything runs (plan {p.plan_hash}).")
        self._log(p, 9, "Pre-check passed." if not fails else f"Pre-check failed: {'; '.join(i.name for i in fails)[:300]}.")
        return self._save(p)

    def draft(self, pid: str, files: list[str], note: str = "", goal: str = "", desired_input: str = "", desired_output: str = "") -> dict[str, Any]:
        """Ask the configured LLM tool for a DRAFT plan. Nothing is saved or applied; the human edits and saves it."""
        p = self.get(pid)
        goal = goal.strip() or p.goal
        if not goal and not note:
            raise AFMError("invalid_input", "Write the Task Goal first, so the LLM knows what to draft.", 400)
        contents = insp.read_files(p.workspace, files)
        ins = p.inspection
        ctx = {"goal": goal or note, "desired_input": desired_input or p.desired_input, "desired_output": desired_output or p.desired_output, "note": note,
               "languages": ins.get("languages"), "tests": ins.get("tests", [])[:40], "suggested_commands": ins.get("suggested_commands"),
               "files": contents}
        llm = self._llm()
        d = llm.draft_project_plan(ctx)
        sent = {"provider": llm.name, "files": [f["path"] for f in contents], "chars": sum(len(f["content"]) for f in contents),
                "also": "Task Goal, desired input/output, languages, test file names and suggested commands."}
        return {"draft": d, "sent": sent}

    def chat(self, pid: str, message: str, files: list[str]) -> ProjectTest:
        """The human describes the change in plain words; the LLM answers with a reply and a DRAFT plan
        (goal, patch, commands, predictions, criteria). The draft is only stored on the message."""
        p = self.get(pid)
        if p.status in ("executed", "failed"):
            raise AFMError("conflict", "This test already ran. Start a new project test to try another change.", 409)
        known = set(p.inspection.get("files", []))
        low = message.lower()
        mentioned = [f for f in known if f.lower() in low or (len(f.rsplit("/", 1)[-1]) > 3 and re.search(rf"\b{re.escape(f.rsplit('/', 1)[-1].lower())}\b", low))]
        # also send the tests that belong to a mentioned file (calc.py → tests/test_calc.py), so test ids are not guessed
        stems = {Path(f).stem.lower() for f in mentioned if not Path(f).name.startswith("test_")}
        related = [t for t in p.inspection.get("tests", []) if t in known and any(s and s in Path(t).stem.lower() for s in stems)]
        chosen = list(dict.fromkeys([*files, *sorted(mentioned), *sorted(related)]))[:12]
        contents = insp.read_files(p.workspace, chosen)
        ins = p.inspection
        history = [{"role": m.role, "content": m.content} for m in p.chat[-10:]]
        ctx = {"goal": p.goal, "desired_input": p.desired_input, "desired_output": p.desired_output, "note": "",
               "languages": ins.get("languages"), "tests": ins.get("tests", [])[:40], "suggested_commands": ins.get("suggested_commands"),
               "files": contents, "history": history, "message": message,
               "current_plan": {"patch": p.patch[:8000], "commands": p.commands, "predictions": [x.statement for x in p.predictions],
                                "criteria": [c.text for c in p.criteria]}}
        llm = self._llm()
        now = now_iso()
        p.chat.append(ChatMessage(role="user", content=message, at=now, files=[f["path"] for f in contents]))
        d = llm.draft_project_plan(ctx)
        p.chat.append(ChatMessage(role="assistant", content=d.get("summary") or "Here is a draft plan.", at=now_iso(), provider=llm.name, draft=d))
        self._log(p, 7, f"Asked {llm.name} in plain words; draft received (proposal only). Files sent: {', '.join(f['path'] for f in contents) or 'none'}.")
        return self._save(p)

    def describe(self, pid: str) -> ProjectTest:
        """Ask the LLM to read the README, config and main source files and list the project's name, goal,
        features and suggested improvements. Labelled LLM-generated; it never changes the plan by itself."""
        p = self.get(pid)
        ins = p.inspection
        files = ins.get("files", [])
        readme = [f for f in files if f.lower().split("/")[-1].startswith("readme")][:1]
        config = [f for f in ins.get("key_files", []) if f in files and not f.lower().startswith("readme")][:4]
        tests = set(ins.get("tests", []))
        source = sorted((f for f in files if f not in tests and Path(f).suffix.lower() in SOURCE_EXT), key=lambda f: (f.count("/"), f))[:10]
        chosen = list(dict.fromkeys([*readme, *config, *source]))[:14]
        contents = insp.read_files(p.workspace, chosen, per_file=6000, total=60000)
        ctx = {"name": p.name, "languages": ins.get("languages"), "top_level": ins.get("top_level"), "tests": ins.get("tests", [])[:40],
               "file_count": ins.get("file_count"), "files": contents}
        llm = self._llm()
        d = llm.describe_project(ctx)
        p.overview = {**d, "provider": llm.name, "files_read": [f["path"] for f in contents], "at": now_iso()}
        self._log(p, 4, f"{llm.name} described the project (LLM-generated) from {len(contents)} file(s): {len(d.get('features', []))} feature(s), "
                        f"{len(d.get('suggestions', []))} suggested change(s).")
        return self._save(p)

    # ------------------------------------------------------------------ step 12: human review
    def decide(self, pid: str, decision: str, reviewer: str, plan_hash: str, criteria_agreed: bool, note: str = "") -> ProjectTest:
        p = self.get(pid)
        if p.status in ("executed", "failed"):
            raise AFMError("conflict", "This test already ran.", 409)
        if plan_hash != p.plan_hash:
            raise AFMError("stale", "The plan changed since you opened it. Review the current plan.", 409)
        if decision == "approve" and any(i.status == "FAIL" for i in p.precheck):
            raise AFMError("precheck_failed", "The pre-check failed, so this plan cannot be approved.", 409)
        p.decision = Decision(status="approved" if decision == "approve" else "rejected", reviewer=reviewer, at=now_iso(),
                              plan_hash=p.plan_hash, policy_version=policy_version(), criteria_agreed=criteria_agreed, note=note)
        p.status = "approved" if decision == "approve" else "rejected"
        self._log(p, 12, f"{reviewer} {'approved' if decision == 'approve' else 'rejected'} plan {p.plan_hash}"
                         + (" and agreed the success criteria." if criteria_agreed and decision == "approve" else "."))
        return self._save(p)

    # ------------------------------------------------------------------ steps 13-16: recheck, run, compare, win
    def execute(self, pid: str) -> ProjectTest:
        p = self.get(pid)
        d = p.decision
        if p.status in ("executed", "failed"):
            raise AFMError("conflict", "This approved plan was already executed once.", 409)
        if not d or d.status != "approved":
            raise AFMError("not_approved", "A human must approve this exact plan first.", 403)
        problems = []
        if d.plan_hash != self._hash(p):
            problems.append("the plan changed after approval")
        if d.policy_version != policy_version():
            problems.append("the rules or real-project policy changed after approval")
        head, clean = workspace.workspace_state(p.workspace)
        if head != p.commit or not clean:
            problems.append("the workspace is no longer at the recorded commit or has changes")
        if p.source == "local" and workspace.fingerprint(Path(p.origin), p.workspace_kind) != p.origin_fingerprint:
            self._log(p, 13, "Note: your original folder changed since the copy was made (by you or another tool). The test still uses the copy.")
        if problems:
            d.status = "invalidated"
            p.status = "planned"
            self._log(p, 13, "Recheck failed, approval cancelled: " + "; ".join(problems) + ".")
            self._save(p)
            raise AFMError("stale", "Recheck failed: " + "; ".join(problems) + ". Review the plan again.", 409)
        self._log(p, 13, f"Recheck passed: commit {p.commit[:12]}, plan {p.plan_hash}, policy {d.policy_version}.")
        d.status = "used"
        p.executed_at = now_iso()
        for argv in p.commands:
            p.results.append(runner.run(p.workspace, argv, "baseline"))
        ok, err = runner.apply_patch(p.workspace, p.patch)
        p.patch_applied = ok
        if not ok:
            p.status = "failed"
            self._log(p, 14, f"Baseline ran; applying the approved patch failed: {err}")
        else:
            for argv in p.commands:
                p.results.append(runner.run(p.workspace, argv, "after"))
            p.status = "executed"
            self._log(p, 14, f"Baseline tests ran, approved patch applied, the same {len(p.commands)} command(s) ran again.")
        self._evaluate(p)
        return self._save(p)

    def verify(self, pid: str, kind: str, ref: str, status: str, evidence: str, reviewer: str) -> ProjectTest:
        p = self.get(pid)
        if p.status not in ("executed", "failed"):
            raise AFMError("conflict", "Human verification is recorded after the test ran.", 409)
        p.verifications.append(Verification(kind=kind, ref=ref, status=status, evidence=evidence, reviewer=reviewer, at=now_iso()))
        self._log(p, 16, f"{reviewer} recorded {status} for {kind} {ref} (user-provided).")
        self._evaluate(p)
        return self._save(p)

    def delete(self, pid: str) -> dict[str, Any]:
        p = self.get(pid)
        removed = workspace.remove(p.workspace)
        self.db.delete_project(pid)
        return {"deleted": pid, "workspace_removed": removed}

    # ------------------------------------------------------------------ evaluation
    def _result(self, p: ProjectTest, phase: str, i: int) -> CommandResult | None:
        rs = [r for r in p.results if r.phase == phase]
        return rs[i] if i < len(rs) else None

    def _measure(self, p: ProjectTest, c: Check, ref: str, kind: str) -> tuple[bool | None, str]:
        """Evaluate a check on the OBSERVED results. None = not verifiable."""
        if c.type == "manual":
            v = next((x for x in reversed(p.verifications) if x.kind == kind and x.ref == ref), None)
            return (None, "awaiting human verification") if not v else (v.status == "PASS", f"user-provided by {v.reviewer}: {v.evidence}")
        after = self._result(p, "after", c.command)
        if after is None:
            return None, "the command did not run after the patch"
        if after.error:
            return None, after.error
        if c.type == "command_exit":
            return (after.exit_code == 0) == (c.expect == "0"), f"exit code {after.exit_code}"
        if c.type == "test_outcome":
            got = after.tests.get(c.test)
            return (None, f"{c.test} was not found in the output") if got is None else (got == c.expect, f"{c.test} {got}")
        base = self._result(p, "baseline", c.command)
        if not base or base.error or not base.tests or not after.tests:
            return None, "individual test results could not be read from both runs"
        named = {x.check.test for x in p.predictions if x.check.type == "test_outcome"}
        changed = [t for t in sorted(set(base.tests) | set(after.tests)) if t not in named and base.tests.get(t) != after.tests.get(t)]
        return (not changed), ("no other test changed" if not changed else f"changed: {', '.join(f'{t} {base.tests.get(t)}→{after.tests.get(t)}' for t in changed[:5])}")

    def _evaluate(self, p: ProjectTest) -> None:
        p.comparison = []
        for x in p.predictions:
            ok, obs = self._measure(p, x.check, x.id, "prediction")
            p.comparison.append(ComparisonRow(prediction_id=x.id, statement=x.statement, expected=_describe(x.check, p.commands), observed=obs,
                                              result="NOT VERIFIED" if ok is None else ("MATCH" if ok else "MISMATCH"), required=x.required))
        req = [r for r in p.comparison if r.required]
        pc = [WinCheck(name=f"{r.prediction_id} · {r.statement[:80]}", status={"MATCH": PASS, "MISMATCH": FAIL}.get(r.result, NV),
                       evidence=f"expected: {r.expected}; observed: {r.observed} ({r.result})", phase="observation") for r in req]
        n = {k: sum(1 for r in req if r.result == k) for k in ("MATCH", "MISMATCH", "NOT VERIFIED")}
        pred = WinCondition(condition="prediction_accuracy", question="Did the required predictions match the observed test results?",
                            status=combine([c.status for c in pc]) if pc else NV, checks=pc,
                            summary=f"{n['MATCH']} matched, {n['MISMATCH']} mismatched, {n['NOT VERIFIED']} not verified.")

        d = p.decision
        gc: list[WinCheck] = []
        if not d or not d.criteria_agreed:
            gc.append(WinCheck(name="Success criteria agreed by the human", status=NV, phase="review",
                               evidence="The success criteria were not explicitly agreed at review."))
        if not p.criteria:
            gc.append(WinCheck(name="Success criteria defined", status=NV, phase="task goal", evidence="No success criteria, so achievement cannot be judged."))
        for c in p.criteria:
            ok, obs = self._measure(p, c.check, c.id, "criterion")
            gc.append(WinCheck(name=f"{c.id} · {c.text[:80]}", status=NV if ok is None else (PASS if ok else FAIL), phase="observation",
                               evidence=f"On the observed results: {obs} (criterion: {c.source.replace('_', ' ')})"))
        goal = WinCondition(condition="task_goal", question="Did the observed results meet the agreed Task Goal?", status=combine([c.status for c in gc]),
                            checks=gc, summary=f"Task Goal: “{p.goal[:200]}”.")

        ran = [r.argv for r in p.results]
        expected_runs = p.commands + (p.commands if p.patch_applied else [])
        rc = [
            WinCheck(name="Human approval before any change (R08, R23)", phase="review", status=PASS if d and d.status == "used" else FAIL,
                     evidence=f"Approved by {d.reviewer} at {d.at}, bound to plan {d.plan_hash}, commit {p.commit[:12]}, policy {d.policy_version}." if d else "No approval."),
            WinCheck(name="Predictions saved before the tests ran", phase="prediction",
                     status=PASS if p.predictions_saved_at and p.predictions_saved_at <= p.executed_at else FAIL,
                     evidence=f"saved {p.predictions_saved_at}, executed {p.executed_at}"),
            WinCheck(name="Only the approved commands ran, without a shell", phase="execution", status=PASS if ran == expected_runs else FAIL,
                     evidence=f"{len(ran)} run(s) of {len(p.commands)} approved command(s) (baseline + after)."),
            WinCheck(name="Patch confined to the workspace and pre-checked", phase="pre-check",
                     status=PASS if all(i.status == "PASS" for i in p.precheck) else FAIL, evidence="git apply --check passed; no path outside the workspace."),
            WinCheck(name="Recheck of plan, commit and policy before running (R13, R24)", phase="execution", status=PASS,
                     evidence="Plan hash, workspace commit/cleanliness and policy version matched at execution."),
            WinCheck(name="No push, pull request or remote change", phase="execution", status=PASS,
                     evidence="ACFM has no code path that pushes, opens pull requests or changes remotes; git push/remote/config commands are refused."),
        ]
        if p.source == "local":
            same = workspace.fingerprint(Path(p.origin), p.workspace_kind) == p.origin_fingerprint
            rc.append(WinCheck(name="Your original folder was not modified", phase="observation", status=PASS if same else NV,
                               evidence="Read-only fingerprint unchanged." if same else
                               "Your folder changed since the copy was made. ACFM only wrote to the workspace, but cannot prove who changed it."))
        rc.append(WinCheck(name="Honest reporting (R06, R18)", phase="reporting", status=PASS,
                           evidence="Unverifiable results stay NOT VERIFIED; human entries are labelled user-provided. Workspace is not a sandbox."))
        for v in p.verifications:
            if v.kind == "rule":
                rc.append(WinCheck(name=f"Human judgment on {v.ref}", phase="human verification", status=v.status, evidence=f"{v.reviewer}: {v.evidence}"))
        rules = WinCondition(condition="rule_compliance", question="Were the applicable rules and permissions respected?",
                             status=combine([c.status for c in rc]), checks=rc,
                             summary="Concrete checks of the real-project policy. Broad principles are not proven by the absence of a detected violation.")
        conds = [pred, goal, rules]
        sts = [c.status for c in conds]
        overall = "NOT A WIN" if FAIL in sts else ("NOT VERIFIED" if NV in sts else "WIN")
        names = {"prediction_accuracy": "prediction accuracy", "task_goal": "task goal", "rule_compliance": "rule compliance"}
        expl = {"WIN": "All three conditions passed on real test results.",
                "NOT A WIN": "Failed: " + ", ".join(names[c.condition] for c in conds if c.status == FAIL) + ".",
                "NOT VERIFIED": "No failure is known, but not verified: " + ", ".join(names[c.condition] for c in conds if c.status == NV) + "."}[overall]
        if not p.patch_applied:
            expl += " The approved patch could not be applied."
        p.win = WinEvaluation(evaluated_at=now_iso(), simulated=False, conditions=conds, overall=overall,
                              explanation=expl + " Results come from real commands run in the ACFM test workspace (not a sandbox).")
        self._log(p, 15, f"Compared {len(p.comparison)} prediction(s): {n['MATCH']} MATCH, {n['MISMATCH']} MISMATCH, {n['NOT VERIFIED']} NOT VERIFIED.")
        self._log(p, 16, f"ACFM Win: {overall}.")

