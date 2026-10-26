"""Which frame elements refer to the same thing.

A goal and an action can only be compared if "John's car" in one sentence and
"his car" or "it" in another are recognised as the same entity. Pronouns are
resolved by MLM's context graph; everything else is keyed on its head lemma, or on
the full text for named entities, whose head lemma would lose words ("New York").

Keying on the head lemma is coarse - two different cars share the key "car" - and
is recorded as a limitation in the README rather than hidden.
"""

from __future__ import annotations

from splm.graph.context_graph import ContextGraph
from splm.phrase.schema import FrameElement, UniversalPhraseFrame

from acm.schema import SELF

NAMED = frozenset({"PERSON", "ORG", "LOCATION", "FACILITY"})
PLACE_TYPES = frozenset({"LOCATION", "FACILITY"})
PLACE_ROLES = frozenset({"LOCATION", "DESTINATION", "SOURCE"})


class EntityIndex:
    """Canonical keys for the elements of a sequence of sentence frames."""

    def __init__(self, frames: list[UniversalPhraseFrame]) -> None:
        graph = ContextGraph()
        graph.add_frames(frames)
        self._resolved: dict[tuple[int, str], str] = {
            (ref.sentence_index, ref.mention.strip().lower()): ref.resolved_label
            for ref in graph.coreferences
            if ref.resolved_label
        }

    def resolve(self, element: FrameElement, sentence_index: int) -> tuple[str, str]:
        """``(key, label)`` for an element in the given sentence."""
        text = element.text.strip()
        if is_first_person(element):
            # "I", "me", "we": the speaker. When ACM is given its own planned action,
            # this is the model itself - never resolved to some earlier third party.
            return SELF, "self"
        resolved = self._resolved.get((sentence_index, text.lower()))
        if resolved:
            return resolved.lower(), resolved
        if element.entity_type in NAMED or not element.head_lemma:
            return text.lower(), text
        return element.head_lemma.lower(), text


def is_place(element: FrameElement) -> bool:
    # "to Sarah" is a DESTINATION, but Sarah is a recipient, not somewhere.
    if is_animate(element) or element.entity_type == "ORG":
        return False
    return element.entity_type in PLACE_TYPES or element.semantic_role in PLACE_ROLES


def is_animate(element: FrameElement) -> bool:
    return (
        element.entity_type == "PERSON"
        or element.features.get("animacy") == "animate"
        or is_first_person(element)
    )


def is_first_person(element: FrameElement) -> bool:
    return element.features.get("person") == 1 and element.features.get("pronoun_type") is not None
