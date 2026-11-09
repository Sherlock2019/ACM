"""Scene directions (schema ``acm.directions/1``): the selected scene as an ordered, validated
list of actions and lines, for a player, a future 3D renderer or a text-to-speech provider.

This is an export format. No 3D, physics or voice engine consumes it yet; the dashboard's
2D player reads the same events. Actions outside the vocabulary (``schema.VERBS``) are kept
and flagged in ``unsupported``, never dropped.
"""

from __future__ import annotations

from typing import Any

from acm.scene.schema import DIRECTIONS_SCHEMA, SCENE_SCHEMA, VERBS, Branch, Event, EventType, Scene
from acm.scene.state import final_state, initial_state
from acm.scene.validate import SceneError, validate_branch, validate_scene


def _verb(e: Event) -> str | None:
    if e.verb:
        return e.verb
    return "speak" if e.type == EventType.DIALOGUE else None


def directions(scene: Scene, branch: Branch | None = None) -> dict[str, Any]:
    """Directions for scene 1 (``branch=None``) or for a branch continuing it."""
    validate_scene(scene)
    if branch is not None:
        validate_branch(branch, scene)
    events = branch.events if branch is not None else scene.events
    start = final_state(scene) if branch is not None else initial_state(scene)
    actions, unsupported = [], []
    for e in events:
        verb = _verb(e)
        supported = verb in VERBS if verb else e.type in (EventType.OBSERVATION, EventType.STATE_CHANGE)
        item = {
            "order": e.order, "event": e.id, "type": e.type.value, "verb": verb, "actor": e.actor,
            "target": e.target, "object": e.object, "text": e.description, "dialogue": e.dialogue,
            "voice": e.voice, "animation": e.animation, "source": e.source.value, "player_supported": supported,
        }
        actions.append(item)
        if not supported:
            unsupported.append({"event": e.id, "verb": verb, "reason": "not in the action vocabulary"})
    out = {
        "schema": DIRECTIONS_SCHEMA,
        "scene_schema": SCENE_SCHEMA,
        "scene": scene.id,
        "branch": branch.id if branch is not None else None,
        "title": branch.title if branch is not None else scene.title,
        "location": scene.location.model_dump(mode="json"),
        "time": scene.time,
        "actors": [{"id": a.id, "name": a.name, "position": start.get(a.id, {}).get("position")} for a in scene.actors],
        "objects": [{"id": o.id, "label": o.label, "kind": o.kind, **{k: start.get(o.id, {}).get(k) for k in ("owner", "holder", "position")}}
                    for o in scene.objects],
        "actions": actions,
        "assumptions": branch.assumptions if branch is not None else [],
        "source": (branch.source.value if branch is not None else "authored_demo"),
        "unsupported": unsupported,
        "vocabulary": VERBS,
        "integrations": {"renderer_3d": "planned (not integrated)", "physics": "planned (not integrated)",
                         "text_to_speech": "browser speech synthesis in the dashboard only; no export consumer"},
    }
    check_directions(out, scene)
    return out


def check_directions(data: dict[str, Any], scene: Scene) -> None:
    """Validate an export: schema tag, references and strictly increasing order."""
    problems = []
    if data.get("schema") != DIRECTIONS_SCHEMA:
        problems.append(f"schema must be {DIRECTIONS_SCHEMA!r}")
    if data.get("scene") != scene.id:
        problems.append("scene id mismatch")
    actors = {a.id for a in scene.actors}
    names = actors | {o.id for o in scene.objects} | {m.id for m in scene.location.marks}
    orders = [a["order"] for a in data.get("actions", [])]
    if orders != sorted(orders) or len(set(orders)) != len(orders):
        problems.append(f"actions out of order: {orders}")
    for a in data.get("actions", []):
        if a["actor"] is not None and a["actor"] not in actors:
            problems.append(f"action {a['event']}: unknown actor {a['actor']!r}")
        for key in ("target", "object"):
            if a[key] is not None and a[key] not in names:
                problems.append(f"action {a['event']}: unknown {key} {a[key]!r}")
        if a["verb"] == "speak" and not a["dialogue"]:
            problems.append(f"action {a['event']}: 'speak' without dialogue")
    if problems:
        raise SceneError(problems)
