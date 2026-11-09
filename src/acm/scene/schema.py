"""The ACM scene model (schema ``acm.scene/1``).

A scene is a script: where and when, who is there (goals, relationships, what they know),
which objects are present and who owns or holds them, and an ordered list of events
(actions, dialogue, observations, state changes). Each event may change the scene state.
On top of the script, an analysis lists consequences per scope, and next-scene branches
continue it under stated assumptions.

Provenance is explicit everywhere:

    Source   where a piece of content comes from
             scenario_fact · authored_demo · generated_inference · unknown
    Status   how well a consequence is supported
             stated · possible · unknown · not_identified

Goals, behaviour and feelings are separate. Private thoughts and feelings exist only as
``Inference`` items, whose status is ``possible`` (or ``unknown``), never ``stated``.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCENE_SCHEMA = "acm.scene/1"
DIRECTIONS_SCHEMA = "acm.directions/1"


class Source(str, Enum):
    SCENARIO_FACT = "scenario_fact"
    AUTHORED_DEMO = "authored_demo"
    GENERATED_INFERENCE = "generated_inference"
    UNKNOWN = "unknown"


class Status(str, Enum):
    STATED = "stated"
    POSSIBLE = "possible"
    UNKNOWN = "unknown"
    NOT_IDENTIFIED = "not_identified"


class Valence(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    UNDETERMINED = "undetermined"


class Horizon(str, Enum):
    IMMEDIATE = "immediate"
    LATER = "later"
    UNKNOWN = "unknown"


class EventType(str, Enum):
    ACTION = "action"
    DIALOGUE = "dialogue"
    OBSERVATION = "observation"
    STATE_CHANGE = "state_change"


#: The documented action vocabulary for scene directions. The 2D player can show all of
#: these; anything else is flagged as unsupported in an export (never silently dropped).
VERBS: dict[str, str] = {
    "move": "go to a stage mark (target: a mark id)",
    "hold": "hold an object (target: object id)",
    "offer": "hold an object out toward another actor (target: actor id, object: object id)",
    "place": "put an object down at a mark (object: object id, target: mark id)",
    "take": "pick an object up (target: object id)",
    "speak": "say the event's dialogue (target: the actor addressed, optional)",
    "pause": "stop and wait",
    "gesture": "a visible gesture with no object (e.g. raise a hand)",
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class Mark(_Model):
    """A named spot in the location. Coordinates are metres on the floor plan (optional)."""

    id: str
    label: str
    x: float | None = None
    y: float | None = None


class Location(_Model):
    name: str
    city: str | None = None
    marks: list[Mark] = Field(default_factory=list)


class Inference(_Model):
    """A possible thought, feeling or behaviour. Never a fact."""

    kind: Literal["thought", "feeling", "behaviour", "reaction"]
    text: str
    status: Status = Status.POSSIBLE
    source: Source = Source.AUTHORED_DEMO

    @field_validator("status")
    @classmethod
    def _not_stated(cls, v: Status) -> Status:
        if v in (Status.STATED, Status.NOT_IDENTIFIED):
            raise ValueError("an inference about a person's mind cannot be 'stated' or 'not_identified'")
        return v


class Actor(_Model):
    id: str
    name: str
    role: str
    relationships: dict[str, str] = Field(default_factory=dict, description="other actor id -> relation")
    goals: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list, description="stated preferences and positions")
    constraints: list[str] = Field(default_factory=list)
    position: str | None = Field(default=None, description="a mark id, when known")
    knows: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list, description="what the scene does not establish about them")
    inferences: list[Inference] = Field(default_factory=list)


class SceneObject(_Model):
    id: str
    label: str
    kind: Literal["physical", "obligation"] = "physical"
    description: str = ""
    owner: str | None = None
    holder: str | None = None
    position: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class Change(_Model):
    """One state change: ``subject.attribute = value`` (subject: actor, object or 'scene')."""

    subject: str
    attribute: str
    value: Any


class Event(_Model):
    id: str
    order: int
    actor: str | None = None
    type: EventType
    verb: str | None = None
    target: str | None = None
    object: str | None = None
    description: str
    dialogue: str | None = None
    voice: str | None = Field(default=None, description="optional voice direction for future TTS")
    animation: str | None = Field(default=None, description="optional animation cue for a future 3D player")
    effects: list[Change] = Field(default_factory=list)
    source: Source = Source.AUTHORED_DEMO


class Scope(_Model):
    n: int
    id: str
    title: str
    short: str


class Consequence(_Model):
    id: str
    scope: str
    affected: list[str] = Field(default_factory=list, description="actor, object or system ids")
    description: str
    goal: str | None = None
    evidence: list[str] = Field(default_factory=list, description="event ids that support it")
    status: Status
    effect: dict[str, Valence] = Field(default_factory=dict, description="affected id -> sign, from their view")
    horizon: Horizon = Horizon.UNKNOWN
    assumptions: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    source: Source = Source.AUTHORED_DEMO


class GoalChange(_Model):
    actor: str
    change: str
    effect: Valence


class Branch(_Model):
    id: str
    title: str
    parent: str
    assumptions: list[str] = Field(min_length=1)
    summary: str
    events: list[Event] = Field(min_length=1)
    goal_changes: list[GoalChange] = Field(default_factory=list)
    inferences: dict[str, list[Inference]] = Field(default_factory=dict, description="actor id -> possible reactions")
    consequences: list[Consequence] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    plausibility: str
    source: Source


class Conflict(_Model):
    between: list[str]
    description: str
    evidence: list[str] = Field(default_factory=list)
    status: Status


class Analysis(_Model):
    scene: str
    provider: str
    source: Source
    conflicts: list[Conflict] = Field(default_factory=list)
    consequences: list[Consequence] = Field(default_factory=list)


class DemoContent(_Model):
    """Authored analysis and branches the deterministic demo provider returns."""

    conflicts: list[Conflict] = Field(default_factory=list)
    consequences: list[Consequence] = Field(default_factory=list)
    branches: list[Branch] = Field(default_factory=list)


class Scene(_Model):
    schema_: Literal["acm.scene/1"] = Field(default=SCENE_SCHEMA, alias="schema")
    id: str
    title: str
    description: str
    action: str | None = Field(default=None, description="the central action, at the centre of the consequence radius")
    location: Location
    time: str
    context: list[str] = Field(default_factory=list)
    status: str = Field(description="the scene's state at its end, in words")
    initial: dict[str, Any] = Field(default_factory=dict, description="scene-level facts at the start (subject 'scene')")
    actors: list[Actor]
    objects: list[SceneObject] = Field(default_factory=list)
    events: list[Event] = Field(min_length=1)
    scopes: list[Scope] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    demo: DemoContent | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def actor(self, actor_id: str) -> Actor | None:
        return next((a for a in self.actors if a.id == actor_id), None)

    def object(self, object_id: str) -> SceneObject | None:
        return next((o for o in self.objects if o.id == object_id), None)
