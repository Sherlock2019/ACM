"""The action graph: one action, its context and its consequences, as vectors.

Nodes
    action      the predicate (SALE / sell)
    self        the actor, when the actor is "I" - the model itself
    entity      WHO / WHAT / TO WHOM / WITH WHOM
    place       WHERE
    time        WHEN
    state       a state change the action causes: has(Sarah, car)
    impact      a society or earth impact
    scope       the society and earth circles themselves
    intention   another actor's goal or action

Edges
    action -[ROLE]-> entity          semantic roles from MLM (AGENT, PATIENT, ...)
    action -[causes]-> state -[changes:<target>]-> entity
    action -[impacts]-> impact -[within]-> scope
    owner -[wants|did]-> intention,  action -[<status>]-> intention

Every node has a vector, so graphs from many actions can be stored together and
searched (:mod:`acm.store`). The default :class:`HashingEmbedder` is structural:
it encodes what part a node plays, plus a hashed identity of its lemma. Two nodes
are close when they play the same part in similar actions; "car" and "vehicle"
are as unrelated as "car" and "Paris". That is a baseline, not semantics - a
learned embedder can replace it behind the same interface.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Protocol, Sequence

from acm.schema import SELF, Target

if TYPE_CHECKING:  # pragma: no cover
    from acm.engine import Binding
    from acm.schema import ConsequenceReport

NODE_KINDS: tuple[str, ...] = (
    "action", "self", "entity", "place", "time", "state", "impact", "scope", "intention",
)
TARGETS: tuple[str, ...] = tuple(t.value for t in Target)
TENSES: tuple[str, ...] = ("past", "present", "future")


class Embedder(Protocol):
    dim: int

    def embed(self, **features: Any) -> list[float]: ...


class HashingEmbedder:
    """Deterministic structural vectors; no model, no download.

    Layout, in order: node kind | MLM role | entity type | target circle |
    hashed lemma | scalars (certainty, polarity, past, present, future, negation).
    """

    def __init__(self, roles: Sequence[str], entity_types: Sequence[str], lemma_dims: int = 32) -> None:
        self.roles = tuple(roles)
        self.entity_types = tuple(entity_types)
        self.lemma_dims = lemma_dims
        self.layout: list[tuple[str, int]] = [
            ("kind", len(NODE_KINDS)),
            ("role", len(self.roles)),
            ("entity_type", len(self.entity_types)),
            ("target", len(TARGETS)),
            ("lemma", lemma_dims),
            ("scalars", 6),
        ]
        self.dim = sum(size for _, size in self.layout)

    def embed(
        self,
        *,
        kind: str,
        role: str | None = None,
        entity_type: str | None = None,
        target: str | None = None,
        lemma: str | None = None,
        certainty: float = 0.0,
        polarity: float = 0.0,
        tense: str | None = None,
        negation: bool = False,
    ) -> list[float]:
        parts: list[list[float]] = [
            _one_hot(kind, NODE_KINDS),
            _one_hot(role, self.roles),
            _one_hot(entity_type, self.entity_types),
            _one_hot(target, TARGETS),
            self._hash(lemma),
            [
                certainty,
                polarity,
                *(1.0 if tense == t else 0.0 for t in TENSES),
                1.0 if negation else 0.0,
            ],
        ]
        vector = [value for part in parts for value in part]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [round(v / norm, 6) for v in vector]

    def _hash(self, lemma: str | None) -> list[float]:
        out = [0.0] * self.lemma_dims
        if lemma:
            digest = hashlib.md5(lemma.lower().encode("utf-8")).digest()
            for i in range(0, 4, 2):  # two buckets reduce collisions
                out[digest[i] % self.lemma_dims] += 1.0 if digest[i + 1] & 1 else -1.0
        return out


def _one_hot(value: str | None, vocabulary: Sequence[str]) -> list[float]:
    return [1.0 if value == item else 0.0 for item in vocabulary]


@lru_cache(maxsize=1)
def default_embedder() -> HashingEmbedder:
    """Role and entity-type inventories come from MLM's universal pack, not from here."""
    from splm.language.packs import get_registry

    universal = get_registry().universal()
    entity_types = list(universal.semantic_roles.get("entity_types", {}).keys())
    return HashingEmbedder(universal.role_names, entity_types)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class ActionGraph:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)

    def add_node(self, node_id: str, *, kind: str, label: str, vector: list[float], **attrs: Any) -> str:
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id": node_id, "kind": kind, "label": label, "vector": vector, **attrs}
        return node_id

    def add_edge(self, source: str, target: str, relation: str) -> None:
        edge = {"source": source, "target": target, "relation": relation}
        if edge not in self.edges:
            self.edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges)}


