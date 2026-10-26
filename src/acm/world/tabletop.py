"""A constrained, deterministic tabletop simulator - not general physical understanding.

Scope: one table (a rectangular support boundary in a calibrated world frame),
round objects on it, and three actions:

    move  target to an explicit destination point (pick-and-place, kinematic)
    push  target along ``direction_deg`` by ``distance`` (kinematic slide)
    drop  a held target at its current position

Rules (declared, not learned):

* A pushed object slides in a straight line. If its footprint would touch
  another object's footprint, it stops at contact: ``collides``. How the hit
  object then moves is not modelled and is reported as unknown.
* An object whose footprint centre ends beyond the support boundary
  ``crosses_edge`` and ``falls``: its centre of mass is assumed at the footprint
  centre. Part of the footprint over the edge with the centre inside is
  ``overhangs_edge`` and the object stays supported.
* Where a fallen object lands is unknown. Whether it breaks or spills is unknown.

Nothing is assumed silently: every parameter not taken from the scene is an
:class:`Assumption`, and the force, friction, mass, material and heights the
rules do not use are listed as unknowns.
"""

from __future__ import annotations

import math
from typing import Sequence

from splm.meaning import (
    Assumption,
    BackendInfo,
    CoordinateFrame,
    Observation,
    OutcomeEvent,
    PredictedOutcome,
    ProposedAction,
    SceneEntity,
    SceneState,
    StateChange,
    Status,
    UncertaintyReport,
)
from splm.meaning.geometry import Point

from acm.world.interface import check_no_leakage

SUPPORT_CLASSES = frozenset({"table", "shelf", "counter", "desk"})
STATIC_CLASSES = SUPPORT_CLASSES | {"floor", "person", "pusher", "robot", "hand"}
FLOOR_ID = "floor_01"
VERSION = "1.0"


class SimulationError(ValueError):
    """The scene or action lacks what the constrained simulator needs."""


