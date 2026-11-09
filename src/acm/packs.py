"""Consequence packs: the YAML knowledge ACM reasons with.

Same rule as MLM's language packs - no linguistic or world facts in Python. Which
verb is a SALE, what a SALE changes and which states are exclusive all live in
``packs/``; this module only loads and indexes them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from acm.schema import LAYERS

PACKS_DIR = Path(__file__).resolve().parents[2] / "packs"


class _StrictLoader(yaml.SafeLoader):
    """Refuses duplicate keys, as MLM's pack loader does.

    Standard YAML keeps the last of two repeated keys without complaint; in a verb
    table that silently drops one lemma's concept. Better to fail loudly.
    """


def _no_duplicate_keys(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found a duplicate key {key!r}; one of the two entries would be silently discarded",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.load(handle, Loader=_StrictLoader) or {}


@dataclass(frozen=True)
class RoleSpec:
    """One way a concept role can be filled: an MLM role, optionally typed."""

    role: str
    entity_type: str | None = None

    @classmethod
    def parse(cls, text: str) -> "RoleSpec":
        role, _, entity_type = text.partition("@")
        return cls(role=role, entity_type=entity_type or None)


@dataclass(frozen=True)
class EffectSpec:
    """A state change, written in concept roles: has(buyer, thing) = true."""

    state: str
    args: tuple[str, ...]
    value: bool = True
    primary: bool = False

    @classmethod
    def parse(cls, data: dict[str, Any]) -> "EffectSpec":
        return cls(
            state=data["state"],
            args=tuple(data["args"]),
            value=bool(data.get("value", True)),
            primary=bool(data.get("primary", False)),
        )


@dataclass(frozen=True)
class Concept:
    name: str
    roles: dict[str, tuple[RoleSpec, ...]]
    effects: tuple[EffectSpec, ...]
    requires: tuple[EffectSpec, ...] = ()

    @property
    def primary_effects(self) -> tuple[EffectSpec, ...]:
        return tuple(effect for effect in self.effects if effect.primary)


PLACE_KINDS = frozenset({"site", "business", "enterprise", "system", "city", "region", "country"})


@dataclass(frozen=True)
class PlaceSpec:
    """A gazetteer entry: what surrounds a place, what it is tied to, where it sits."""

    key: str
    name: str
    kind: str
    city: str | None = None  # gazetteer key of the city it is in
    country: str | None = None  # gazetteer key of the country it is in
    neighbours: tuple[str, ...] = ()
    organization: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImpactRule:
    """An impact on one environment layer, conditional on concept and/or category."""

    scope: str
    aspect: str
    direction: str
    effect: str
    concepts: frozenset[str] = frozenset()
    categories: frozenset[str] = frozenset()

    def matches(self, concept: str | None, categories: set[str]) -> bool:
        if self.concepts and concept not in self.concepts:
            return False
        if self.categories and not (self.categories & categories):
            return False
        return bool(self.concepts or self.categories)


@dataclass(frozen=True)
class StateSpec:
    name: str
    args: tuple[str, ...]
    exclusive: str | None = None
    phrases: dict[str, dict[bool, str]] = field(default_factory=dict)

    @property
    def exclusive_index(self) -> int | None:
        return self.args.index(self.exclusive) if self.exclusive else None

    def phrase(self, perspective: str, value: bool, labels: dict[str, str]) -> str:
        """Render this state from one argument's point of view."""
        template = self.phrases.get(perspective, {}).get(value)
        if template is None:
            template = self.phrases.get("sentence", {}).get(value, f"{self.name}({{}})")
        return template.format_map(_Default(labels))


