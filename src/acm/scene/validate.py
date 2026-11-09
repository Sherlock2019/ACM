"""Scene validation beyond the schema: references, event order, vocabulary, evidence.

``validate_scene`` raises ``SceneError`` listing every problem found, so an author can fix
a scene file in one pass. Branches are checked against their parent scene.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from acm.scene.schema import VERBS, Branch, Consequence, Event, EventType, Inference, Scene, Status


class SceneError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("invalid scene:\n  - " + "\n  - ".join(problems))


def _dupes(ids: Iterable[str]) -> list[str]:
    return [i for i, n in Counter(ids).items() if n > 1]


def _check_events(events: list[Event], scene: Scene, where: str, problems: list[str],
                  known_events: set[str] | None = None) -> None:
    actors = {a.id for a in scene.actors}
    objects = {o.id for o in scene.objects}
    marks = {m.id for m in scene.location.marks}
    subjects = actors | objects | {"scene"}
    for dup in _dupes(e.id for e in events):
        problems.append(f"{where}: duplicate event id {dup!r}")
    if known_events:
        for e in events:
            if e.id in known_events:
                problems.append(f"{where}: event id {e.id!r} reuses an id from the parent scene")
    orders = [e.order for e in events]
    if orders != sorted(orders) or len(set(orders)) != len(orders):
        problems.append(f"{where}: events must be listed in strictly increasing order (got {orders})")
    for e in events:
        tag = f"{where} event {e.id}"
        if e.actor is not None and e.actor not in actors:
            problems.append(f"{tag}: unknown actor {e.actor!r}")
        if e.type in (EventType.ACTION, EventType.DIALOGUE) and e.actor is None:
            problems.append(f"{tag}: an {e.type.value} needs an actor")
        if e.type == EventType.DIALOGUE and not (e.dialogue and e.dialogue.strip()):
            problems.append(f"{tag}: a dialogue event needs dialogue text")
        if e.verb is not None and e.verb not in VERBS:
            problems.append(f"{tag}: verb {e.verb!r} is not in the action vocabulary {sorted(VERBS)}")
        if e.target is not None and e.target not in actors | objects | marks:
            problems.append(f"{tag}: unknown target {e.target!r}")
        if e.object is not None and e.object not in objects:
            problems.append(f"{tag}: unknown object {e.object!r}")
        for c in e.effects:
            if c.subject not in subjects:
                problems.append(f"{tag}: effect on unknown subject {c.subject!r}")
            if c.attribute in ("holder", "owner") and c.value is not None and c.value not in actors:
                problems.append(f"{tag}: {c.subject}.{c.attribute} set to unknown actor {c.value!r}")
            if c.attribute == "position" and c.value is not None and c.value not in marks:
                problems.append(f"{tag}: {c.subject}.position set to unknown mark {c.value!r}")


def _check_consequences(items: list[Consequence], scene: Scene, events: set[str], where: str,
                        problems: list[str]) -> None:
    scopes = {s.id for s in scene.scopes}
    parties = {a.id for a in scene.actors} | {o.id for o in scene.objects}
    for dup in _dupes(c.id for c in items):
        problems.append(f"{where}: duplicate consequence id {dup!r}")
    for c in items:
        tag = f"{where} consequence {c.id}"
        if scopes and c.scope not in scopes:
            problems.append(f"{tag}: unknown scope {c.scope!r}")
        for a in c.affected:
            if a not in parties:
                problems.append(f"{tag}: unknown affected party {a!r}")
        for a in c.effect:
            if a not in c.affected:
                problems.append(f"{tag}: effect given for {a!r}, which is not in 'affected'")
        for ev in c.evidence:
            if ev not in events:
                problems.append(f"{tag}: evidence refers to unknown event {ev!r}")
        if c.status == Status.STATED and not c.evidence:
            problems.append(f"{tag}: a stated consequence must cite the events that state it")
        if c.status == Status.NOT_IDENTIFIED and c.affected:
            problems.append(f"{tag}: 'not identified' cannot name affected parties")


def _check_inferences(items: dict[str, list[Inference]], scene: Scene, where: str, problems: list[str]) -> None:
    for actor in items:
        if scene.actor(actor) is None:
            problems.append(f"{where}: inferences for unknown actor {actor!r}")


def validate_branch(branch: Branch, scene: Scene, problems: list[str] | None = None) -> list[str]:
    own = problems if problems is not None else []
    where = f"branch {branch.id}"
    if branch.parent != scene.id:
        own.append(f"{where}: parent {branch.parent!r} is not scene {scene.id!r}")
    parent_events = {e.id for e in scene.events}
    _check_events(branch.events, scene, where, own, known_events=parent_events)
    last = max(e.order for e in scene.events)
    if branch.events and branch.events[0].order <= last:
        own.append(f"{where}: its events must come after the parent scene's (order > {last})")
    for g in branch.goal_changes:
        if scene.actor(g.actor) is None:
            own.append(f"{where}: goal change for unknown actor {g.actor!r}")
    _check_inferences(branch.inferences, scene, where, own)
    _check_consequences(branch.consequences, scene, parent_events | {e.id for e in branch.events}, where, own)
    if problems is None and own:
        raise SceneError(own)
    return own


def validate_scene(scene: Scene) -> Scene:
    problems: list[str] = []
    for kind, ids in (("actor", [a.id for a in scene.actors]), ("object", [o.id for o in scene.objects]),
                      ("mark", [m.id for m in scene.location.marks]), ("scope", [s.id for s in scene.scopes])):
        for dup in _dupes(ids):
            problems.append(f"duplicate {kind} id {dup!r}")
    actors = {a.id for a in scene.actors}
    marks = {m.id for m in scene.location.marks}
    for a in scene.actors:
        for other in a.relationships:
            if other not in actors:
                problems.append(f"actor {a.id}: relationship with unknown actor {other!r}")
        if a.position is not None and a.position not in marks:
            problems.append(f"actor {a.id}: position {a.position!r} is not a mark of {scene.location.name}")
    for o in scene.objects:
        for attr in ("owner", "holder"):
            value = getattr(o, attr)
            if value is not None and value not in actors:
                problems.append(f"object {o.id}: {attr} {value!r} is not an actor")
        if o.position is not None and o.position not in marks:
            problems.append(f"object {o.id}: position {o.position!r} is not a mark")
    _check_events(scene.events, scene, "scene", problems)
    if scene.demo is not None:
        events = {e.id for e in scene.events}
        _check_consequences(scene.demo.consequences, scene, events, "demo analysis", problems)
        for c in scene.demo.conflicts:
            for a in c.between:
                if a not in actors:
                    problems.append(f"demo conflict: unknown actor {a!r}")
            for ev in c.evidence:
                if ev not in events:
                    problems.append(f"demo conflict: unknown evidence event {ev!r}")
        for dup in _dupes(b.id for b in scene.demo.branches):
            problems.append(f"duplicate branch id {dup!r}")
        for b in scene.demo.branches:
            validate_branch(b, scene, problems)
    if problems:
        raise SceneError(problems)
    return scene