class TabletopSimulator:
    def __init__(self) -> None:
        self.info = BackendInfo(
            name="tabletop-kinematic", version=VERSION, kind="simulator", live=True,
            config={"model": "2D kinematic, centre-of-mass support rule, stop-at-contact collisions"},
        )

    # -- interface -------------------------------------------------------------

    def predict(
        self, history: Sequence[SceneState], action: ProposedAction | None, horizon_s: float = 2.0
    ) -> PredictedOutcome:
        check_no_leakage(history, action)
        state = history[-1].model_copy(deep=True)  # the input history is never modified
        table = self._table(state)
        extent = table.geometry.extent
        objects = {e.id: e for e in state.entities if e.cls not in STATIC_CLASSES}
        positions = {oid: self._position(e) for oid, e in objects.items()}
        radius = {oid: self._radius(e) for oid, e in objects.items()}

        assumptions = [
            Assumption(name="rigid bodies", reason="objects are not deformed by the action"),
            Assumption(name="centre of mass at footprint centre", reason="mass distribution is not observed"),
            Assumption(name="falls iff centre of mass beyond the support boundary",
                       reason="static support rule; tipping dynamics are not modelled"),
            Assumption(name="no rotation", reason="orientation is not modelled"),
            Assumption(name=f"{FLOOR_ID} lies below the table", value=FLOOR_ID,
                       reason="the floor is not in the scene; it is where a fallen object goes"),
        ]
        unknowns = ["applied force", "friction coefficients", "object masses", "materials",
                    "table height", "object contents"]
        events: list[OutcomeEvent] = []
        changes: list[StateChange] = []
        moved: dict[str, tuple[float, float]] = {}

        if action is not None:
            if action.target not in objects:
                raise SimulationError(f"{action.target!r} is not a movable object in the scene")
            start = positions[action.target]
            if action.predicate in {"push", "shove", "nudge"}:
                direction = self._param(action, "direction_deg", "deg")
                distance = self._param(action, "distance", "m")
                assumptions.append(Assumption(
                    name="push displacement", value=distance, unit="m",
                    reason="kinematic: the object slides exactly the requested distance (friction and force not modelled)",
                ))
                end, hit = self._sweep(action.target, start, direction, distance, positions, radius)
                if hit is not None:
                    events.append(OutcomeEvent(kind="collides", entity_id=action.target, other_id=hit,
                                               note="stopped at contact; the hit object's response is not modelled"))
                    unknowns.append(f"how {hit} moves after being hit")
                moved[action.target] = end
            elif action.predicate in {"move", "place", "reposition"}:
                if action.destination is None:
                    raise SimulationError("a move needs an explicit destination point")
                x, y, _ = self._world(action.destination, state)
                assumptions.append(Assumption(name="pick-and-place path is clear",
                                              reason="the path of a carried object is not checked"))
                moved[action.target] = (x, y)
            elif action.predicate == "drop":
                held = state.relation(action.target, "held_by")
                if held is None:
                    raise SimulationError(f"{action.target} is not held; nothing to drop")
                moved[action.target] = start
            else:
                raise SimulationError(f"the tabletop simulator does not model {action.predicate!r}")

        for oid, entity in objects.items():
            before = positions[oid]
            after = moved.get(oid, before)
            supported_before = self._inside(before, extent)
            supported_after = self._inside(after, extent)
            if after != before:
                changes.append(StateChange(entity_id=oid, property="position", before=list(before),
                                           after=[round(after[0], 4), round(after[1], 4)], unit="m"))
            if supported_before and not supported_after:
                events.append(OutcomeEvent(kind="crosses_edge", entity_id=oid))
                events.append(OutcomeEvent(kind="falls", entity_id=oid))
                changes += [
                    StateChange(entity_id=oid, property="supported_by", before=table.id, after=None),
                    StateChange(entity_id=oid, property="region", before=table.id, after=FLOOR_ID),
                    StateChange(entity_id=oid, property="landing_position", before=None, after=None,
                                status=Status.UNKNOWN),
                ]
                self._place(entity, None, state, on=False, table_id=table.id)
            else:
                if supported_after and self._overhangs(after, radius[oid], extent):
                    events.append(OutcomeEvent(kind="overhangs_edge", entity_id=oid,
                                               note="part of the footprint is over the edge; the centre is not"))
                if supported_after:
                    events.append(OutcomeEvent(kind="remains_supported", entity_id=oid))
                self._place(entity, after if after != before else None, state, on=supported_after, table_id=table.id)

        return PredictedOutcome(
            action_id=action.id if action else None,
            changes=changes,
            events=events,
            horizon_s=horizon_s,
            backend=self.info,
            assumptions=assumptions,
            unknowns=list(dict.fromkeys(unknowns)),
            uncertainty=UncertaintyReport(
                prediction="deterministic rule output; no probability is estimated",
                rule_applicability="valid only for rigid round objects on a flat rectangular support",
                simulation_assumptions=f"{len(assumptions)} declared assumptions (see list)",
            ),
            final_state=state.model_copy(update={"timestamp_s": None}),
        )

    # -- geometry ----------------------------------------------------------------

    @staticmethod
    def _table(state: SceneState) -> SceneEntity:
        tables = [e for e in state.entities if e.cls in SUPPORT_CLASSES and e.geometry.extent is not None]
        if len(tables) != 1:
            raise SimulationError(f"need exactly one support surface with a world extent, found {len(tables)}")
        if tables[0].geometry.extent.frame != CoordinateFrame.WORLD:
            raise SimulationError("the support boundary must be in the calibrated world frame")
        return tables[0]

    @staticmethod
    def _position(entity: SceneEntity) -> tuple[float, float]:
        point = entity.geometry.position
        if point is None or point.frame != CoordinateFrame.WORLD:
            raise SimulationError(f"{entity.id} has no calibrated world position; pixels are not metres")
        x, y, _ = point.in_metres()
        return x, y

    @staticmethod
    def _radius(entity: SceneEntity) -> float:
        if entity.geometry.footprint_radius is None:
            raise SimulationError(f"{entity.id} has no footprint radius")
        return entity.geometry.footprint_radius.metres

    @staticmethod
    def _world(point: Point, state: SceneState) -> tuple[float, float, float | None]:
        if point.frame != CoordinateFrame.WORLD or state.calibration is None or point.calibration_id != state.calibration.id:
            raise SimulationError("the destination must be a world point in the scene's calibration")
        return point.in_metres()

    @staticmethod
    def _param(action: ProposedAction, name: str, unit: str) -> float:
        q = action.parameters.get(name)
        if q is None:
            raise SimulationError(f"{action.predicate} needs parameter {name!r} ({unit}); it is not assumed")
        if q.unit != unit:
            if unit == "m" and q.unit in {"cm", "mm"}:
                return q.value * {"cm": 0.01, "mm": 0.001}[q.unit]
            raise SimulationError(f"parameter {name!r} must be in {unit}, got {q.unit}")
        return q.value

    @staticmethod
    def _inside(p: tuple[float, float], extent) -> bool:
        return extent.x_min <= p[0] <= extent.x_max and extent.y_min <= p[1] <= extent.y_max

    @staticmethod
    def _overhangs(p, r, extent) -> bool:
        return (p[0] - r < extent.x_min or p[0] + r > extent.x_max
                or p[1] - r < extent.y_min or p[1] + r > extent.y_max)

    @staticmethod
    def _sweep(target, start, direction_deg, distance, positions, radius):
        """Slide a disc; stop at the first contact with another disc."""
        dx, dy = math.cos(math.radians(direction_deg)), math.sin(math.radians(direction_deg))
        best, hit = distance, None
        for other, centre in positions.items():
            if other == target:
                continue
            reach = radius[target] + radius[other]
            fx, fy = start[0] - centre[0], start[1] - centre[1]
            b = fx * dx + fy * dy
            c = fx * fx + fy * fy - reach * reach
            disc = b * b - c
            if disc < 0:
                continue
            s = -b - math.sqrt(disc)
            if 0 <= s < best:
                best, hit = s, other
        return (round(start[0] + best * dx, 4), round(start[1] + best * dy, 4)), hit

    @staticmethod
    def _place(entity: SceneEntity, xy, state: SceneState, *, on: bool, table_id: str) -> None:
        if xy is not None and entity.geometry.position is not None:
            entity.geometry.position = entity.geometry.position.model_copy(update={"x": xy[0], "y": xy[1]})
        if not on:
            entity.geometry.position = None  # where it lands is unknown
        entity.status = Status.PREDICTED
        entity.evidence = []
        state.observations = [o for o in state.observations if o.subject != entity.id or o.relation is None]
        state.observations.append(Observation(
            subject=entity.id, relation="on" if on else "not_on", object=table_id, status=Status.PREDICTED,
            note="predicted by the tabletop simulator",
        ))
