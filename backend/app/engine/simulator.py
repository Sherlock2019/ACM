"""Generic consequence simulator. Knows nothing about any domain.

1. Copy the environment snapshot.
2. For each action: check the tool exists and is not prohibited, then ask the ADAPTER to apply it to the copy.
3. Ask the adapter for effects on the final state (connected effects).
4. Report relationships with unknown evidence touching changed objects as UNKNOWN (never simulated).
The original state is never touched.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain.models import Consequence, Evidence, PermissionClass, Plan, SimulationError, SimulationResult, ToolSpec, now_iso
from ..domain.profile import load_profile
from .environment import EnvState

if TYPE_CHECKING:
    from ..adapters.base import EnvironmentAdapter

RULE_UNKNOWN = "CORE-1 relationships with unknown evidence are reported, not simulated"


def tool_index(adapter: "EnvironmentAdapter", blocked: frozenset[str] = frozenset()) -> dict[str, ToolSpec]:
    """Generic + environment tools. `blocked` (from use-case rules) can only NARROW permissions."""
    idx = {t.name: t for t in load_profile().tools}
    idx.update({t.name: t for t in adapter.tools()})
    for name in blocked:
        if name in idx:
            idx[name] = idx[name].model_copy(update={"permission": PermissionClass.prohibited, "executable": False,
                                                      "description": idx[name].description + " (blocked by a use-case rule)"})
    return idx


def simulate(adapter: "EnvironmentAdapter", state: EnvState, plan: Plan, version: int, fingerprint: str,
             blocked: frozenset[str] = frozenset()) -> tuple[SimulationResult, EnvState]:
    from ..adapters.base import AdapterError

    tools = tool_index(adapter, blocked)
    work = state.copy()
    consequences: list[Consequence] = []
    errors: list[SimulationError] = []
    for step, action in enumerate(plan.actions, start=1):
        spec = tools.get(action.tool)
        try:
            if spec is None:
                raise AdapterError("unknown_action", f"Tool '{action.tool}' is not registered for {adapter.name}.")
            if spec.permission.value == "prohibited" or not spec.executable:
                raise AdapterError("prohibited_action", f"'{action.tool}' is prohibited and is not available for execution.")
            if action.operation != spec.operation:
                raise AdapterError("invalid_operation", f"'{action.tool}' supports operation '{spec.operation}', not '{action.operation}'.")
            if spec.scope == "generic":
                if action.target_object_id and action.target_object_id not in work.objects and action.tool == "inspect_object":
                    raise AdapterError("missing_object", f"Object '{action.target_object_id}' does not exist in the known environment.")
                continue  # generic read-only tools never change state
            if spec.modifies_state and not adapter.capabilities.get("simulate", False):
                raise AdapterError("simulation_unsupported", f"{adapter.name} cannot simulate '{action.tool}'.")
            before = work.fingerprint()
            consequences.extend(adapter.simulate_action(action, work, step))
            if not spec.modifies_state and work.fingerprint() != before:
                raise AdapterError("read_only_violation", f"Read-only tool '{action.tool}' changed state; adapter bug, plan rejected.")
        except AdapterError as e:
            errors.append(SimulationError(step=step, action_id=action.action_id, code=e.code, message=e.message))
            break

    feasible = not errors
    changed: dict[str, dict] = {}
    if feasible:
        consequences.extend(adapter.connected_effects(state, work, plan, len(plan.actions)))
        for oid, obj in work.objects.items():
            if oid not in state.objects or state.objects[oid].state != obj.state:
                changed[oid] = obj.state
        for rel in work.relationships:
            if rel.target in changed and rel.evidence == Evidence.unknown:
                src = work.objects.get(rel.source)
                tgt = work.objects.get(rel.target)
                consequences.append(Consequence(
                    step=len(plan.actions), affected_object_id=rel.source, relationship_to_target=f"{rel.type} {tgt.name if tgt else rel.target} (unverified)",
                    before={}, predicted_after={},
                    description=f"Unknown: whether {src.name if src else rel.source} {rel.type.replace('_', ' ')} {tgt.name if tgt else rel.target}. Not simulated.",
                    type="connected", evidence_rule=RULE_UNKNOWN, status="unknown",
                ))
    unknowns = [
        "Dependencies outside the known catalog are not known; this prediction cannot cover them.",
        *sorted({u for oid in changed if oid in work.objects for u in work.objects[oid].known_unknowns}),
    ]
    return SimulationResult(
        plan_id=plan.plan_id, environment_id=adapter.environment_id, environment_version=version, environment_fingerprint=fingerprint,
        simulated_at=now_iso(),
        applies_to=f"Immediately after step {len(plan.actions)} of the plan, against {adapter.name} version {version}. Not a forecast of later events.",
        feasible=feasible, consequences=consequences, errors=errors, predicted_objects=changed, unknowns=unknowns,
    ), work