def build_action_graph(
    report: "ConsequenceReport", entities: list["Binding"], embedder: Embedder
) -> ActionGraph:
    graph = ActionGraph()
    negated = not report.realized
    action = graph.add_node(
        "action",
        kind="action",
        label=report.concept or report.predicate or "?",
        lemma=report.predicate,
        vector=embedder.embed(
            kind="action",
            lemma=report.concept or report.predicate,
            certainty=report.certainty,
            tense=report.tense,
            negation=negated,
        ),
    )

    def entity_node(key: str, label: str, *, role: str | None = None, entity_type: str | None = None, place: bool = False) -> str:
        kind = "self" if key == SELF else ("place" if place else ("time" if role == "TIME" else "entity"))
        return graph.add_node(
            f"e:{key}",
            kind=kind,
            label=label,
            role=role,
            vector=embedder.embed(kind=kind, role=role, entity_type=entity_type, lemma=key),
        )

    for entity in entities:
        node = entity_node(
            entity.key, entity.label, role=entity.role, entity_type=entity.entity_type, place=entity.place
        )
        if entity.role:
            graph.add_edge(action, node, entity.role)

    for consequence in report.consequences:
        if consequence.fact is not None:
            fact = consequence.fact
            state = graph.add_node(
                f"s:{fact.state}({','.join(fact.args)})={fact.value}",
                kind="state",
                label=str(fact),
                vector=embedder.embed(
                    kind="state",
                    lemma=fact.state,
                    target=consequence.target.value,
                    certainty=consequence.certainty,
                    polarity=1.0 if fact.value else -1.0,
                ),
            )
            graph.add_edge(action, state, "causes")
            about = entity_node(consequence.about, consequence.about_label)
            graph.add_edge(state, about, f"changes:{consequence.target.value}")
        else:
            scope = graph.add_node(
                f"scope:{consequence.target.value}",
                kind="scope",
                label=consequence.target.value,
                vector=embedder.embed(kind="scope", target=consequence.target.value),
            )
            polarity = {"+": 1.0, "-": -1.0}.get(consequence.direction or "0", 0.0)
            impact = graph.add_node(
                f"impact:{consequence.target.value}:{consequence.about}",
                kind="impact",
                label=f"{consequence.about}: {consequence.text}",
                direction=consequence.direction,
                vector=embedder.embed(
                    kind="impact",
                    lemma=consequence.about,
                    target=consequence.target.value,
                    certainty=consequence.certainty,
                    polarity=polarity,
                ),
            )
            graph.add_edge(action, impact, "impacts")
            graph.add_edge(impact, scope, "within")

    for number, relation in enumerate(report.relations):
        intention = relation.intention
        node = graph.add_node(
            f"i{number}",
            kind="intention",
            label=f"{intention.owner_label}: {intention.text}",
            intention_kind=intention.kind,
            status=relation.status.value,
            vector=embedder.embed(
                kind="intention",
                lemma=intention.concept,
                target=Target.OTHER_ACTORS.value
                if intention.owner != report.actor
                else Target.ACTOR.value,
            ),
        )
        owner = entity_node(intention.owner, intention.owner_label)
        graph.add_edge(owner, node, "wants" if intention.kind == "goal" else "did")
        graph.add_edge(action, node, relation.status.value)
    return graph
