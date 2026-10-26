"""The transition-prediction interface every world model implements.

    predict(history, action, horizon_s) -> PredictedOutcome

``history`` is the observation history up to the decision time T (oldest first);
``action`` is an explicit :class:`ProposedAction` or None for "no action";
``horizon_s`` is how far ahead to predict. The result holds predicted state
changes, supported outcome interpretations (falls, collides...), the assumptions
and unknowns behind them, kept-apart uncertainty, and the backend's provenance.

Backends: the deterministic tabletop simulator (implemented), PyBullet and
V-JEPA 2-AC (interfaces only - they raise :class:`BackendUnavailable`, they never
fall back to another backend or fabricate a prediction).
"""

from __future__ import annotations

from typing import Protocol, Sequence

from splm.meaning import BackendInfo, PredictedOutcome, ProposedAction, SceneState
from splm.meaning.adapters import BackendUnavailable

__all__ = ["BackendUnavailable", "FutureLeakage", "TransitionPredictor", "check_no_leakage"]


class FutureLeakage(ValueError):
    """A prediction for time T was given information from after T."""


class TransitionPredictor(Protocol):
    info: BackendInfo

    def predict(
        self, history: Sequence[SceneState], action: ProposedAction | None, horizon_s: float
    ) -> PredictedOutcome: ...


def check_no_leakage(history: Sequence[SceneState], action: ProposedAction | None) -> None:
    """Refuse states from after the decision time. Later frames are for evaluation only."""
    if not history:
        raise ValueError("a prediction needs at least one scene state")
    times = [s.timestamp_s for s in history if s.timestamp_s is not None]
    if times != sorted(times):
        raise ValueError("history must be in time order")
    decision = action.issued_at_s if action is not None else None
    if decision is not None and times and times[-1] > decision:
        raise FutureLeakage(
            f"history contains a state at t={times[-1]}s, after the decision time t={decision}s"
        )
