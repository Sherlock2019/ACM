"""LLM adapter: a TOOL that AFM may consult. Never an authority on the actual environment.

- MockLLM: deterministic, no key, no network. Default.
- ClaudeProvider (adapters/claude_provider.py): AFM_LLM_PROVIDER=claude. Official SDK, the user's own credentials.
- Any other provider name → RealProviderPlaceholder, which refuses to run instead of pretending.

Everything returned is labelled LLM-generated. Instruction-like text found in object data is
treated as untrusted data: it is reported, never followed (R22).
"""
from __future__ import annotations

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


class RealProviderPlaceholder:
    """Any provider other than mock/claude: not implemented. Refuses instead of pretending."""

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
