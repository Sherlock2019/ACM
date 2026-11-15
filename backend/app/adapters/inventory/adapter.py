"""Inventory demo adapter: warehouses, inventory records, orders, a dashboard.

All inventory-specific behavior lives here (moved out of the generic core): reservation rules,
order status, dashboard refresh, shortage analysis, goal parsing and success criteria.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ...domain.models import (
    Action, CheckStatus, Consequence, EnvObject, Evidence, GoalCriterion, GoalSpec, PermissionClass, Plan,
    Relationship, SimulationResult,
)
from ...engine.environment import EnvState
from ..base import AdapterError, EnvironmentAdapter

S = CheckStatus
RULE_RESERVE = "INV-1 reserve_stock: inventory.reserved += q; inventory.available -= q"
RULE_ORDER = "INV-2 order.reserved_quantity += q; status = 'reserved' when reserved_quantity >= quantity_required"
RULE_DASHBOARD = "INV-3 dashboard displays inventory.available; updates immediately (configured behavior)"
RULE_RESERVATION = "INV-4 a reservation record is created and affects the inventory record's availability"
RULE_OTHER_ORDERS = "INV-5 other pending orders: eligible stock = sum(available) over their eligible inventory records"
_ORDER = r"order\s+([a-z0-9]+)"
_UNSUPPORTED = {
    "delete": "Deleting orders is prohibited (rule I1).",
    "cancel": "Cancelling orders is not a supported action in this demo.",
    "ship": "'Fulfilled' here means fully reserved. Shipping is not modeled.",
    "deliver": "'Fulfilled' here means fully reserved. Delivery is not modeled.",
    "restock": "Replenishing stock is not a supported action in this demo.",
    "transfer": "Moving stock between warehouses is not modeled.",
    "edit": "Directly editing inventory or order status is prohibited (rule I2).",
    "set": "Directly setting inventory or order status is prohibited (rule I2).",
    "ignore": "Goals cannot change or switch off AFM's rules (R10).",
    "rules": "Goals cannot change AFM's rules; that is a separate human-controlled operation (R10).",
}
_OTHER_DOMAIN = r"\b(port|server|proxy|config|endpoint|object a|processor|display)\b"


class ReserveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    quantity: int


def eligible_available(state: EnvState, order: EnvObject) -> int:
    return sum(state.objects[i].state["available"] for i in order.state.get("eligible_inventory_ids", []) if i in state.objects)


def remaining_need(order: EnvObject) -> int:
    return max(0, order.state["quantity_required"] - order.state["reserved_quantity"])


def _inv_view(o: EnvObject) -> dict:
    return {k: o.state[k] for k in ("on_hand", "reserved", "available")}


class InventoryAdapter(EnvironmentAdapter):
    environment_id = "warehouse-demo"
    name = "Inventory Assistant"
    adapter_name = "InventorySimulationAdapter"
    summary = "Explore consequences in a supply-chain scenario: two warehouses, two competing orders, one dashboard."
    scenario_path = Path(__file__).with_name("scenario.json")
    error_rules = {
        "insufficient_inventory": "I3 Do not reserve more stock than is available.",
        "invalid_quantity": "I2 Do not falsify inventory: a zero or negative reservation is not a real allocation.",
        "exceeds_order_need": "I2 Do not falsify order status: reserving more than the order needs over-allocates.",
        "ineligible_inventory": "Scenario constraint: the order cannot be served from this warehouse.",
        "product_mismatch": "Scenario constraint: the inventory holds a different product.",
    }

    # ------------------------------------------------------------------ goals
    def _order_by_label(self, state: EnvState, label: str) -> str | None:
        return next((o.id for o in state.objects.values() if o.type == "customer_order" and o.name.lower() == f"order {label.lower()}"), None)

    def interpret_goal(self, text: str, state: EnvState) -> GoalSpec:
        t = " ".join(text.strip().split())
        low = t.lower()
        if not t:
            return self.unsupported(t, "The goal is empty.")
        if re.search(_OTHER_DOMAIN, low) and "order" not in low:
            return self.unsupported(t, "This goal does not fit the Inventory Assistant: this environment has warehouses, inventory and orders only. Select the matching playground instead.")
        for verb, why in _UNSUPPORTED.items():
            if re.search(rf"\b{verb}\b", low):
                return self.unsupported(t, f"This demo cannot evaluate that goal. {why}")
        m = re.search(rf"\b(?:fulfil|fulfill|reserve(?:\s+stock)?\s+for|serve)\w*\s+{_ORDER}", low)
        if not m:
            return self.unsupported(t, "AFM could not map this goal to supported success criteria. This environment understands goals about reserving stock for a known order.")
        target = self._order_by_label(state, m.group(1))
        if not target:
            return self.unsupported(t, f"'Order {m.group(1).upper()}' is not in the known environment.")
        protect: list[str] = []
        for pm in re.finditer(rf"(?:avoid\w*|prevent\w*|without)\s+(?:a\s+|any\s+)?shortages?\s+(?:for|of|on)\s+{_ORDER}|protect\w*\s+{_ORDER}", low[m.end():]):
            label = pm.group(1) or pm.group(2)
            oid = self._order_by_label(state, label)
            if not oid:
                return self.unsupported(t, f"'Order {label.upper()}' is not in the known environment.")
            if oid != target and oid not in protect:
                protect.append(oid)
        tname = state.objects[target].name
        crit = [GoalCriterion(id="c1", kind="order_fully_reserved", params={"order_id": target},
                              description=f"{tname} is fully reserved (reserved_quantity ≥ quantity_required).")]
        crit += [GoalCriterion(id=f"c{i + 2}", kind="no_shortage", params={"order_id": p},
                               description=f"{state.objects[p].name} keeps eligible available stock ≥ its remaining need.")
                 for i, p in enumerate(protect)]
        others = [o.name for o in state.objects.values() if o.type == "customer_order" and o.id != target]
        return GoalSpec(
            goal_id=self.goal_id(t), environment_id=self.environment_id, text=t, supported=True,
            intent="reserve_for_order", parameters={"order_id": target, "protect": protect}, success_criteria=crit,
            explanation="Mapped to structured criteria. 'Fulfilled' in this demo means the required stock is successfully reserved, not shipped or delivered.",
            intended_benefits=[f"{tname} gets the stock it needs allocated."],
            potential_negative_effects=[f"Stock taken from a shared warehouse may leave {', '.join(others) or 'other orders'} short.",
                                        "Displays and possible external syncs reading inventory will change."],
            missing_information=["Customer deadlines and priorities are not provided.",
                                 "Replenishment schedules are unknown.",
                                 "Whether an external ERP sync reads these records is not verified."],
        )

    def propose_plans(self, goal: GoalSpec, state: EnvState) -> list[Plan]:
        order = state.objects[goal.parameters["order_id"]]
        need = remaining_need(order)
        if need == 0:
            return []
        plans = []
        for i, inv_id in enumerate(order.state["eligible_inventory_ids"], start=1):
            inv = state.objects.get(inv_id)
            if inv is None:
                continue
            wh = state.objects.get(inv.state["warehouse_id"])
            whn = wh.name if wh else inv.state["warehouse_id"]
            plans.append(Plan(
                plan_id=f"P{i}", goal_id=goal.goal_id, title=f"Reserve {need} from {whn}",
                actions=[Action(
                    action_id=f"P{i}-a1", tool="reserve_stock", operation="reserve", target_object_id=inv_id,
                    parameters={"order_id": order.id, "quantity": need},
                    expected_preconditions=[f"{inv.name} has at least {need} available (now {inv.state['available']}).",
                                            f"{order.name} is pending and eligible for {whn}.",
                                            "The environment has not changed since this prediction."],
                    permission=PermissionClass.requires_approval,
                    purpose=f"Allocate {need} unit(s) of {inv.name} to {order.name}.",
                )],
                assumptions=["Inventory numbers in the catalog are the current simulated truth.",
                             "No other reservation happens between prediction and execution (checked at execution)."],
                known_limitations=["Shipping, picking and delivery are not modeled.", "Only dependencies in the known catalog are simulated."],
            ))
        return plans

    # ------------------------------------------------------------------ simulation
    def simulate_action(self, action: Action, state: EnvState, step: int) -> list[Consequence]:
        if action.tool != "reserve_stock":
            raise AdapterError("unsupported_action", f"No simulation rule exists for '{action.tool}' in the Inventory Assistant.")
        try:
            p = ReserveParams.model_validate(action.parameters)
        except ValidationError as e:
            fields = ", ".join(".".join(str(x) for x in err["loc"]) or "parameters" for err in e.errors())
            raise AdapterError("invalid_parameters", f"reserve_stock needs exactly {{order_id: str, quantity: int}}; problem with: {fields}.")
        inv = state.objects.get(action.target_object_id)
        if inv is None:
            raise AdapterError("missing_object", f"Target object '{action.target_object_id}' does not exist in the known environment.")
        if inv.type != "inventory_record":
            raise AdapterError("invalid_target", f"'{inv.name}' is a {inv.type}, not an inventory record.")
        order = state.objects.get(p.order_id)
        if order is None or order.type != "customer_order":
            raise AdapterError("missing_object", f"Order '{p.order_id}' does not exist in the known environment.")
        if p.quantity <= 0:
            raise AdapterError("invalid_quantity", f"Quantity must be a positive whole number; got {p.quantity}.")
        if order.state["product_id"] != inv.state["product_id"]:
            raise AdapterError("product_mismatch", f"{order.name} needs {order.state['product_id']}, but {inv.name} holds {inv.state['product_id']}.")
        if inv.id not in order.state["eligible_inventory_ids"]:
            raise AdapterError("ineligible_inventory", f"{order.name} cannot be fulfilled from {inv.name} in this scenario.")
        if p.quantity > inv.state["available"]:
            raise AdapterError("insufficient_inventory", f"Cannot reserve {p.quantity}: only {inv.state['available']} available in {inv.name} (rule I3).")
        need = remaining_need(order)
        if p.quantity > need:
            raise AdapterError("exceeds_order_need", f"{order.name} needs only {need} more unit(s); reserving {p.quantity} would over-allocate.")

        out: list[Consequence] = []
        before_state = state.copy()
        inv_before = _inv_view(inv)
        inv.state["reserved"] += p.quantity
        inv.state["available"] -= p.quantity
        out.append(Consequence(step=step, affected_object_id=inv.id, relationship_to_target="target", before=inv_before,
                               predicted_after=_inv_view(inv), description=f"{inv.name} availability: {inv_before['available']} → {inv.state['available']}.",
                               type="direct", evidence_rule=RULE_RESERVE, status="known_in_simulation"))

        res_id = f"res-{len([o for o in state.objects.values() if o.type == 'reservation']) + 1}"
        res = EnvObject(id=res_id, type="reservation", name=f"Reservation {res_id[4:]} ({order.name})",
                        purpose=f"Allocates {p.quantity} unit(s) from {inv.name} to {order.name}.",
                        state={"order_id": order.id, "inventory_id": inv.id, "quantity": p.quantity},
                        behavior="Reduces the inventory record's available quantity.", evidence=Evidence.observed,
                        known_unknowns=["Picking, shipping and delivery are outside this demo."])
        state.objects[res_id] = res
        state.relationships.append(Relationship(id=f"rel-{res_id}", source=res_id, target=inv.id, type="affects",
                                                description=f"Reservation allocates {p.quantity} unit(s) of this record.", evidence=Evidence.observed))
        out.append(Consequence(step=step, affected_object_id=res_id, relationship_to_target="affects target", before={},
                               predicted_after=dict(res.state), description=f"A reservation of {p.quantity} unit(s) for {order.name} is recorded.",
                               type="direct", evidence_rule=RULE_RESERVATION, status="known_in_simulation"))

        o_before = {"reserved_quantity": order.state["reserved_quantity"], "status": order.state["status"]}
        order.state["reserved_quantity"] += p.quantity
        order.state["reservations"] = [*order.state["reservations"], res_id]
        if order.state["reserved_quantity"] >= order.state["quantity_required"]:
            order.state["status"] = "reserved"
        o_after = {"reserved_quantity": order.state["reserved_quantity"], "status": order.state["status"]}
        full = o_after["status"] == "reserved"
        out.append(Consequence(step=step, affected_object_id=order.id, relationship_to_target="depends_on target", before=o_before,
                               predicted_after=o_after,
                               description=f"{order.name} {'gets its full required reservation' if full else 'is only partly reserved'} ({o_after['reserved_quantity']}/{order.state['quantity_required']}). Reserved ≠ shipped.",
                               type="connected", evidence_rule=RULE_ORDER, status="known_in_simulation", effect="benefit" if full else "neutral"))

        for rel in state.relationships:
            if rel.target == inv.id and rel.type == "displays":
                dash = state.objects[rel.source]
                shown = dash.state["available_by_inventory"]
                d_before = {inv.id: shown.get(inv.id)}
                shown[inv.id] = inv.state["available"]
                out.append(Consequence(step=step, affected_object_id=dash.id, relationship_to_target="displays target", before=d_before,
                                       predicted_after={inv.id: shown[inv.id]}, description=f"{dash.name} shows {inv.name} availability as {shown[inv.id]}.",
                                       type="connected", evidence_rule=RULE_DASHBOARD, status="known_in_simulation",
                                       assumptions=["The immediate refresh is a configured simulator behavior, not an observed real dashboard."]))

        for other in state.objects.values():
            if other.type != "customer_order" or other.id == order.id or remaining_need(other) == 0:
                continue
            if other.state["product_id"] != inv.state["product_id"]:
                continue
            need_o = remaining_need(other)
            eb = eligible_available(before_state, before_state.objects[other.id])
            ea = eligible_available(state, other)
            depends = inv.id in other.state["eligible_inventory_ids"]
            short = ea < need_o
            if depends and short:
                where = "its only eligible warehouse" if len(other.state["eligible_inventory_ids"]) == 1 else "its eligible warehouses"
                desc = f"Potential shortage for {other.name}: it needs {need_o} and only {ea} would remain in {where}."
            elif depends:
                desc = f"{other.name} still has sufficient eligible stock ({ea} available for {need_o} needed)."
            elif not short:
                desc = f"{other.name} does not depend on {inv.name}; its eligible stock stays at {ea} for {need_o} needed (sufficient)."
            else:
                desc = f"{other.name} does not depend on {inv.name}, but its eligible stock ({ea}) is already below its need ({need_o})."
            out.append(Consequence(
                step=step, affected_object_id=other.id,
                relationship_to_target="depends_on target" if depends else "same product, not connected to target",
                before={"eligible_available": eb, "remaining_need": need_o, "sufficient": eb >= need_o},
                predicted_after={"eligible_available": ea, "remaining_need": need_o, "sufficient": not short},
                description=desc, type="connected", evidence_rule=RULE_OTHER_ORDERS,
                assumptions=[f"No replenishment, cancellation or other reservation happens before {other.name} is served.",
                             f"{other.name}'s eligible warehouses stay as configured."],
                status="conditional", effect="warning" if (depends and short) else "neutral",
                observable={"eligible_available": ea},
            ))
        return out

    # ------------------------------------------------------------------ evaluation
    def evaluate_criterion(self, c: GoalCriterion, predicted: EnvState) -> tuple[CheckStatus, str]:
        o = predicted.objects.get(c.params.get("order_id", ""))
        if o is None:
            return S.UNKNOWN, f"{c.params.get('order_id')} is not in the known environment."
        if c.kind == "order_fully_reserved":
            ok = o.state["reserved_quantity"] >= o.state["quantity_required"]
            return (S.PASS if ok else S.FAIL), f"{o.name} reserved {o.state['reserved_quantity']}/{o.state['quantity_required']} (fulfilled = fully reserved)."
        if c.kind == "no_shortage":
            need, ea = remaining_need(o), eligible_available(predicted, o)
            return (S.PASS if ea >= need else S.FAIL), f"{o.name} keeps {ea} eligible unit(s) for {need} needed ({'no shortage' if ea >= need else f'short by {need - ea}'})."
        return S.UNKNOWN, f"Unknown criterion kind '{c.kind}'."

    def rule_checks(self, plan: Plan, sim: SimulationResult, predicted: EnvState) -> list[tuple[CheckStatus, str]]:
        others = {c.affected_object_id for c in sim.consequences if c.evidence_rule.startswith("INV-5")}
        return [
            (S.PASS, "I1 No order is deleted."),
            (S.PASS, "I2 Inventory and order status change only through reserve_stock (available = on_hand − reserved)."),
            (S.PASS, "I3 Every reservation is within the available stock."),
            (S.PASS, f"I4 Impacts on {len(others)} other known order(s) were computed and are shown."),
        ]

    def measure(self, state: EnvState, object_id: str, key: str) -> Any:
        o = state.objects[object_id]
        if key == "eligible_available":
            return eligible_available(state, o)
        raise KeyError(key)
