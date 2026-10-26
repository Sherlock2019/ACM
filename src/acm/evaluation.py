"""Prediction versus actual outcome.

An :class:`Episode` records the whole chain with enough provenance to rerun it:

    initial evidence -> MLM meaning (as known at T) -> proposed action
        -> predicted outcome -> actual action -> later observations -> comparison

:func:`compare_outcome` scores a prediction against a later observed state where
the ground truth supports it: support state, fall events (precision/recall),
position error in metres (calibrated positions only), and abstention - a
prediction that says "unknown" is scored as an abstention, not as an error or a
hit. Episodes are stored per split (train / dev / eval) and never mixed; storing
episodes does not by itself improve anything.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from splm.meaning import (
    BackendInfo,
    EvidenceReference,
    MeaningDocument,
    MeaningEvent,
    OutcomeComparison,
    PredictedOutcome,
    ProposedAction,
    SceneState,
    StateChange,
)
from splm.meaning.geometry import CoordinateFrame

SUPPORT_RELATIONS = {"on": True, "not_on": False}


class Episode(BaseModel):
    id: str
    split: Literal["train", "dev", "eval"]
    inputs: list[EvidenceReference]
    extraction_config: dict[str, Any] = Field(default_factory=dict)
    backends: list[BackendInfo] = Field(default_factory=list)
    decision_time_s: float | None
    horizon_s: float
    meaning_at_decision: MeaningDocument
    proposed_action: ProposedAction | None
    prediction: PredictedOutcome
    actual_action: MeaningEvent | None = Field(default=None, description="What was observed to be done, if anything")
    subsequent: list[SceneState] = Field(default_factory=list)
    comparison: OutcomeComparison | None = None
    notes: list[str] = Field(default_factory=list)


def _support(state: SceneState, entity_id: str) -> bool | None:
    for obs in state.observations:
        if obs.subject == entity_id and obs.relation in SUPPORT_RELATIONS:
            return SUPPORT_RELATIONS[obs.relation]
    return None


def _xy(state: SceneState, entity_id: str) -> tuple[float, float] | None:
    try:
        point = state.entity(entity_id).geometry.position
    except KeyError:
        return None
    if point is None or point.frame != CoordinateFrame.WORLD:
        return None
    x, y, _ = point.in_metres()
    return x, y


def compare_outcome(
    prediction: PredictedOutcome, initial: SceneState, observed: SceneState
) -> OutcomeComparison:
    if prediction.final_state is None:
        raise ValueError("the prediction has no final state to compare")
    predicted_state = prediction.final_state
    movable = [e.id for e in initial.entities if _support(initial, e.id) is not None]
    predicted_falls = {e.entity_id for e in prediction.events if e.kind == "falls"}

    predicted_changes: list[StateChange] = []
    observed_changes: list[StateChange] = []
    support_hits, support_total = 0, 0
    tp = fp = fn = 0
    errors: list[float] = []
    abstentions, correct_abstentions = 0, 0
    per_entity: dict[str, Any] = {}

    for entity_id in movable:
        before = _support(initial, entity_id)
        predicted = _support(predicted_state, entity_id)
        actual = _support(observed, entity_id)
        observed_fell = before is True and actual is False
        if predicted != before:
            predicted_changes.append(StateChange(entity_id=entity_id, property="supported", before=before, after=predicted))
        if actual is not None and actual != before:
            observed_changes.append(StateChange(entity_id=entity_id, property="supported", before=before,
                                                after=actual, status="observed"))
        if actual is not None and predicted is not None:
            support_total += 1
            support_hits += int(actual == predicted)
        fell = entity_id in predicted_falls
        tp += int(fell and observed_fell)
        fp += int(fell and not observed_fell)
        fn += int(not fell and observed_fell)

        p_xy, o_xy = _xy(predicted_state, entity_id), _xy(observed, entity_id)
        entry: dict[str, Any] = {"predicted_supported": predicted, "observed_supported": actual}
        if p_xy is not None and o_xy is not None:
            error = math.hypot(p_xy[0] - o_xy[0], p_xy[1] - o_xy[1])
            errors.append(error)
            entry["position_error_m"] = round(error, 4)
        elif p_xy is None and predicted is False:
            abstentions += 1
            correct_abstentions += int(o_xy is None)  # the observation cannot place it either
            entry["position"] = "abstained (landing position unknown)"
        per_entity[entity_id] = entry

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 4) if b else None

    metrics = {
        "support_state_accuracy": ratio(support_hits, support_total),
        "fall_events": {"tp": tp, "fp": fp, "fn": fn, "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn)},
        "position_error_m": {"mean": round(sum(errors) / len(errors), 4) if errors else None,
                             "max": round(max(errors), 4) if errors else None, "n": len(errors), "unit": "m"},
        "abstentions": {"count": abstentions, "consistent_with_observation": correct_abstentions},
        "per_entity": per_entity,
    }
    return OutcomeComparison(
        action_id=prediction.action_id, predicted=predicted_changes, observed=observed_changes, metrics=metrics,
        notes=[
            "Scores compare one prediction with one later observation; they are not an accuracy estimate.",
            f"Observed state at t={observed.timestamp_s}s; prediction horizon {prediction.horizon_s}s.",
        ],
    )


class EpisodeStore:
    """Episodes as JSON lines, one file per split. Splits are never mixed."""

    def __init__(self, directory: Path | str) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def add(self, episode: Episode) -> Path:
        path = self.dir / f"{episode.split}.jsonl"
        if any(e.id == episode.id for split in ("train", "dev", "eval") for e in self.load(split)):
            raise ValueError(f"episode {episode.id!r} already stored; ids are unique across splits")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(episode.model_dump_json() + "\n")
        return path

    def load(self, split: Literal["train", "dev", "eval"]) -> list[Episode]:
        path = self.dir / f"{split}.jsonl"
        if not path.is_file():
            return []
        return [Episode.model_validate(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line]
