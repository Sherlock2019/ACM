"""Web application demo adapter: users → web server → Python application → database, plus a health monitor.

Main demonstration of AFM: changing the application's port works locally, but connected objects
(web server, health monitor) still point at the old port, so the human goal "keep it accessible" fails
unless the plan updates them too. All behavior is explicit, fictional and simulated.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...domain.models import (
    Action, CheckStatus, Consequence, GoalCriterion, GoalSpec, PermissionClass, Plan, SimulationResult,
)
from ...engine.environment import EnvState
from ..base import AdapterError, EnvironmentAdapter

S = CheckStatus
RULE_APP = "WEB-1 set_app_port: application listens on the new port (restarts automatically, configured)"
RULE_PROXY = "WEB-2 set_proxy_upstream: web server forwards to the new upstream port"
RULE_MON = "WEB-3 set_monitor_port: health monitor checks the new port"
RULE_ACCESS = "WEB-4 users can reach the app iff web server and app run and upstream_port == listening_port"
RULE_HEALTH = "WEB-5 monitor is healthy iff target_port == application's listening_port"
RULE_DB = "WEB-6 the database connection does not depend on the application's listening port (configured)"
RULE_TEST = "WEB-7 send_test_request: a simulated request through the web server reaches the app iff WEB-4 holds"
PORT_TOOLS = {"set_app_port": ("python-app", "listening_port", "port", RULE_APP),
              "set_proxy_upstream": ("web-server", "upstream_port", "upstream_port", RULE_PROXY),
              "set_monitor_port": ("health-monitor", "target_port", "port", RULE_MON)}
_OTHER_DOMAIN = r"\b(order|orders|warehouse|inventory|stock|object a|object b|processor)\b"
_UNSUPPORTED = {
    "delete": "Deleting data is prohibited (rule W1).",
    "drop": "Deleting data is prohibited (rule W1).",
    "stop": "Stopping services is prohibited (rule W5).",
    "shutdown": "Stopping services is prohibited (rule W5).",
    "firewall": "The firewall is an unknown dependency in this demo; it cannot be inspected or changed.",
    "deploy": "Deployments are not modelled in this demo.",
    "ignore": "Goals cannot change or switch off AFM's rules (R10).",
}


def accessible(s: EnvState) -> bool:
    ws, app = s.objects["web-server"].state, s.objects["python-app"].state
    return ws["status"] == "running" and app["status"] == "running" and ws["upstream_port"] == app["listening_port"]


def healthy(s: EnvState) -> bool:
    return s.objects["health-monitor"].state["target_port"] == s.objects["python-app"].state["listening_port"]


class WebAppAdapter(EnvironmentAdapter):
    environment_id = "webapp-demo"
    name = "Web application port change"
    adapter_name = "WebAppSimulationAdapter"
    summary = "Change a web application's port without breaking access. The main demonstration of AFM's reasoning loop."
    scenario_path = Path(__file__).with_name("scenario.json")
    error_rules = {
        "invalid_port": "W4 Ports must be between 1024 and 65535.",
        "port_conflict": "W4 Ports must not be used by another known service.",
        "no_change": "The plan would not change anything.",
    }

    # ------------------------------------------------------------------ goals
    def interpret_goal(self, text: str, state: EnvState) -> GoalSpec:
        t = " ".join(text.strip().split())
        low = t.lower()
        if not t:
            return self.unsupported(t, "The goal is empty.")
        if re.search(_OTHER_DOMAIN, low):
            return self.unsupported(t, "This goal does not fit the web application environment: it has a web server, a Python application, a database and a health monitor only. Select the matching playground instead.")
        about_port = re.search(r"\b(port|listen\w*)\b", low) and re.search(r"\b(app|application|service)\b", low)
        constraints = []
        if re.search(r"\b(do not|don't|dont|never)\s+(delete|drop|lose)\s+(any\s+)?data\b", low):
            constraints.append("data")
            low_for_verbs = re.sub(r"\b(do not|don't|dont|never)\s+(delete|drop|lose)\s+(any\s+)?data\b", "", low)
        else:
            low_for_verbs = low
        for verb, why in _UNSUPPORTED.items():
            if re.search(rf"\b{verb}\b", low_for_verbs):
                return self.unsupported(t, f"This demo cannot evaluate that goal. {why}")
        if not about_port:
            return self.unsupported(t, "AFM could not map this goal to supported success criteria. This environment understands goals about changing the application's port.")
        m = re.search(r"\bport\s*(?:to|=|:)?\s*(\d{1,6})\b", low) or re.search(r"\bto\s+(?:port\s+)?(\d{1,6})\b", low)
        if not m:
            return self.unsupported(
                t, "The goal does not say which port to use, so AFM cannot plan or predict yet (R16, R17).",
                clarification="Which port should the application use? For example: “Change the application to port 9000 while keeping it accessible.”",
                missing=["The target port number."])
        port = int(m.group(1))
        app = state.objects["python-app"].state
        crit = [GoalCriterion(id="c1", kind="app_listens_on", params={"port": port}, description=f"The application listens on port {port}.")]
        keep = bool(re.search(r"\b(accessible|reachable|available|keep\w*\s+(it|the app\w*)\s+(up|working|running)|without\s+(breaking|downtime))\b", low))
        if keep:
            crit.append(GoalCriterion(id="c2", kind="app_accessible", params={}, description="Users can still reach the application through the web server."))
        if "data" in constraints:
            crit.append(GoalCriterion(id=f"c{len(crit) + 1}", kind="data_preserved", params={}, description="No data is deleted (database unchanged)."))
        notes = []
        if re.search(r"\bask me\b|\bapprov|\breview\b", low):
            notes.append("“Ask me before making changes” is always enforced: every state-changing action needs your approval (R08).")
        return GoalSpec(
            goal_id=self.goal_id(t), environment_id=self.environment_id, text=t, supported=True,
            intent="change_app_port", parameters={"port": port, "from_port": app["listening_port"]}, success_criteria=crit,
            explanation=" ".join(["Mapped to structured criteria.", *notes]),
            intended_benefits=[f"The application moves to port {port}."],
            potential_negative_effects=["Objects that point at the old port (web server, health monitor) may break: users could lose access and monitoring could alert.",
                                        "A firewall, if one exists, might block the new port (unknown)."],
            missing_information=["Whether a firewall exists and allows the new port is not verified.",
                                 "Other clients that call the application directly are not known.",
                                 "Acceptable downtime window is not stated."],
        )

    def propose_plans(self, goal: GoalSpec, state: EnvState) -> list[Plan]:
        port = goal.parameters["port"]
        old = state.objects["python-app"].state["listening_port"]

        def act(i: str, tool: str, target: str, params: dict, purpose: str, pre: list[str]) -> Action:
            perm = PermissionClass.allowed if tool == "send_test_request" else PermissionClass.requires_approval
            return Action(action_id=i, tool=tool, operation="verify" if tool == "send_test_request" else "configure",
                          target_object_id=target, parameters=params, purpose=purpose, permission=perm, expected_preconditions=pre)

        app = lambda p: act(f"{p}-a1", "set_app_port", "python-app", {"port": port}, f"Make the application listen on port {port}.",
                            [f"Application currently listens on {old}.", f"Port {port} is free (checked in simulation)."])
        proxy = lambda p, n: act(f"{p}-a{n}", "set_proxy_upstream", "web-server", {"upstream_port": port}, f"Forward web traffic to port {port}.",
                                 [f"Web server currently forwards to {state.objects['web-server'].state['upstream_port']}."])
        mon = lambda p, n: act(f"{p}-a{n}", "set_monitor_port", "health-monitor", {"port": port}, f"Check application health on port {port}.",
                               [f"Monitor currently checks {state.objects['health-monitor'].state['target_port']}."])
        test = lambda p, n: act(f"{p}-a{n}", "send_test_request", "web-server", {}, "Verify that a test request reaches the application.", ["Read-only check."])
        common = dict(goal_id=goal.goal_id, assumptions=["The catalog shows every known dependency of the application's port.",
                                                         "Configuration changes take effect immediately (configured behavior)."],
                      known_limitations=["Restart timing, TLS and DNS are not modelled.", "The possible firewall is not simulated."])
        return [
            Plan(plan_id="P1", title=f"Change only the application port to {port}", actions=[app("P1")], **common),
            Plan(plan_id="P2", title=f"Change app port and web-server upstream to {port}, then test",
                 actions=[app("P2"), proxy("P2", 2), test("P2", 3)], **common),
            Plan(plan_id="P3", title=f"Change app, web server and health monitor to {port}, then test",
                 actions=[app("P3"), proxy("P3", 2), mon("P3", 3), test("P3", 4)], **common),
        ]

    # ------------------------------------------------------------------ simulation
    def simulate_action(self, action: Action, state: EnvState, step: int) -> list[Consequence]:
        if action.tool == "send_test_request":
            ok = accessible(state)
            ws, app = state.objects["web-server"].state, state.objects["python-app"].state
            return [Consequence(
                step=step, affected_object_id="web-server", relationship_to_target="target (read-only check)",
                before={}, predicted_after={"test_request_reaches_app": ok},
                description=(f"A test request through the web server would reach the application on port {app['listening_port']}." if ok else
                             f"A test request would FAIL: the web server forwards to {ws['upstream_port']} but the app listens on {app['listening_port']}."),
                type="direct", evidence_rule=RULE_TEST, status="conditional", effect="benefit" if ok else "warning",
                assumptions=["No unknown network rule (e.g. a firewall) blocks the port."], observable={"test_request_reaches_app": ok},
            )]
        if action.tool not in PORT_TOOLS:
            raise AdapterError("unsupported_action", f"No simulation rule exists for '{action.tool}' in the web application demo.")
        target_id, field, pname, rule = PORT_TOOLS[action.tool]
        if action.target_object_id != target_id:
            raise AdapterError("invalid_target", f"{action.tool} must target '{target_id}', not '{action.target_object_id}'.")
        if set(action.parameters) != {pname} or not isinstance(action.parameters.get(pname), int) or isinstance(action.parameters.get(pname), bool):
            raise AdapterError("invalid_parameters", f"{action.tool} needs exactly {{{pname}: int}}.")
        port = action.parameters[pname]
        if not 1024 <= port <= 65535:
            raise AdapterError("invalid_port", f"Port {port} is outside 1024–65535 (rule W4).")
        if port == state.objects["web-server"].state["listen_port"]:
            raise AdapterError("port_conflict", f"Port {port} is already used by the web server (rule W4).")
        obj = state.objects[target_id]
        before = obj.state[field]
        if before == port:
            raise AdapterError("no_change", f"{obj.name} already uses port {port}.")
        obj.state[field] = port
        return [Consequence(step=step, affected_object_id=target_id, relationship_to_target="target", before={field: before},
                            predicted_after={field: port}, description=f"{obj.name}: {field.replace('_', ' ')} {before} → {port}.",
                            type="direct", evidence_rule=rule, status="known_in_simulation")]

    def connected_effects(self, before: EnvState, after: EnvState, plan: Plan, step: int) -> list[Consequence]:
        out: list[Consequence] = []
        b_app, a_app = before.objects["python-app"].state, after.objects["python-app"].state
        ws_b, ws_a = before.objects["web-server"].state, after.objects["web-server"].state
        mon_b, mon_a = before.objects["health-monitor"].state, after.objects["health-monitor"].state
        changed_ports = (b_app["listening_port"], ws_b["upstream_port"], mon_b["target_port"]) != (a_app["listening_port"], ws_a["upstream_port"], mon_a["target_port"])
        if not changed_ports:
            return out
        # web server forwarding (only when it was not itself the target of a change)
        if ws_a["upstream_port"] != a_app["listening_port"] and ws_b["upstream_port"] == ws_a["upstream_port"]:
            out.append(Consequence(step=step, affected_object_id="web-server", relationship_to_target="forwards_to target",
                                   before={"upstream_port": ws_b["upstream_port"], "matches_app_port": ws_b["upstream_port"] == b_app["listening_port"]},
                                   predicted_after={"upstream_port": ws_a["upstream_port"], "matches_app_port": False},
                                   description=f"Web server still forwards to port {ws_a['upstream_port']}, but the application listens on {a_app['listening_port']}: user requests may fail.",
                                   type="connected", evidence_rule=RULE_ACCESS, status="known_in_simulation", effect="warning"))
        # users / accessibility (derived state)
        acc_b, acc_a = accessible(before), accessible(after)
        after.objects["users"].state["can_reach_app"] = acc_a
        if acc_b != acc_a or acc_a:
            out.append(Consequence(
                step=step, affected_object_id="users", relationship_to_target="reach target via web server",
                before={"can_reach_app": acc_b}, predicted_after={"can_reach_app": acc_a},
                description=("Users can still reach the application through the web server (forwarding "
                             f"{ws_a['upstream_port']} → app on {a_app['listening_port']})." if acc_a else
                             "Users may no longer reach the application: the web server forwards to a port nothing listens on."),
                type="connected", evidence_rule=RULE_ACCESS, status="conditional", effect="benefit" if acc_a else "warning",
                assumptions=["Users reach the app only through the web server.", "No unknown network rule blocks the port."],
                observable={"can_reach_app": acc_a},
            ))
        # health monitor (derived state)
        h_b, h_a = healthy(before), healthy(after)
        after.objects["health-monitor"].state["status"] = "healthy" if h_a else "unhealthy"
        if mon_b["target_port"] == mon_a["target_port"] and not h_a:
            desc = f"Health monitor still checks port {mon_a['target_port']}; it may report the application as unhealthy and raise alerts."
        elif h_a:
            desc = f"Health monitor checks port {mon_a['target_port']}, where the application listens: the health check is predicted to pass."
        else:
            desc = f"Health monitor checks port {mon_a['target_port']} but the application listens on {a_app['listening_port']}: predicted unhealthy."
        out.append(Consequence(step=step, affected_object_id="health-monitor", relationship_to_target="checks target",
                               before={"target_port": mon_b["target_port"], "status": "healthy" if h_b else "unhealthy"},
                               predicted_after={"target_port": mon_a["target_port"], "status": "healthy" if h_a else "unhealthy"},
                               description=desc, type="connected", evidence_rule=RULE_HEALTH, status="known_in_simulation",
                               effect="benefit" if (h_a and not h_b) else ("neutral" if h_a else "warning"),
                               observable={"status": "healthy" if h_a else "unhealthy"}))
        # database: explicitly no predicted change
        db = after.objects["database"].state
        out.append(Consequence(step=step, affected_object_id="database", relationship_to_target="used by target",
                               before=dict(before.objects["database"].state), predicted_after=dict(db),
                               description="Database: no direct change predicted, based on the known configuration.",
                               type="connected", evidence_rule=RULE_DB, status="known_in_simulation"))
        return out

    # ------------------------------------------------------------------ evaluation
    def evaluate_criterion(self, c: GoalCriterion, p: EnvState) -> tuple[CheckStatus, str]:
        app = p.objects["python-app"].state
        if c.kind == "app_listens_on":
            ok = app["listening_port"] == c.params["port"]
            return (S.PASS if ok else S.FAIL), f"Application listens on {app['listening_port']} (goal: {c.params['port']})."
        if c.kind == "app_accessible":
            ok = accessible(p)
            ws = p.objects["web-server"].state
            return (S.PASS if ok else S.FAIL), (f"Users can reach the app (web server → {ws['upstream_port']}, app on {app['listening_port']})." if ok else
                                                f"Not accessible: web server forwards to {ws['upstream_port']}, app listens on {app['listening_port']}.")
        if c.kind == "data_preserved":
            return S.PASS, "Database state unchanged in the prediction; no data is deleted."
        return S.UNKNOWN, f"Unknown criterion kind '{c.kind}'."

    def rule_checks(self, plan: Plan, sim: SimulationResult, predicted: EnvState) -> list[tuple[CheckStatus, str]]:
        out: list[tuple[CheckStatus, str]] = [
            (S.PASS, "W1 No data is deleted: the database state is unchanged in the prediction."),
            (S.PASS, "W5 No service is stopped."),
        ]
        app = predicted.objects["python-app"].state["listening_port"]
        mism = []
        if predicted.objects["web-server"].state["upstream_port"] != app:
            mism.append(f"web server forwards to {predicted.objects['web-server'].state['upstream_port']}")
        if predicted.objects["health-monitor"].state["target_port"] != app:
            mism.append(f"health monitor checks {predicted.objects['health-monitor'].state['target_port']}")
        if mism:
            out.append((S.REVIEW_REQUIRED, f"FLAG · W3 Predicted port mismatch with the application (port {app}): {'; '.join(mism)}."))
        else:
            out.append((S.PASS, f"W3 Web server and health monitor both point at the application's port ({app})."))
        return out

    def measure(self, state: EnvState, object_id: str, key: str) -> Any:
        if key == "can_reach_app" or key == "test_request_reaches_app":
            return accessible(state)
        if object_id == "health-monitor" and key == "status":
            return "healthy" if healthy(state) else "unhealthy"
        raise KeyError(key)
