"""Scene state, built from the script: the initial facts, then each event's effects in order.

The state is a plain mapping ``{subject: {attribute: value}}`` (subjects are actors, objects
and ``scene``), so it serialises directly and a player can read positions and holders from it.
Nothing is inferred here: an attribute changes only when an event says so.
"""

from __future__ import annotations

import copy
from typing import Any

from acm.scene.schema import Branch, Event, Scene

State = dict[str, dict[str, Any]]


def initial_state(scene: Scene) -> State:
    state: State = {"scene": dict(scene.initial)}
    for a in scene.actors:
        state[a.id] = {"position": a.position}
    for o in scene.objects:
        state[o.id] = {"owner": o.owner, "holder": o.holder, "position": o.position, **o.attributes}
    return state


def apply(state: State, event: Event) -> State:
    nxt = copy.deepcopy(state)
    for change in event.effects:
        nxt.setdefault(change.subject, {})[change.attribute] = change.value
    return nxt


def timeline(scene: Scene, events: list[Event] | None = None, start: State | None = None) -> list[dict[str, Any]]:
    """The state before the first event and after every event: ``[{event, state, changed}]``."""
    state = start if start is not None else initial_state(scene)
    out: list[dict[str, Any]] = [{"event": None, "state": state, "changed": []}]
    for event in events if events is not None else scene.events:
        nxt = apply(state, event)
        changed = [f"{c.subject}.{c.attribute}" for c in event.effects if state.get(c.subject, {}).get(c.attribute) != c.value]
        out.append({"event": event.id, "state": nxt, "changed": changed})
        state = nxt
    return out


def final_state(scene: Scene) -> State:
    return timeline(scene)[-1]["state"]


def branch_timeline(scene: Scene, branch: Branch) -> list[dict[str, Any]]:
    """A branch continues from the end of its parent scene."""
    return timeline(scene, branch.events, start=final_state(scene))
