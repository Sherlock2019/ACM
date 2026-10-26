"""ACM's output: state changes, where they land, and how they relate to others."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

#: Placeholder key for a concept role the sentence did not fill.
UNKNOWN = "?"

#: Key used for a first-person actor: the model reasoning about its own action.
SELF = "self"


class Target(str, Enum):
    """The circles an action's consequences reach, from nearest to widest."""

    ACTOR = "actor"  # WHO - the one acting (possibly the model itself)
    IMPACTED = "impacted"  # WHAT / TO WHOM - the subjects the action lands on
    OTHER_ACTORS = "other_actors"  # other actors' goals and actions
    ENVIRONMENT = "environment"  # WHERE - the local environment acted upon
    NEIGHBOUR = "neighbour"  # the places next to it
    ORGANIZATION = "organization"  # businesses, enterprises, institutions and systems it belongs to
    CITY = "city"  # the city it is in
    COUNTRY = "country"  # the country it is in
    SOCIETY = "society"  # shared human systems
    EARTH = "earth"  # the planet


#: The blast radius: environment layers from the place itself outwards. Each one
#: can carry impact rules (packs/universal/impacts.yaml).
LAYERS: tuple[Target, ...] = (
    Target.ENVIRONMENT,
    Target.NEIGHBOUR,
    Target.ORGANIZATION,
    Target.CITY,
    Target.COUNTRY,
    Target.SOCIETY,
    Target.EARTH,
)

#: Layers whose extent is resolved from the place gazetteer (packs/universal/places.yaml).
GEO_LAYERS: tuple[Target, ...] = (Target.NEIGHBOUR, Target.ORGANIZATION, Target.CITY, Target.COUNTRY)


class RelationStatus(str, Enum):
    ADVANCED = "advanced"  # makes the goal's outcome true / reinforces the action
    ENABLED = "enabled"  # provides something the goal or action needs
    BLOCKED = "blocked"  # makes the outcome false or impossible / undoes the action
    AT_RISK = "at_risk"  # blocked, unless an unnamed participant is the owner
    HINDERED = "hindered"  # removes something the goal or action needs
    UNAFFECTED = "unaffected"
    NO_EVIDENCE = "no_evidence"  # ACM does not know what one side changes


#: Kept for readability at call sites that only deal with goals.
GoalStatus = RelationStatus


class StateFact(BaseModel):
    """One state with concrete arguments: has(sarah, car) = true.

    ``args`` are canonical entity keys used for matching; ``labels`` are the
    surface texts used for display.
    """

    state: str
    args: list[str]
    labels: list[str]
    value: bool = True

    def same_state(self, other: "StateFact") -> bool:
        return self.state == other.state and self.args == other.args

    @property
    def grounded(self) -> bool:
        return UNKNOWN not in self.args

    def __str__(self) -> str:
        sign = "" if self.value else "not "
        return f"{sign}{self.state}({', '.join(self.labels)})"


class Consequence(BaseModel):
    """A change, seen from the entity or scope it is reported under."""

    fact: StateFact | None = Field(
        default=None, description="The state change; None for layer impacts"
    )
    target: Target
    about: str
    about_label: str
    text: str
    primary: bool = False
    direction: str | None = Field(default=None, description="'+', '-' or '0' for impacts")
    certainty: float = Field(
        ge=0.0, le=1.0,
        description="ACM's rule certainty (tense, modality, conditions). Not a calibrated probability.",
    )
    source: str = Field(
        description="'rule:<CONCEPT>', 'impact:<aspect>', 'frame', 'generic', or the backend for external facts"
    )
    informative: bool = True
    basis: str = Field(
        default="rule",
        description="'rule' (concept/impact pack), 'simulation' (named predictor) or 'observation' (evidence)",
    )
    evidence: list[str] = Field(default_factory=list, description="Evidence or assumption references")


class ExternalFact(BaseModel):
    """A state change ACM did not derive from its own rules.

    It was observed (image/video evidence) or predicted by a named backend (a
    simulator). ACM places it in the circles like any other fact, but keeps its
    basis and evidence so the two are never confused.
    """

    fact: StateFact
    basis: str = Field(description="'simulation' or 'observation'")
    source: str = Field(description="Backend and version, e.g. 'simulator:tabletop-kinematic@1'")
    evidence: list[str] = Field(default_factory=list)


class Participant(BaseModel):
    """A scene entity that may not appear in the action frame (the floor, the table)."""

    key: str
    label: str
    place: bool = False
    animate: bool = False


class UnknownConsequence(BaseModel):
    """Something ACM cannot say, and what it would need to say it."""

    about: str
    about_label: str
    aspect: str
    text: str
    needs: list[str] = Field(default_factory=list)


class Intention(BaseModel):
    """Something another actor wants (a goal) or has done (an action).

    Both are written as states so they can be compared with the current action's
    consequences: ``outcome`` is what the goal wants or the action achieved,
    ``requires`` is what it depends on.
    """

    kind: str = Field(description="'goal' or 'action'")
    owner: str
    owner_label: str
    text: str
    concept: str | None = None
    outcome: list[StateFact] = Field(default_factory=list)
    requires: list[StateFact] = Field(default_factory=list)
    sentence_index: int = 0


class Relation(BaseModel):
    """How the current action bears on one intention."""

    intention: Intention
    status: RelationStatus
    reason: str
    via: StateFact | None = None


class ConsequenceReport(BaseModel):
    action_text: str
    language: str
    predicate: str | None = None
    concept: str | None = None
    actor: str | None = None
    actor_label: str | None = None
    self_view: bool = Field(
        default=False, description="The actor is 'I': the model is assessing its own action"
    )
    places: list[str] = Field(default_factory=list)
    scopes: dict[str, list[str]] = Field(
        default_factory=dict,
        description="What each geographic layer is for this action: neighbour/organization/city/country -> names",
    )
    tense: str | None = None
    modality: str | None = None
    certainty: float = 1.0
    realized: bool = Field(
        default=True, description="False when the action is negated: nothing changes"
    )
    condition: str | None = None
    consequences: list[Consequence] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    unknowns: list[UnknownConsequence] = Field(default_factory=list)
    trace: dict[str, Any] = Field(
        default_factory=dict,
        description="What ACM used: MLM frame, concept, role bindings, state facts, categories, rules fired",
    )
    graph: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    def for_target(self, target: Target) -> list[Consequence]:
        return [c for c in self.consequences if c.target == target]

    def own_goals(self) -> list[Relation]:
        return [
            r for r in self.relations
            if r.intention.owner == self.actor and r.intention.kind == "goal"
        ]

    def other_relations(self) -> list[Relation]:
        return [r for r in self.relations if r.intention.owner != self.actor]
