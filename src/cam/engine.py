"""The consequence engine: Phrase DNA in, consequences and relations out.

    text -> MLM frames -> bind concept roles -> state changes
         -> place each change: actor / impacted subjects / environment (WHERE)
         -> wider impacts: society / earth
         -> compare with other actors' goals and actions
         -> action graph with a vector on every node

Earlier sentences are context: they supply other actors' goals ("Mark wants to
buy John's car") and actions ("Mark bought a car"). The last sentence is the
action being assessed. When its actor is "I", the report is the model's view of
its own action.

Same honesty rules as MLM: a verb CAM has no concept for gets generic, explicitly
uninformative consequences, and never a verdict on anyone's goals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from splm.phrase.schema import FrameElement, PredicateType, UniversalPhraseFrame

from cam.entities import EntityIndex, is_animate, is_place
from cam.graph import Embedder, build_action_graph, default_embedder
from cam.packs import Concept, ConsequencePacks, EffectSpec, get_packs
from cam.schema import (
    SELF,
    UNKNOWN,
    Consequence,
    ConsequenceReport,
    Intention,
    Relation,
    RelationStatus,
    StateFact,
    Target,
)

#: Predicates that describe how things are rather than something being done.
STATE_PREDICATES = frozenset(
    {
        PredicateType.STATE,
        PredicateType.RELATIONSHIP,
        PredicateType.EXISTENCE,
        PredicateType.POSSESSION,
    }
)
SUBJECT_ROLES = frozenset({"AGENT", "EXPERIENCER"})
PLACE_SLOTS = ("location", "destination", "source")


@dataclass(frozen=True)
class Binding:
    """A frame element resolved to a canonical entity."""

    key: str
    label: str
    place: bool = False
    animate: bool = False
    role: str | None = None
    entity_type: str | None = None


@dataclass
class _Fact:
    fact: StateFact
    primary: bool
    source: str
    informative: bool


class ConsequenceEngine:
    """Predict what an action changes, and for whom."""

    def __init__(
        self,
        packs: ConsequencePacks | None = None,
        *,
        pipeline: Any | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.packs = packs or get_packs()
        self._pipeline = pipeline
        self._embedder = embedder

    @property
    def pipeline(self) -> Any:
        if self._pipeline is None:
            from splm.pipeline import SPLMPipeline

            self._pipeline = SPLMPipeline()
        return self._pipeline

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = default_embedder()
        return self._embedder

    # -- entry points ------------------------------------------------------

    def analyze(
        self, text: str, *, context: list[str] | None = None, language: str | None = None
    ) -> ConsequenceReport:
        """Parse context + action with MLM, then predict. The last sentence is the action."""
        full = " ".join(part.strip() for part in [*(context or []), text] if part.strip())
        analysis = self.pipeline.analyze(full, language=language, detect_style=False)
        if not analysis.frames:
            return ConsequenceReport(
                action_text=text,
                language=analysis.language,
                notes=["MLM produced no frame for this text.", *analysis.warnings],
            )
        report = self.predict(analysis.frames, language=analysis.language)
        report.notes.extend(analysis.warnings)
        return report

    def predict(
        self, frames: list[UniversalPhraseFrame], *, language: str | None = None
    ) -> ConsequenceReport:
        """Consequences of the last frame, read against the frames before it."""
        if not frames:
            raise ValueError("predict() needs at least one frame")
        action = frames[-1]
        position = len(frames) - 1
        language = language or action.language
        index = EntityIndex(frames)

        report = ConsequenceReport(
            action_text=action.text,
            language=language,
            tense=action.tense.value if action.tense else None,
            modality=action.modality,
            realized=not action.negation,
        )
        intentions = self._context_intentions(frames[:-1], index, language)

        if action.predicate is None:
            report.notes.append("MLM found no predicate in the action sentence; nothing to predict.")
            return report

        lemma = action.predicate.lemma
        report.predicate = lemma
        actor = self._actor(action, position, index)
        if actor is not None:
            report.actor, report.actor_label = actor.key, actor.label
            report.self_view = actor.key == SELF

        concept = self.packs.concept_for(lemma, language)
        report.concept = concept.name if concept else None
        report.certainty = self._certainty(action)
        if action.condition:
            report.condition = "; ".join(element.text for element in action.condition)
            report.notes.append(f"Consequences hold only if: {report.condition}.")

        bindings = self._bind(action, concept, position, index) if concept else {}
        places = self._places(action, position, index, bindings)
        report.places = [place.label for place in places.values()]

        is_state = action.predicate.type in STATE_PREDICATES and concept is None
        facts: list[_Fact] = []
        if concept is not None:
            for effect in concept.effects:
                fact = self._fact(effect, bindings)
                if fact is not None:
                    facts.append(_Fact(fact, effect.primary, f"rule:{concept.name}", True))
        elif is_state:
            report.notes.append(f"'{lemma}' describes a state, not an action: nothing changes.")
        else:
            facts.extend(self._generic(action, actor, position, index))
            report.notes.append(
                f"CAM has no concept for '{lemma}': consequences are generic and say "
                "nothing about anyone's goals."
            )
        if not is_state:
            for place in places.values():
                facts.append(
                    _Fact(
                        StateFact(state="occurs_at", args=[lemma, place.key], labels=[lemma, place.label]),
                        False,
                        "frame",
                        True,
                    )
                )

        if action.negation:
            report.notes.append("The action is negated: none of its consequences follow.")
            facts = []

        entities = self._entities(action, position, index, actor, bindings, places)
        report.consequences = self._place_facts(facts, actor, places, entities, report.certainty)
        if report.realized and not is_state:
            report.consequences += self._impacts(action, concept, language, report.certainty)

        if actor is not None:
            intentions += self._purpose_goals(action, actor, position, index, language)
            # Only *other* actors' past actions are relations; the actor's own goals stay.
            intentions = [
                i for i in intentions if i.kind == "goal" or i.owner != actor.key
            ]
        report.relations = [self._relate(i, facts, report) for i in intentions]

        report.graph = build_action_graph(
            report, list(entities.values()), self.embedder
        ).to_dict()
        return report

    # -- binding -----------------------------------------------------------

    def _binding(self, element: FrameElement, sentence: int, index: EntityIndex) -> Binding:
        key, label = index.resolve(element, sentence)
        return Binding(
            key=key,
            label=label,
            place=is_place(element),
            animate=is_animate(element),
            role=element.semantic_role,
            entity_type=element.entity_type,
        )

    def _actor(
        self, frame: UniversalPhraseFrame, sentence: int, index: EntityIndex
    ) -> Binding | None:
        """The AGENT wherever it sits (a passive puts it outside the subject), else the subject."""
        agents = [e for e in frame.find_role("AGENT") if e.frame is None]
        subjects = [e for e in frame.subject if e.frame is None]
        element = (agents or subjects or [None])[0]
        return None if element is None else self._binding(element, sentence, index)

    def _bind(
        self,
        frame: UniversalPhraseFrame,
        concept: Concept,
        sentence: int,
        index: EntityIndex,
        *,
        implicit: Binding | None = None,
    ) -> dict[str, Binding]:
        """Fill the concept's roles from the frame, each element at most once.

        ``implicit`` stands in for a missing subject: in "Mark wants to buy John's
        car" the nested frame for *buy* has no subject of its own - it is Mark's.
        """
        elements = [element for _, element in frame.elements() if element.frame is None]
        used: set[int] = set()
        bindings: dict[str, Binding] = {}
        implicit_free = implicit is not None and not frame.subject

        for role, specs in concept.roles.items():
            for spec in specs:
                match = next(
                    (
                        e
                        for e in elements
                        if id(e) not in used
                        and e.semantic_role == spec.role
                        and _type_matches(e, spec.entity_type)
                    ),
                    None,
                )
                if match is not None:
                    used.add(id(match))
                    bindings[role] = self._binding(match, sentence, index)
                    break
            else:
                if implicit_free and any(spec.role in SUBJECT_ROLES for spec in specs):
                    bindings[role] = implicit  # type: ignore[assignment]
                    implicit_free = False
        return bindings

    def _fact(
        self, effect: EffectSpec, bindings: dict[str, Binding], *, partial: bool = True
    ) -> StateFact | None:
        """Ground an effect in the bound entities.

        An unfilled role becomes "someone" only where it still matters - a
        positive claim on something exclusive ("someone gains the car"). Elsewhere
        ("John is no longer in ?") it would be noise, so the effect is dropped.
        """
        args: list[str] = []
        labels: list[str] = []
        unknown: list[int] = []
        for position, arg in enumerate(effect.args):
            if arg.startswith("="):
                args.append(arg[1:])
                labels.append(arg[1:])
            elif arg in bindings:
                args.append(bindings[arg].key)
                labels.append(bindings[arg].label)
            else:
                args.append(UNKNOWN)
                labels.append("someone")
                unknown.append(position)
        if unknown:
            exclusive = self.packs.states[effect.state].exclusive_index
            if not partial or not effect.value or exclusive is None or exclusive in unknown:
                return None
        return StateFact(state=effect.state, args=args, labels=labels, value=effect.value)

    def _places(
        self,
        frame: UniversalPhraseFrame,
        sentence: int,
        index: EntityIndex,
        bindings: dict[str, Binding],
    ) -> dict[str, Binding]:
        places = {b.key: b for b in bindings.values() if b.place}
        for slot in PLACE_SLOTS:
            for element in frame.slot(slot):
                if element.frame is None and is_place(element):
                    binding = self._binding(element, sentence, index)
                    places.setdefault(binding.key, binding)
        return places

    def _entities(
        self,
        frame: UniversalPhraseFrame,
        sentence: int,
        index: EntityIndex,
        actor: Binding | None,
        bindings: dict[str, Binding],
        places: dict[str, Binding],
    ) -> dict[str, Binding]:
        """Every entity in the action frame, keyed canonically."""
        entities: dict[str, Binding] = {}
        for _, element in frame.elements():
            if element.frame is None:
                binding = self._binding(element, sentence, index)
                entities.setdefault(binding.key, binding)
        for binding in [*bindings.values(), *places.values(), *([actor] if actor else [])]:
            entities.setdefault(binding.key, binding)
        return entities

    # -- consequences ------------------------------------------------------

    def _generic(
        self,
        frame: UniversalPhraseFrame,
        actor: Binding | None,
        sentence: int,
        index: EntityIndex,
    ) -> list[_Fact]:
        """What can be said about an unknown verb: someone did it, to something."""
        lemma = frame.predicate.lemma if frame.predicate else "?"
        facts: list[_Fact] = []
        if actor is not None:
            facts.append(
                _Fact(
                    StateFact(state="performed", args=[actor.key, lemma], labels=[actor.label, lemma]),
                    True,
                    "generic",
                    False,
                )
            )
        for slot in ("objects", "recipients", "participants"):
            for element in frame.slot(slot):
                if element.frame is not None:
                    continue
                target = self._binding(element, sentence, index)
                if actor is not None and target.key == actor.key:
                    continue
                facts.append(
                    _Fact(
                        StateFact(state="affected", args=[target.key, lemma], labels=[target.label, lemma]),
                        False,
                        "generic",
                        False,
                    )
                )
        return facts

    def _place_facts(
        self,
        facts: list[_Fact],
        actor: Binding | None,
        places: dict[str, Binding],
        entities: dict[str, Binding],
        certainty: float,
    ) -> list[Consequence]:
        """Report each state change under the actor, an impacted subject or a place."""
        generic_factor = float(self.packs.settings.get("certainty", {}).get("generic_factor", 0.5))
        actor_key = actor.key if actor else None
        out: list[Consequence] = []
        seen: set[tuple[str, str, str]] = set()

        def add(target: Target, about: Binding, text: str, item: _Fact) -> None:
            marker = (target.value, about.key, text)
            if marker in seen:
                return
            seen.add(marker)
            out.append(
                Consequence(
                    fact=item.fact,
                    target=target,
                    about=about.key,
                    about_label=about.label,
                    text=text,
                    primary=item.primary,
                    certainty=round(certainty * (1.0 if item.informative else generic_factor), 3),
                    source=item.source,
                    informative=item.informative,
                )
            )

        for item in facts:
            state = self.packs.states[item.fact.state]
            labels = dict(zip(state.args, item.fact.labels))
            for position, (name, key) in enumerate(zip(state.args, item.fact.args)):
                entity = entities.get(key)
                if entity is None:
                    continue  # literals (money), action names, "someone"
                if key == actor_key:
                    target = Target.ACTOR
                elif key in places:
                    target = Target.ENVIRONMENT
                elif position == 0 or (entity.animate and name in state.phrases):
                    target = Target.IMPACTED
                else:
                    continue  # "car now belongs to Sarah" repeats "Sarah gains car"
                add(target, entity, state.phrase(name, item.fact.value, labels), item)

            # An object that changes somewhere changes that place too: a database
            # deleted in production leaves production without it.
            first = entities.get(item.fact.args[0])
            if (
                first is not None
                and not first.animate
                and not first.place
                and first.key != actor_key
            ):
                sentence = state.phrase("sentence", item.fact.value, labels)
                for place in places.values():
                    add(Target.ENVIRONMENT, place, sentence, item)
        return out

    def _impacts(
        self,
        frame: UniversalPhraseFrame,
        concept: Concept | None,
        language: str,
        certainty: float,
    ) -> list[Consequence]:
        """Society and earth impacts from the rules whose concept and categories match."""
        categories: set[str] = set()
        if frame.predicate is not None:
            categories |= self.packs.categories_for(frame.predicate.lemma, language)
        for _, element in frame.elements():
            if element.frame is not None:
                continue
            categories |= self.packs.categories_for(element.head_lemma or element.text, language)
            for value in element.annotations.values():
                if isinstance(value, str):
                    categories |= self.packs.categories_for(value, language)

        out: list[Consequence] = []
        for rule in self.packs.impacts_for(concept.name if concept else None, categories):
            target = Target.SOCIETY if rule.scope == "society" else Target.EARTH
            out.append(
                Consequence(
                    target=target,
                    about=rule.aspect,
                    about_label=rule.aspect,
                    text=rule.effect,
                    direction=rule.direction,
                    certainty=round(certainty, 3),
                    source=f"impact:{rule.aspect}",
                )
            )
        return out

    def _certainty(self, frame: UniversalPhraseFrame) -> float:
        settings = self.packs.settings.get("certainty", {})
        if frame.certainty is not None:
            value = frame.certainty
        else:
            tense = frame.tense.value if frame.tense else None
            value = settings.get("by_tense", {}).get(tense, settings.get("default", 0.8))
        if frame.condition:
            value *= float(settings.get("condition_factor", 0.6))
        return round(float(value), 3)

    # -- intentions: other actors' goals and actions -----------------------

    def _context_intentions(
        self, frames: list[UniversalPhraseFrame], index: EntityIndex, language: str
    ) -> list[Intention]:
        intentions: list[Intention] = []
        for sentence, frame in enumerate(frames):
            if frame.predicate is None or frame.negation:
                continue
            if self.packs.is_goal_marker(frame.predicate.lemma, language):
                goal = self._stated_goal(frame, sentence, index, language)
                if goal is not None:
                    intentions.append(goal)
                continue

            concept = self.packs.concept_for(frame.predicate.lemma, language)
            actor = self._actor(frame, sentence, index)
            if concept is None or actor is None:
                continue
            bindings = self._bind(frame, concept, sentence, index)
            intentions.append(
                Intention(
                    kind="action",
                    owner=actor.key,
                    owner_label=actor.label,
                    text=frame.text,
                    concept=concept.name,
                    outcome=self._facts(concept.effects, bindings),
                    requires=self._facts(concept.requires, bindings),
                    sentence_index=sentence,
                )
            )
        return intentions

    def _stated_goal(
        self, frame: UniversalPhraseFrame, sentence: int, index: EntityIndex, language: str
    ) -> Intention | None:
        """"Mark wants to buy John's car" / "Sarah needs a car"."""
        owner_element = next((e for e in frame.subject if e.frame is None), None)
        if owner_element is None:
            return None
        owner = self._binding(owner_element, sentence, index)

        purpose = next((e for e in [*frame.goal, *frame.objects] if e.frame is not None), None)
        if purpose is not None and purpose.frame is not None:
            return self._goal_from_frame(purpose.frame, purpose.text, owner, sentence, index, language)

        thing = next((e for e in frame.objects if e.frame is None), None)
        if thing is None:
            return None
        wanted = self._binding(thing, sentence, index)
        return Intention(
            kind="goal",
            owner=owner.key,
            owner_label=owner.label,
            text=f"have {thing.text}",
            outcome=[StateFact(state="has", args=[owner.key, wanted.key], labels=[owner.label, wanted.label])],
            sentence_index=sentence,
        )

    def _goal_from_frame(
        self,
        frame: UniversalPhraseFrame,
        text: str,
        owner: Binding,
        sentence: int,
        index: EntityIndex,
        language: str,
    ) -> Intention:
        concept = (
            self.packs.concept_for(frame.predicate.lemma, language) if frame.predicate else None
        )
        if concept is None:
            return Intention(
                kind="goal", owner=owner.key, owner_label=owner.label, text=text, sentence_index=sentence
            )
        bindings = self._bind(frame, concept, sentence, index, implicit=owner)
        return Intention(
            kind="goal",
            owner=owner.key,
            owner_label=owner.label,
            text=text,
            concept=concept.name,
            outcome=self._facts(concept.primary_effects, bindings),
            requires=self._facts(concept.requires, bindings),
            sentence_index=sentence,
        )

    def _purpose_goals(
        self,
        frame: UniversalPhraseFrame,
        actor: Binding,
        sentence: int,
        index: EntityIndex,
        language: str,
    ) -> list[Intention]:
        """The actor's own goal: "... to pay his debt"."""
        return [
            self._goal_from_frame(element.frame, element.text, actor, sentence, index, language)
            for element in frame.goal
            if element.frame is not None
        ]

    def _facts(self, effects: tuple[EffectSpec, ...], bindings: dict[str, Binding]) -> list[StateFact]:
        """Fully grounded facts only: an intention cannot be compared on "someone"."""
        facts = [self._fact(effect, bindings, partial=False) for effect in effects]
        return [fact for fact in facts if fact is not None]

    # -- relating ----------------------------------------------------------

    def _relate(
        self, intention: Intention, facts: list[_Fact], report: ConsequenceReport
    ) -> Relation:
        def relation(status: RelationStatus, reason: str, via: StateFact | None = None) -> Relation:
            return Relation(intention=intention, status=status, reason=reason, via=via)

        if not intention.outcome and not intention.requires:
            return relation(
                RelationStatus.NO_EVIDENCE,
                f"CAM has no concept for what '{intention.text}' changes",
            )
        if not report.realized:
            return relation(RelationStatus.UNAFFECTED, "the action does not happen (negated)")
        known = [item.fact for item in facts if item.informative]
        if not known:
            return relation(
                RelationStatus.NO_EVIDENCE,
                f"CAM does not know what '{report.predicate}' changes",
            )

        for wanted in intention.outcome:
            for fact in known:
                if fact.same_state(wanted) and fact.value == wanted.value:
                    return relation(
                        RelationStatus.ADVANCED, f"makes '{self._sentence(wanted)}' true", fact
                    )
        for wanted in intention.outcome:
            for fact in known:
                conflict = self._conflict(fact, wanted)
                if conflict == "unknown_holder":
                    return relation(
                        RelationStatus.AT_RISK,
                        f"{self._sentence(fact)} - blocked unless that is {intention.owner_label}",
                        fact,
                    )
                if conflict:
                    return relation(
                        RelationStatus.BLOCKED,
                        f"{self._sentence(fact)}, so '{self._sentence(wanted)}' cannot hold",
                        fact,
                    )
        for needed in intention.requires:
            for fact in known:
                if fact.same_state(needed) and fact.value == needed.value:
                    return relation(
                        RelationStatus.ENABLED,
                        f"provides what it needs: {self._sentence(fact)}",
                        fact,
                    )
        for needed in intention.requires:
            for fact in known:
                if self._conflict(fact, needed):
                    return relation(
                        RelationStatus.HINDERED,
                        f"takes away what it needs: {self._sentence(fact)}",
                        fact,
                    )
        return relation(RelationStatus.UNAFFECTED, "none of the action's changes touch it")

    def _conflict(self, fact: StateFact, wanted: StateFact) -> str | None:
        """Whether ``fact`` makes ``wanted`` impossible, and how."""
        if fact.same_state(wanted) and fact.value != wanted.value:
            return "contradiction"
        if fact.state != wanted.state or not (fact.value and wanted.value):
            return None
        exclusive = self.packs.states[fact.state].exclusive_index
        if exclusive is None or fact.args[exclusive] != wanted.args[exclusive]:
            return None
        holders = [a for i, a in enumerate(fact.args) if i != exclusive]
        wanted_holders = [a for i, a in enumerate(wanted.args) if i != exclusive]
        if holders == wanted_holders:
            return None
        return "unknown_holder" if UNKNOWN in holders else "exclusive"

    def _sentence(self, fact: StateFact) -> str:
        state = self.packs.states[fact.state]
        return state.phrase("sentence", fact.value, dict(zip(state.args, fact.labels)))


def _type_matches(element: FrameElement, entity_type: str | None) -> bool:
    if entity_type is None:
        return True
    if entity_type == "PERSON":
        return is_animate(element)
    return element.entity_type == entity_type
