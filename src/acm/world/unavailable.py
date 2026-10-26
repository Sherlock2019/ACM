"""Backends that have an interface here but no working integration yet.

They exist so callers can name them and get a clear, honest failure - never a
silent fallback to another backend and never a fabricated prediction.
See docs/world_model_feasibility.md for what each would need.
"""

from __future__ import annotations

from typing import Sequence

from splm.meaning import BackendInfo, PredictedOutcome, ProposedAction, SceneState

from acm.world.interface import BackendUnavailable


class PyBulletSimulator:
    """Rigid-body physics (PyBullet). Planned after the deterministic baseline.

    Needs per object: mass (kg), friction coefficients, restitution, a collision
    shape and size (m); per action: force (N) or velocity (m/s) and duration (s);
    the table height (m). None of these are observable from a single image.
    """

    info = BackendInfo(name="pybullet", kind="simulator", live=False, config={"status": "not integrated"})

    def predict(self, history: Sequence[SceneState], action: ProposedAction | None, horizon_s: float) -> PredictedOutcome:
        try:
            import pybullet  # type: ignore  # noqa: F401
        except ImportError as exc:
            raise BackendUnavailable("PyBullet is not installed (pip install 'acm[physics]')") from exc
        raise BackendUnavailable(
            "the PyBullet backend is not integrated yet: physical parameters (mass, friction, force, "
            "table height) have no source in the scene schema. Use TabletopSimulator."
        )


class VJEPA2ACPredictor:
    """V-JEPA 2-AC (Meta) - research interface only.

    The model predicts *latent* frame representations conditioned on 7-D
    end-effector deltas of a Franka arm (position, extrinsic Euler orientation,
    gripper), from 256x256 video at 4 fps. It produces neither rendered future
    frames nor ACM facts; a decoder or probe from latents to scene states would be
    needed first. Not run or evaluated here.
    """

    info = BackendInfo(name="vjepa2-ac-vitg", kind="world_model", live=False, config={"status": "not integrated"})

    def predict(self, history: Sequence[SceneState], action: ProposedAction | None, horizon_s: float) -> PredictedOutcome:
        raise BackendUnavailable(
            "V-JEPA 2-AC is not integrated: it needs a GPU, the vjepa2-ac-vitg checkpoint, robot "
            "end-effector actions instead of object pushes, and a latent-to-state probe. "
            "See docs/world_model_feasibility.md."
        )
