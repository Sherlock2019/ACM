"""MLM meaning (from text, image or video) -> prediction -> ACM consequences.

    MeaningDocument --available_at(T)--> state at T + earlier events + goals
        + explicit ProposedAction
        -> TransitionPredictor (tabletop simulator) -> PredictedOutcome
        -> ACM: action frame (rules) + predicted changes (simulation, via
           packs/universal/simulation.yaml) + scene participants + unknowns
        -> ConsequenceReport per alternative, all from the same initial state

Nothing is rendered to prose and re-parsed: frames come from
:mod:`splm.meaning.frames`, scene facts go in as structured ExternalFacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from splm.meaning import MeaningDocument, PredictedOutcome, ProposedAction, SceneState
from splm.meaning.frames import action_to_frame, event_to_frame

from acm.engine import ConsequenceEngine
from acm.schema import (
    ConsequenceReport,
    ExternalFact,
    Intention,
    Participant,
    StateFact,
    UnknownConsequence,
)
from acm.world import FLOOR_ID, TabletopSimulator, TransitionPredictor


@dataclass
class ScenarioResult:
    key: str
    action: ProposedAction | None
    outcome: PredictedOutcome
    report: ConsequenceReport
    decision_time_s: float | None
    context: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "decision_time_s": self.decision_time_s,
            "action": self.action.model_dump(mode="json") if self.action else None,
            "outcome": self.outcome.model_dump(mode="json"),
            "report": self.report.model_dump(mode="json"),
            "context": self.context,
        }


class MultimodalBridge:
    def __init__(self, engine: ConsequenceEngine | None = None, predictor: TransitionPredictor | None = None) -> None:
        self.engine = engine or ConsequenceEngine()
        self.predictor = predictor or TabletopSimulator()
        sim = self.engine.packs.simulation
        self._properties = sim.get("properties", {})
        self._events = sim.get("events", {})
        self._unknown = sim.get("unknown", {})
        scene = sim.get("scene", {})
        self._place_classes = set(scene.get("place_classes", []))
        self._animate_classes = set(scene.get("animate_classes", []))

    # -- entry points -----------------------------------------------------------

    def compare(
        self,
        doc: MeaningDocument,
        actions: dict[str, ProposedAction | None],
        *,
        at_time: float | None = None,
        horizon_s: float = 2.0,
    ) -> dict[str, ScenarioResult]:
        """Every alternative from the same state at T (the state itself is never modified)."""
        return {key: self.consequences(doc, action, key=key, at_time=at_time, horizon_s=horizon_s)
                for key, action in actions.items()}

    def consequences(
        self,
        doc: MeaningDocument,
        action: ProposedAction | None,
        *,
        key: str = "action",
        at_time: float | None = None,
        horizon_s: float = 2.0,
    ) -> ScenarioResult:
        view = doc.available_at(at_time) if at_time is not None else doc
        state = view.state_at(at_time)
        history = [s for s in view.states if s.timestamp_s is None or at_time is None or s.timestamp_s <= at_time] or [state]
        if action is not None and at_time is not None and action.issued_at_s is None:
            action = action.model_copy(update={"issued_at_s": at_time})
        outcome = self.predictor.predict(history, action, horizon_s)

        context_frames = [g.frame for g in view.goals if g.frame is not None]
        context_frames += [event_to_frame(e, state) for e in view.events]
        context = [f.text for f in context_frames]
        if action is None:
            report = ConsequenceReport(
                action_text="(no action)", language="en", realized=True,
                notes=["No action is taken: no rule applies, and the simulator predicts no change."],
            )
            return ScenarioResult(key, None, outcome, report, at_time, context)

        frames = [*context_frames, action_to_frame(action, state)]
        report = self.engine.predict(
            frames,
            language="en",
            external_facts=self._external_facts(outcome, state),
            participants=self._participants(state, outcome),
            goals=self._supplied_goals(view),
            unknowns=self._unknowns(outcome, state),
        )
        report.notes.append(
            f"Predicted changes come from {outcome.backend.name}@{outcome.backend.version} "
            "(a constrained simulator, not general physical understanding)."
        )
        report.notes.append("ACM certainty scores are rule weights, not calibrated real-world probabilities.")
        return ScenarioResult(key, action, outcome, report, at_time, context)

    # -- mapping ---------------------------------------------------------------------

    def _label(self, entity_id: str | None, state: SceneState) -> str:
        if entity_id is None:
            return "?"
        try:
            return state.entity(entity_id).display
        except KeyError:
            return entity_id

    def _external_facts(self, outcome: PredictedOutcome, state: SceneState) -> list[ExternalFact]:
        source = f"simulator:{outcome.backend.name}@{outcome.backend.version}"
        evidence = [f"assumption: {a.name}" for a in outcome.assumptions]
        out: list[ExternalFact] = []
        for change in outcome.changes:
            spec = self._properties.get(change.property)
            if spec is None:
                continue
            for value, truth in ((change.before, False), (change.after, True)):
                if value is None:
                    continue
                bound = {"entity": change.entity_id, "value": str(value)}
                args = [bound[a] for a in spec["args"]]
                out.append(ExternalFact(
                    fact=StateFact(state=spec["state"], args=args, labels=[self._label(a, state) for a in args], value=truth),
                    basis="simulation", source=source, evidence=evidence,
                ))
        for event in outcome.events:
            for spec in self._events.get(event.kind, []):
                bound = {"entity": event.entity_id, "other": event.other_id}
                args = [bound[a] for a in spec["args"]]
                out.append(ExternalFact(
                    fact=StateFact(state=spec["state"], args=args, labels=[self._label(a, state) for a in args]),
                    basis="simulation", source=source, evidence=evidence,
                ))
        return out

    def _participants(self, state: SceneState, outcome: PredictedOutcome) -> list[Participant]:
        out = [
            Participant(key=e.id, label=e.display, place=e.cls in self._place_classes,
                        animate=e.cls in self._animate_classes or e.id == "self")
            for e in state.entities
        ]
        if any(c.after == FLOOR_ID for c in outcome.changes):
            out.append(Participant(key=FLOOR_ID, label=f"{FLOOR_ID} (assumed)", place=True))
        return out

    def _unknowns(self, outcome: PredictedOutcome, state: SceneState) -> list[UnknownConsequence]:
        out = []
        for event in outcome.events:
            for spec in self._unknown.get(event.kind, []):
                about = event.other_id if spec["aspect"].startswith("response") and event.other_id else event.entity_id
                out.append(UnknownConsequence(about=about, about_label=self._label(about, state),
                                              aspect=spec["aspect"], text=spec["text"], needs=list(spec.get("needs", []))))
        return out

    def _supplied_goals(self, doc: MeaningDocument) -> list[Intention]:
        """Supplied goals with explicit desired states ("keep red_cup_01 on table_01")."""
        out = []
        state = doc.states[-1] if doc.states else None
        for goal in doc.goals:
            if goal.frame is not None or not goal.desired:
                continue  # stated goals with frames are read by ACM from the frame itself
            facts = []
            for desired in goal.desired:
                spec = self._properties.get(desired.property)
                if spec is None:
                    continue
                bound = {"entity": desired.entity_id, "value": str(desired.value)}
                args = [bound[a] for a in spec["args"]]
                facts.append(StateFact(state=spec["state"], args=args,
                                       labels=[self._label(a, state) if state else a for a in args]))
            out.append(Intention(kind="goal", owner=goal.owner, owner_label=goal.owner, text=goal.text,
                                 outcome=facts, sentence_index=0))
        return out