class _Default(dict):
    """Leave unknown placeholders readable instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "?"


class ConsequencePacks:
    """Concepts, states and per-language verb tables."""

    def __init__(self, packs_dir: Path | str | None = None) -> None:
        self.dir = Path(packs_dir) if packs_dir else PACKS_DIR
        universal = self.dir / "universal"

        states = _load_yaml(universal / "states.yaml").get("states", {})
        self.states: dict[str, StateSpec] = {
            name: StateSpec(
                name=name,
                args=tuple(spec["args"]),
                exclusive=spec.get("exclusive"),
                phrases={
                    perspective: {bool(k): str(v) for k, v in forms.items()}
                    for perspective, forms in (spec.get("phrases") or {}).items()
                },
            )
            for name, spec in states.items()
        }

        concepts = _load_yaml(universal / "concepts.yaml").get("concepts", {})
        self.concepts: dict[str, Concept] = {
            name: Concept(
                name=name,
                roles={
                    role: tuple(RoleSpec.parse(item) for item in fillers)
                    for role, fillers in spec["roles"].items()
                },
                effects=tuple(EffectSpec.parse(e) for e in spec.get("effects", [])),
                requires=tuple(EffectSpec.parse(e) for e in spec.get("requires", [])),
            )
            for name, spec in concepts.items()
        }
        self.settings: dict[str, Any] = _load_yaml(universal / "settings.yaml")

        rules = _load_yaml(universal / "impacts.yaml").get("rules", [])
        self.impact_rules: tuple[ImpactRule, ...] = tuple(
            ImpactRule(
                scope=rule["impact"]["scope"],
                aspect=rule["impact"]["aspect"],
                direction=str(rule["impact"].get("direction", "0")),
                effect=rule["impact"]["effect"],
                concepts=frozenset(rule.get("concepts", [])),
                categories=frozenset(rule.get("categories", [])),
            )
            for rule in rules
        )

        places = _load_yaml(universal / "places.yaml").get("places", {})
        self.places: dict[str, PlaceSpec] = {
            key.lower(): PlaceSpec(
                key=key.lower(),
                name=str(spec.get("name", key)),
                kind=spec["kind"],
                city=spec.get("city"),
                country=spec.get("country"),
                neighbours=tuple(spec.get("neighbours", [])),
                organization=tuple(spec.get("organization", [])),
                aliases=tuple(alias.lower() for alias in spec.get("aliases", [])),
            )
            for key, spec in places.items()
        }
        self._place_index = {
            name: place for place in self.places.values() for name in (place.key, *place.aliases)
        }
        self.simulation: dict[str, Any] = _load_yaml(universal / "simulation.yaml")
        self._validate()
        self._languages: dict[str, dict[str, Any]] = {}

    def _validate(self) -> None:
        """Fail at load time on a concept that names an unknown state or role."""
        for concept in self.concepts.values():
            for effect in (*concept.effects, *concept.requires):
                state = self.states.get(effect.state)
                if state is None:
                    raise ValueError(f"{concept.name}: unknown state {effect.state!r}")
                if len(effect.args) != len(state.args):
                    raise ValueError(
                        f"{concept.name}: {effect.state} takes {len(state.args)} args, "
                        f"got {list(effect.args)}"
                    )
                for arg in effect.args:
                    if not arg.startswith("=") and arg not in concept.roles:
                        raise ValueError(f"{concept.name}: unknown role {arg!r}")
        for rule in self.impact_rules:
            unknown = rule.concepts - set(self.concepts)
            if unknown:
                raise ValueError(f"impact rule {rule.effect!r}: unknown concepts {sorted(unknown)}")
            if rule.scope not in {layer.value for layer in LAYERS}:
                raise ValueError(f"impact rule {rule.effect!r}: unknown scope {rule.scope!r}")
        mapped = [
            *(self.simulation.get("properties") or {}).values(),
            *(spec for specs in (self.simulation.get("events") or {}).values() for spec in specs),
        ]
        for spec in mapped:
            state = self.states.get(spec["state"])
            if state is None or len(spec["args"]) != len(state.args):
                raise ValueError(f"simulation.yaml: {spec} does not match a known state")
        for place in self.places.values():
            if place.kind not in PLACE_KINDS:
                raise ValueError(f"place {place.key!r}: unknown kind {place.kind!r}")
            for field_name, kind in (("city", "city"), ("country", "country")):
                ref = getattr(place, field_name)
                if ref is not None and self.places.get(ref.lower(), PlaceSpec("", "", "")).kind != kind:
                    raise ValueError(f"place {place.key!r}: {field_name} {ref!r} is not a {kind} in the gazetteer")

    def language(self, code: str) -> dict[str, Any]:
        if code not in self._languages:
            data = dict(_load_yaml(self.dir / code / "actions.yaml"))
            data["categories"] = _load_yaml(self.dir / code / "categories.yaml").get(
                "categories", {}
            )
            self._languages[code] = data
        return self._languages[code]

    def categories_for(self, lemma: str, language: str) -> set[str]:
        return set(self.language(language)["categories"].get(lemma.lower(), []))

    def impacts_for(self, concept: str | None, categories: set[str]) -> list[ImpactRule]:
        return [rule for rule in self.impact_rules if rule.matches(concept, categories)]

    def place(self, name: str | None) -> PlaceSpec | None:
        return self._place_index.get(name.lower()) if name else None

    def city_of(self, place: PlaceSpec) -> PlaceSpec | None:
        return place if place.kind == "city" else self.place(place.city)

    def country_of(self, place: PlaceSpec) -> PlaceSpec | None:
        if place.kind == "country":
            return place
        if place.country:
            return self.place(place.country)
        city = self.city_of(place)
        return self.place(city.country) if city is not None and city is not place else None

    def concept_for(self, lemma: str, language: str) -> Concept | None:
        name = self.language(language).get("actions", {}).get(lemma.lower())
        return self.concepts.get(name) if name else None

    def is_goal_marker(self, lemma: str, language: str) -> bool:
        return lemma.lower() in set(self.language(language).get("goal_markers", []))


@lru_cache(maxsize=4)
def get_packs(packs_dir: str | None = None) -> ConsequencePacks:
    return ConsequencePacks(packs_dir)
