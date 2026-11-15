"""LLM adapter: a TOOL that AFM may consult. Never an authority on the actual environment.

- MockLLM: deterministic, no key, no network. Default.
- ClaudeProvider (adapters/claude_provider.py): AFM_LLM_PROVIDER=claude. Official SDK, the user's own credentials.
- Any other provider name → RealProviderPlaceholder, which refuses to run instead of pretending.

Everything returned is labelled LLM-generated. Instruction-like text found in object data is
treated as untrusted data: it is reported, never followed (R22).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

from ..domain.errors import AFMError
from ..domain.models import ObjectTypeExplanation

INJECTION_PATTERNS = [
    r"ignore (all |the |your )?(previous |prior )?(rules|instructions)",
    r"system instruction",
    r"auto-?approve",
    r"skip (the )?(review|approval)",
    r"delete (order|all)",
    r"disable (the )?(rules|approval)",
]

# Fields the chat may PROPOSE for a use case. They are shown to the human and never applied silently.
INPUT_FIELDS = ["role", "purpose", "environment_type", "environment_name", "adapter_id", "target_name", "target_type",
                "target_identifier", "proposed_action", "goal_outcome", "desired_input", "desired_output", "success_criteria", "constraints"]
STEP_FIELDS = [f"step_{i}" for i in range(1, 17)]  # proposed new text for a step's "how AFM thinks" note (16 steps)
USECASE_FIELDS = INPUT_FIELDS + ["extra_rules"] + STEP_FIELDS  # extra_rules: newline-separated use-case rules (narrow only)


def find_instruction_like_text(texts: list[str]) -> list[str]:
    return [t for t in texts if t and any(re.search(p, t, re.IGNORECASE) for p in INJECTION_PATTERNS)]


class LLMAdapter(Protocol):
    name: str

    def explain_object_type(self, environment_type: str, object_type: str,
                            observations: dict[str, Any] | None, question: str) -> ObjectTypeExplanation: ...

    def propose_plans(self, goal_text: str, observations: dict[str, Any]) -> list[dict[str, Any]]: ...

    def chat(self, context: dict[str, Any], history: list[dict[str, str]], message: str) -> dict[str, Any]: ...


_KNOWLEDGE: dict[str, dict[str, Any]] = {
    "inventory_record": dict(
        explanation="Inventory records commonly represent quantities available, reserved, or in transit for one product at one location.",
        common_inputs=["reservations", "receipts", "adjustments", "cycle counts"], common_outputs=["available quantity", "reserved quantity", "on-hand quantity"],
        typical_behavior="Reserving stock usually lowers 'available' without lowering 'on hand' until the goods are picked.",
        potential_relationships=["belongs to a warehouse", "counts a product", "orders depend on it", "dashboards display it", "ERP or WMS systems may sync it"],
        suggested_read_only_inspections=["current on hand / reserved / available", "which pending orders are eligible for this stock", "who reads this record"]),
    "customer_order": dict(
        explanation="Customer orders usually request a quantity of a product and move through statuses such as pending, reserved, picked, shipped, delivered.",
        common_inputs=["order lines", "reservations", "cancellations"], common_outputs=["order status", "fulfilment requests"],
        typical_behavior="An order is typically considered allocated once enough stock is reserved; shipping is a separate later step.",
        potential_relationships=["depends on inventory", "belongs to a customer", "may have delivery deadlines"],
        suggested_read_only_inspections=["quantity, status, eligible warehouses", "eligible stock levels"]),
    "warehouse": dict(
        explanation="A warehouse is a storage location holding inventory for one or more products.", common_inputs=["inbound deliveries", "transfers"],
        common_outputs=["picked goods", "inventory records"], typical_behavior="Stock levels change with receipts, reservations, picks and transfers.",
        potential_relationships=["holds inventory records", "serves certain orders or regions"], suggested_read_only_inspections=["inventory per warehouse"]),
    "inventory_dashboard": dict(
        explanation="An inventory dashboard is a read model that displays stock figures; it usually does not own the data.", common_inputs=["inventory updates"],
        common_outputs=["displayed figures"], typical_behavior="Real dashboards may refresh immediately or on a schedule; stale displays are common.",
        potential_relationships=["displays inventory records"], suggested_read_only_inspections=["displayed values vs. the inventory records"]),
    "product": dict(explanation="A product is a catalog item identified by a SKU.", common_inputs=["catalog updates"], common_outputs=["SKU data"],
                    typical_behavior="Usually static during order processing.", potential_relationships=["counted by inventory records", "ordered by customer orders"],
                    suggested_read_only_inspections=["SKU and attributes"]),
    "web_server": dict(
        explanation="A web server (often acting as a reverse proxy) receives client requests and forwards them to an application on an upstream host and port.",
        common_inputs=["HTTP requests", "configuration (listen port, upstream)"], common_outputs=["forwarded requests", "responses", "access logs"],
        typical_behavior="If the upstream port does not match where the application listens, clients typically get 502/503 errors.",
        potential_relationships=["forwards to an application", "receives traffic from users", "may sit behind a load balancer or firewall"],
        suggested_read_only_inspections=["the configured upstream host and port", "whether the server reloads config automatically", "a test request through the server"]),
    "python_application": dict(
        explanation="A Python web application typically listens on a TCP port and serves HTTP requests, often behind a reverse proxy.",
        common_inputs=["HTTP requests", "configuration or environment variables (e.g. PORT)"], common_outputs=["HTTP responses", "database queries", "logs"],
        typical_behavior="Changing the listening port usually needs a restart; anything that calls the old port stops reaching it.",
        potential_relationships=["called by a web server", "reads/writes a database", "checked by a health monitor", "configured by a config file"],
        suggested_read_only_inspections=["the configured listening port", "who calls this port (proxy, monitors, other clients)"]),
    "database": dict(
        explanation="A database stores application data and serves queries over its own connection, usually on its own port.",
        common_inputs=["queries", "migrations"], common_outputs=["query results"], typical_behavior="Usually unaffected by the application's listening port.",
        potential_relationships=["used by applications", "backed up by jobs"], suggested_read_only_inspections=["connection status", "whether any config references the app port"]),
    "health_monitor": dict(
        explanation="A health monitor periodically checks an endpoint or port and raises alerts when it fails.", common_inputs=["target host/port", "check interval"],
        common_outputs=["health status", "alerts"], typical_behavior="If it still checks an old port after a change, it reports the service as down.",
        potential_relationships=["checks an application", "notifies people or on-call systems"], suggested_read_only_inspections=["the configured target port", "who receives alerts"]),
    "user_group": dict(explanation="A user group represents people or clients that use a service.", common_inputs=["service availability"], common_outputs=["requests"],
                       typical_behavior="Users notice errors when the path to the service breaks.", potential_relationships=["send requests to a front door such as a web server"],
                       suggested_read_only_inspections=["how users reach the service"]),
    "input": dict(explanation="An input object holds a value that other components read.", common_inputs=["a new value"], common_outputs=["its value"],
                  typical_behavior="Downstream components recompute when it changes.", potential_relationships=["feeds processors"], suggested_read_only_inspections=["current value", "who reads it"]),
    "processor": dict(explanation="A processor transforms its input into an output by a fixed rule.", common_inputs=["an input value"], common_outputs=["a computed output"],
                      typical_behavior="Its output changes whenever its input changes.", potential_relationships=["reads an input", "feeds a display"], suggested_read_only_inspections=["its rule (e.g. ×2)", "current input and output"]),
    "display": dict(explanation="A display shows a value produced elsewhere; it does not own the data.", common_inputs=["a value to show"], common_outputs=["what the user sees"],
                    typical_behavior="It mirrors its source, possibly with a delay.", potential_relationships=["shows a processor's output"], suggested_read_only_inspections=["shown value vs. source value"]),
}

_ROLES = [(r"cloud|aws|ec2", "Cloud infrastructure assistant"), (r"sap", "SAP business process assistant"),
          (r"python|web ?app|port|server", "Python application engineer"), (r"mobile", "Mobile application assistant"),
          (r"data readiness|dataset", "Data readiness reviewer"), (r"calculator", "Calculator assistant"),
          (r"inventory|warehouse|order", "Inventory assistant")]
_ENVS = [(r"\bec2\b|\baws\b", ("AWS infrastructure", None)), (r"\bsap\b", ("SAP system", None)),
         (r"port|web ?server|python app", ("Web application (simulated)", "webapp-demo")),
         (r"inventory|warehouse|\border", ("Inventory (simulated)", "warehouse-demo")),
         (r"object a|processor|playground", ("Generic object playground (simulated)", "object-playground")),
         (r"spreadsheet|excel", ("Spreadsheet", None)), (r"mobile", ("Mobile application", None)), (r"calculator", ("Calculator", None))]


class MockLLM:
    """Deterministic stand-in. Canned general knowledge, canned proposals (incl. deliberately invalid ones)
    and a rule-based chat that proposes form fields. No network."""

    name = "mock-llm (deterministic, offline)"

    def test(self) -> dict[str, Any]:
        return {"ok": True, "latency_ms": 0, "sample": "mock: no network call"}

    def explain_object_type(self, environment_type: str, object_type: str,
                            observations: dict[str, Any] | None, question: str) -> ObjectTypeExplanation:
        k = _KNOWLEDGE.get(object_type)
        ignored = find_instruction_like_text([str(v) for v in (observations or {}).values() if isinstance(v, str)])
        if k is None:
            return ObjectTypeExplanation(
                provider=self.name, object_type=object_type, environment_type=environment_type,
                explanation=f"I have no general knowledge about '{object_type}' objects. Treat its behavior as unknown until inspected.",
                common_inputs=[], common_outputs=[], typical_behavior="Unknown.", potential_relationships=[],
                suggested_read_only_inspections=["inspect_object", "list_relationships"], assumptions=[],
                unknowns=["Everything about this object type."], ignored_instructions=ignored)
        return ObjectTypeExplanation(
            provider=self.name, object_type=object_type, environment_type=environment_type, **k,
            assumptions=["This is general knowledge about typical systems, not about this environment.",
                         "Behavior in this simulation is defined by its adapter, which takes precedence."],
            unknowns=["Whether this object follows the typical pattern here.", "Dependencies on this object that are not in the catalog."],
            ignored_instructions=ignored)

    def propose_plans(self, goal_text: str, observations: dict[str, Any]) -> list[dict[str, Any]]:
        # canned per environment, deliberately including invalid proposals that AFM's gate must reject
        return list(observations.get("mock_proposals", []))

    def chat(self, context: dict[str, Any], history: list[dict[str, str]], message: str) -> dict[str, Any]:
        low = message.lower()
        proposed: dict[str, str] = {}
        role_m = re.search(r"\byou are (?:an? )?([^.,;!?]+)", message, re.IGNORECASE)
        if role_m:
            proposed["role"] = role_m.group(1).strip().capitalize()
        elif not context.get("role"):
            for pat, role in _ROLES:
                if re.search(pat, low):
                    proposed["role"] = role
                    break
        env_hit = None
        for pat, env in _ENVS:
            if re.search(pat, low):
                env_hit = env
                proposed["environment_type"], adapter = env
                if adapter:
                    proposed["adapter_id"] = adapter
                break
        goal_m = re.search(r"\b(?:i want to|i'd like to|goal is to|please)\s+([^.?!]+)", message, re.IGNORECASE)
        if goal_m:
            proposed["goal_outcome"] = goal_m.group(1).strip().rstrip(".") + "."
        port_m = re.search(r"port\s*(?:to\s*)?(\d{2,5})", low)
        if port_m:
            proposed.setdefault("goal_outcome", f"Change the application to port {port_m.group(1)} while keeping it accessible.")
            proposed["target_name"], proposed["target_type"] = "Python application", "python_application"
        if re.search(r"\bec2\b", low):
            proposed["target_type"] = "EC2 instance"
        # step overrides: "step 9: <new text>" / "change step 4 to <text>"
        for m in re.finditer(r"\bstep\s*(\d{1,2})\s*(?::|=|should say|to say|to)\s*([^\n]+?)(?=\s*\bstep\s*\d{1,2}\s*(?::|=)|$)", message, re.IGNORECASE):
            n = int(m.group(1))
            if 1 <= n <= 16:
                proposed[f"step_{n}"] = m.group(2).strip().strip("\"“”")
        rule_m = re.search(r"\badd (?:a )?(?:use-case )?rule:?\s*(.+)", message, re.IGNORECASE)
        if rule_m:
            proposed["extra_rules"] = rule_m.group(1).strip().rstrip(".")
        if any(k.startswith("step_") for k in proposed):
            proposed.pop("goal_outcome", None) if not re.search(r"\bgoal\b", low) else None
        # reply
        lines: list[str] = []
        labels = ["llm_general"]
        if env_hit and env_hit[1] is None:
            lines.append(f"I can help think this through. {env_hit[0]} has no connected adapter in AFM, so I cannot inspect it, simulate it or "
                         "execute anything there. I can only describe possible effects in general, based on what you tell me.")
            if "stop" in low and "ec2" in low:
                lines.append("In general, stopping an EC2 instance ends its running processes, can drop in-memory data and ephemeral storage, "
                             "may change its public IP, and breaks anything that depends on it (load balancers, other services, users).")
            labels.append("unknown")
        elif env_hit:
            lines.append(f"This matches a simulated AFM playground ({env_hit[0]}). AFM can inspect its known objects and predict consequences there; "
                         "those results will be labelled as simulated, not real.")
            labels.append("simulated")
        else:
            lines.append("I can help prepare a use case. Tell me the role AFM should play, the environment, the object to assess and what you want to achieve.")
        missing = [f for f, q in (("role", "What role should AFM play?"), ("environment_type", "Which environment will AFM work in?"),
                                   ("target_name", "Which object or system should AFM assess?"), ("goal_outcome", "What do you want to achieve?"))
                   if not (context.get(f) or proposed.get(f))]
        qs = {"role": "What role should AFM play?", "environment_type": "Which environment will AFM work in?",
              "target_name": "Which object or system should AFM assess?", "goal_outcome": "What do you want to achieve?"}
        if proposed:
            lines.append("I suggested some form fields below. Nothing is applied until you accept them.")
        if missing:
            lines.append("Still missing: " + ", ".join(m.replace("_", " ") for m in missing) + ".")
        return {"reply": " ".join(lines), "labels": labels, "proposed_fields": proposed, "suggested_questions": [qs[m] for m in missing]}


    def draft_project_plan(self, ctx: dict[str, Any]) -> dict[str, Any]:
        msg = (ctx.get("message") or "").strip()
        goal = ctx.get("goal") or msg
        cmds = [c["argv"] for c in (ctx.get("suggested_commands") or [])][:1]
        preds, crit = [], []
        if cmds:
            preds = [{"statement": "The test command still exits with 0 after the change.", "type": "command_exit", "command": 0, "test": "", "expect": "0"},
                     {"statement": "No existing test changes outcome because of the change.", "type": "no_other_changes", "command": 0, "test": "", "expect": ""}]
            crit = [{"text": "The project's tests pass after the change.", "type": "command_exit", "command": 0, "test": "", "expect": "0"}]
        target = next((f["path"] for f in ctx.get("files", [])), "the project")
        return normalize_draft({
            "summary": ("I'm the offline mock, so I can't write the code change itself. I filled in the Task Goal from your words, a test command "
                        "and testable predictions. Switch to Claude or a local model under 'Use your LLM' and I'll propose real plans."),
            "goal": goal[:600], "desired_input": "", "desired_output": "", "commands": cmds, "criteria": crit,
            "plans": [{"title": "Plan A (mock): no code change written", "approach": "The mock cannot write code; add the patch by hand.",
                       "edits": [], "predictions": preds, "risks": [],
                       "consequences": [{"object": target, "relation": "target", "effect": "Unknown: the offline mock cannot read code.",
                                         "kind": "unknown", "likelihood": "unknown", "why": "No LLM reasoning available."}]}],
            "assumptions": ["The project's dependencies are installed for the suggested command."],
            "unknowns": ["The mock did not read the selected files."]})


    def describe_project(self, ctx: dict[str, Any]) -> dict[str, Any]:
        readme = next((f["content"] for f in ctx.get("files", []) if f["path"].lower().split("/")[-1].startswith("readme")), "")
        first = next((ln.strip("# ").strip() for ln in readme.splitlines() if ln.strip() and not ln.startswith("#")), "")
        srcs = [f["path"] for f in ctx.get("files", []) if not f["path"].lower().split("/")[-1].startswith("readme")]
        return normalize_overview({
            "name": ctx.get("name", ""), "goal": first or "Not stated in a README (the offline mock only reads it literally).",
            "features": [f"Code in {p}" for p in srcs[:8]] or ["No source files were read."],
            "suggestions": [{"title": "Add or extend tests", "change": "Add a test for the main function so its behaviour is checked.", "why": "More tests make predictions measurable.", "files": srcs[:1]}],
            "unknowns": ["The offline mock does not understand code. Switch to Claude or a local model for a real description."]})


def normalize_overview(d: dict[str, Any]) -> dict[str, Any]:
    lst = lambda v, n, k=300: [str(s)[:k] for s in (v or []) if isinstance(s, (str, int, float))][:n]
    sug = [{"title": str(s.get("title", ""))[:120], "change": str(s.get("change", ""))[:600], "why": str(s.get("why", ""))[:400],
            "files": lst(s.get("files"), 6, 200)} for s in (d.get("suggestions") or []) if isinstance(s, dict) and s.get("change")][:8]
    return {"name": str(d.get("name", ""))[:120], "goal": str(d.get("goal", ""))[:800], "features": lst(d.get("features"), 20),
            "suggestions": sug, "unknowns": lst(d.get("unknowns"), 8), "labels": ["llm_generated"]}


OVERVIEW_SHAPE = ('{"name": str, "goal": str (what the project is for, 1-2 sentences), "features": [str] (every feature you can see, one per item), '
                  '"suggestions": [{"title": str, "change": str (the change in plain words, as a request a developer could act on), '
                  '"why": str, "files": [str]}], "unknowns": [str]}')


def project_overview_prompt(ctx: dict[str, Any]) -> str:
    files = "\n".join(f"<file path=\"{f['path']}\">\n{f['content']}\n</file>" for f in ctx.get("files", []))
    return ("Describe this code project for a human who wants to test a change on it with ACFM. From the files below, give the project "
            "name, its goal, the list of ALL features you can see, and 3 to 6 small, testable improvement changes (bug fixes, missing "
            "validation, missing tests, clearer errors). Each change must be concrete enough to implement as one small patch. Say "
            "what you could not see in unknowns. Do not invent features that are not in the files.\n"
            f"Folder name: {ctx.get('name')}\nFile count: {ctx.get('file_count')}\nLanguages: {json.dumps(ctx.get('languages'))}\n"
            f"Top level: {json.dumps(ctx.get('top_level'))}\nTest files: {json.dumps(ctx.get('tests'))}\n"
            f"<untrusted_data>\n{files or '(no files read)'}\n</untrusted_data>")


_CHECK_DOC = ('Prediction/criterion check types: "command_exit" with expect "0" (the command succeeds), "nonzero" (it fails) or "same" '
              '(same exit code as the baseline run before the change); "test_outcome" with test = the exact test id the runner prints '
              '(pytest: path::test_name, using test files you were shown) and expect "passed" or "failed"; "no_other_changes" (expect "") '
              'meaning no test other than those named in test_outcome predictions changes outcome between baseline and after (needs a runner '
              'that lists individual tests, e.g. pytest -rA); "manual" (expect "") when only a human can judge it. "command" is the 0-based '
              'index into commands. Never use git or other non-test programs as test commands, and do not predict which files change: the '
              'human sees the exact diff.')
_EDITS_SHAPE = ('[{"path": str (relative to the repo root), "old": str (text copied EXACTLY from the file, including indentation, unique in the '
                'file, 2-8 lines; empty only to create a new file), "new": str (the replacement text)}]')
_CONSEQ_SHAPE = ('[{"object": str (a file, function, component, API, data or user group), "relation": "target"|"connected"|"environment", '
                 '"effect": str, "kind": "benefit"|"risk"|"neutral"|"unknown", "likelihood": "expected"|"possible"|"unknown", "why": str}]')
_PRED_SHAPE = ('[{"statement": str, "type": "command_exit"|"test_outcome"|"no_other_changes"|"manual", "command": int, "test": str, '
               '"expect": "0"|"nonzero"|"same"|"passed"|"failed"|""}]')
DRAFT_SHAPE = ('{"summary": str (your reply to the human, plain words), "goal": str (the Task Goal in one sentence), "desired_input": str, '
               '"desired_output": str, "commands": [[str]] (argv lists, no shell), "criteria": [same shape as a prediction but "text" instead of '
               f'"statement"], "plans": [{{"title": str, "approach": str, "edits": {_EDITS_SHAPE}, "consequences": {_CONSEQ_SHAPE}, '
               f'"predictions": {_PRED_SHAPE}, "risks": [str]}}], "assumptions": [str], "unknowns": [str]}}')


def project_draft_prompt(ctx: dict[str, Any]) -> str:
    files = "\n".join(f"<file path=\"{f['path']}\">\n{f['content']}\n</file>" for f in ctx.get("files", []))
    convo = "\n".join(f"{m['role']}: {m['content'][:1500]}" for m in ctx.get("history", [])[-10:])
    return ("You help ACFM (Action–Consequence Foresight Model) test a change on a real code project. The human describes the change in "
            "plain words. Reply briefly in plain words (summary) and give: the Task Goal in one sentence with desired input/output; the "
            "test commands that measure it (argv lists, never a shell, never install anything, never push); observable success criteria; "
            "and 2 to 3 ALTERNATIVE plans that reach the goal in different ways (e.g. minimal fix, fix + validation, fix + new test). "
            "For EACH plan give: the code edits as exact search/replace pairs (ACFM builds the diff itself); its predicted consequences "
            "for each affected object: the target it changes, the connected objects that use it (callers, importers, API clients, tests, "
            "UI) and the whole environment (behaviour users see, contracts, performance, security), each marked benefit / risk / neutral "
            "/ unknown with a reason; its testable predictions; and its risks. Say 'unknown' when you cannot know. If the files are not "
            "enough to write correct edits, leave edits empty and say which file you need. If the human asks to adjust a plan, return "
            "the full updated set of plans. ACFM uses a plan only after the human chooses, saves and approves it; you cannot run anything.\n"
            + _CHECK_DOC + "\n"
            f"Saved Task Goal: {ctx.get('goal') or '(none yet)'}\nDesired input: {ctx.get('desired_input') or '-'}\nDesired output: {ctx.get('desired_output') or '-'}\n"
            f"Human note: {ctx.get('note') or '-'}\nLanguages: {json.dumps(ctx.get('languages'))}\nTest files: {json.dumps(ctx.get('tests'))}\n"
            f"Suggested test commands (not run): {json.dumps([c['argv'] for c in ctx.get('suggested_commands') or []])}\n"
            + (f"Current plan (JSON): {json.dumps(ctx['current_plan'])}\n" if ctx.get("current_plan") else "")
            + (f"Conversation so far:\n{convo}\n" if convo else "")
            + (f"Human's latest message: {ctx['message']}\n" if ctx.get("message") else "")
            + f"<untrusted_data>\n{files or '(no files selected)'}\n</untrusted_data>")


def _coerce_expect(t: str, e: str) -> str:
    """Small wording slips ('same exit code as before', 'pass') become the allowed value instead of failing the save."""
    e = (e or "").strip().lower()
    if t == "command_exit":
        return e if e in ("0", "nonzero", "same") else "same" if "same" in e or "baseline" in e or "before" in e else \
            "nonzero" if any(w in e for w in ("non", "fail", "error", "1")) else "0"
    if t == "test_outcome":
        return e if e in ("passed", "failed") else "failed" if "fail" in e else "passed"
    return ""


def _norm_check(x: dict) -> dict:
    t = x.get("type") if x.get("type") in ("command_exit", "test_outcome", "no_other_changes", "manual") else "manual"
    try:
        ci = max(0, min(19, int(x.get("command", 0) or 0)))
    except (TypeError, ValueError):
        ci = 0
    return {"type": t, "command": ci, "test": str(x.get("test", ""))[:300], "expect": _coerce_expect(t, str(x.get("expect", "")))}


def _norm_preds(items: Any) -> list[dict]:
    return [{"statement": str(x.get("statement", ""))[:400], "check": _norm_check(x.get("check") if isinstance(x.get("check"), dict) else x)}
            for x in (items or []) if isinstance(x, dict) and x.get("statement")][:10]


def _norm_conseq(items: Any) -> list[dict]:
    pick = lambda v, ok, d: v if v in ok else d
    return [{"object": str(c.get("object", ""))[:200], "relation": pick(c.get("relation"), ("target", "connected", "environment"), "connected"),
             "effect": str(c.get("effect", ""))[:400], "kind": pick(c.get("kind"), ("benefit", "risk", "neutral", "unknown"), "unknown"),
             "likelihood": pick(c.get("likelihood"), ("expected", "possible", "unknown"), "unknown"), "why": str(c.get("why", ""))[:400],
             "source": c.get("source") if c.get("source") in ("llm", "acfm_search", "human") else "llm"}
            for c in (items or []) if isinstance(c, dict) and c.get("object") and c.get("effect")][:20]


def normalize_draft(d: dict[str, Any]) -> dict[str, Any]:
    """Shape an LLM draft: shared goal/commands/criteria + 1-3 alternative plans, each with edits, per-object
    consequences and testable predictions. Invalid items are dropped; the human reviews and chooses."""
    cmds = [[str(a)[:300] for a in c][:30] for c in (d.get("commands") or []) if isinstance(c, list) and c][:5]
    crit = [{"text": str(x.get("text", ""))[:400], "check": _norm_check(x.get("check") if isinstance(x.get("check"), dict) else x), "source": "llm_proposed"}
            for x in (d.get("criteria") or []) if isinstance(x, dict) and x.get("text")][:8]
    lst = lambda v, n=10: [str(s)[:300] for s in (v or []) if isinstance(s, (str, int, float))][:n]
    raw_plans = [x for x in (d.get("plans") or []) if isinstance(x, dict)][:3]
    if not raw_plans:  # older single-plan shape
        raw_plans = [{"title": "Plan A", "approach": "", "edits": d.get("edits") or [], "patch": d.get("patch", ""),
                      "predictions": d.get("predictions") or [], "consequences": d.get("consequences") or [], "risks": []}]
    plans = []
    for i, x in enumerate(raw_plans):
        edits = [{"path": str(e.get("path", ""))[:300], "old": str(e.get("old", ""))[:20000], "new": str(e.get("new", ""))[:20000]}
                 for e in (x.get("edits") or []) if isinstance(e, dict) and e.get("path")][:20]
        plans.append({"title": str(x.get("title") or f"Plan {chr(65 + i)}")[:120], "approach": str(x.get("approach", ""))[:600], "edits": edits,
                      "patch": str(x.get("patch", "") or "")[:60000], "consequences": _norm_conseq(x.get("consequences")),
                      "predictions": _norm_preds(x.get("predictions")), "risks": lst(x.get("risks"), 8)})
    return {"summary": str(d.get("summary", ""))[:1500], "goal": str(d.get("goal", "") or "")[:600],
            "desired_input": str(d.get("desired_input", "") or "")[:500], "desired_output": str(d.get("desired_output", "") or "")[:500],
            "commands": cmds, "criteria": crit, "plans": plans, "recommended": 0, "recommended_why": "",
            "patch": plans[0]["patch"], "predictions": plans[0]["predictions"],
            "assumptions": lst(d.get("assumptions")), "unknowns": lst(d.get("unknowns")), "labels": ["llm_generated", "prediction"]}


class RealProviderPlaceholder:
    """Any provider other than mock/claude: not implemented. Refuses instead of pretending."""

    def draft_project_plan(self, *a, **k):
        self._refuse()

    def describe_project(self, *a, **k):
        self._refuse()

    def __init__(self, provider: str):
        self.name = f"{provider} (not configured)"
        self.provider = provider

    def _refuse(self):
        raise AFMError("llm_provider_unavailable", f"LLM provider '{self.provider}' is not implemented. Use AFM_LLM_PROVIDER=mock or claude.", 501)

    def explain_object_type(self, *a, **k):
        self._refuse()

    def propose_plans(self, *a, **k):
        self._refuse()

    def chat(self, *a, **k):
        self._refuse()


def get_llm(use_ui_settings: bool = True) -> LLMAdapter:
    """UI settings (backend/data/llm_settings.json) win; otherwise environment (backend/.env); otherwise the mock."""
    if use_ui_settings:
        from . import llm_settings

        s = llm_settings.load()
        if s is not None:
            return llm_settings.build(s)
    provider = os.environ.get("AFM_LLM_PROVIDER", "mock").strip().lower()
    if provider in ("", "mock"):
        return MockLLM()
    if provider in ("claude", "anthropic"):
        from .claude_provider import ClaudeProvider

        return ClaudeProvider()
    return RealProviderPlaceholder(provider)
