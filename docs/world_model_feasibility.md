# World-model feasibility: V-JEPA 2-AC behind ACM's transition interface

Status: **interface only - not integrated, not run, not evaluated.**
`acm.world.VJEPA2ACPredictor.predict()` raises `BackendUnavailable` and never falls
back to another backend.

Facts below were checked on 2026-10-26 against the official sources:
[facebookresearch/vjepa2](https://github.com/facebookresearch/vjepa2) and the paper
[arXiv:2506.09985](https://arxiv.org/abs/2506.09985) (HTML v1).

## The interface it would implement

```python
predict(history: Sequence[SceneState], action: ProposedAction | None, horizon_s: float) -> PredictedOutcome
```

The deterministic `TabletopSimulator` already implements it. A learned model has to
return the same thing: predicted state changes, supported outcome events (falls,
collides, ...), assumptions, unknowns, kept-apart uncertainty and backend provenance.

## What V-JEPA 2-AC is

| | From the official sources |
|---|---|
| Checkpoint | `vjepa2-ac-vitg.pt` (ViT-g/16 encoder + action-conditioned predictor), loaded with `torch.hub.load('facebookresearch/vjepa2', 'vjepa2_ac_vit_giant')` |
| Predictor | about 300M parameters, 24-layer transformer, block-causal attention |
| Visual input | 256×256 frames at 4 fps, about 4 s clips (16 frames); each frame becomes a 16×16×1408 feature map from the frozen encoder |
| Action | 7-D vector: **change** in end-effector state between frames - 3 Cartesian position, 3 extrinsic Euler orientation, 1 gripper - relative to the robot base |
| State | 7-D end-effector state, same layout |
| Training data | under 62 hours of unlabeled DROID robot video (Franka arm) |
| Planning | Cross-Entropy Method; energy = L1 distance between the predicted latent and a goal-image latent; 800 samples × 10 iterations; each action within an L1 ball of 0.075 (≈13 cm); receding horizon |
| Compute | about 16 s per planning step on one RTX 4090; the repository assumes a CUDA GPU |
| Output | **latent** representations of future frames - not pixels, not object states |
| Licence | code mostly MIT (three video utilities Apache-2.0); the repository does not state a separate weights licence - check before use |
| Stated limits | sensitive to camera position (no calibration, action axes inferred from a monocular view); error accumulates over long horizons; goals are images, not language |

## The gap to ACM

1. **Action representation.** ACM proposes object-level actions in a calibrated world
   frame ("push `blue_cup_01` +x by 0.20 m"). V-JEPA 2-AC expects robot end-effector
   deltas in the robot-base frame. A bridge needs camera-to-robot calibration and a
   controller policy that turns "push the cup 0.20 m" into a sequence of 7-D deltas,
   each within its 13 cm envelope.
2. **Domain.** The model was post-trained on Franka-arm tabletop video. A human hand or
   another embodiment pushing an object is outside that distribution.
3. **From latents to ACM facts.** The predictor returns feature maps. ACM needs
   `supported(cup, table) = false` and `fallen(cup)`. That needs a probe trained on
   (latent, scene state) pairs: support, position (m), on-floor, contact. Without that
   probe nothing reaches ACM. Rendering a "future video" would need a separate decoder,
   which V-JEPA does not provide.
4. **Uncertainty.** The model gives one deterministic rollout per action sequence. Any
   probability would have to come from an ensemble or sampled rollouts, and would need
   calibrating against outcomes before it is reported as one.

## What it would take

| Step | Needs |
|---|---|
| Run the checkpoint | CUDA GPU (24 GB class), PyTorch, `timm`, `einops`, the ViT-g checkpoint (several GB) |
| Embodiment | a Franka arm (or matching data); camera placed so the robot base is visible |
| Action bridge | camera-robot calibration; object push → end-effector delta sequence |
| State probe | labelled episodes: latent → support / position / contact / fall |
| Evaluation | the same episodes and metrics as the simulator baseline (`acm.evaluation`): fall precision/recall, support-state accuracy, position error in metres, abstention |

## Evaluation against the baseline

The deterministic simulator is the bar. On the bundled synthetic scene it reproduces
the scripted outcome exactly (fall P = R = 1, red-cup position error 0.0 m). That is a
property of the scripted scene, not evidence about real pushes. A learned model is only
worth integrating if, on held-out **real** episodes (`EpisodeStore` split `eval`), it
beats the simulator where the simulator's assumptions fail: friction, tipping, and
objects that are not discs.
