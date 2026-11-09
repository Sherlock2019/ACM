"""Where analysis and next-scene branches come from.

    DemoProvider    deterministic: returns the authored analysis and branches stored with the
                    scene (``demo:`` in the scene file). Needs nothing else. Source: authored_demo.
    ModelProvider   optional: asks the local LLM already used by ACM (acm.llm, Ollama by default)
                    for branches. Every reply is parsed and validated before it is returned;
                    malformed or empty output, timeouts and an unreachable server raise
                    ProviderError. Source: generated_inference.

Generated branches carry text only: their events do not change the scene state, and they
never carry probabilities. The model provider does not produce an analysis; ACM's analysis of
a scene comes from the demo content (or, for single sentences, from the rule engine).
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import ValidationError

from acm.scene.schema import (
    VERBS, Analysis, Branch, Event, EventType, GoalChange, Inference, Scene, Source, Status, Valence,
)
from acm.scene.validate import SceneError, validate_branch


class ProviderError(RuntimeError):
    pass


class ScenarioProvider(Protocol):
    name: str

    def analyze(self, scene: Scene) -> Analysis: ...

    def branches(self, scene: Scene) -> list[Branch]: ...


class DemoProvider:
    name = "demo"

    def _demo(self, scene: Scene):
        if scene.demo is None:
            raise ProviderError(f"scene {scene.id!r} has no authored demo content")
        return scene.demo

    def analyze(self, scene: Scene) -> Analysis:
        demo = self._demo(scene)
        return Analysis(scene=scene.id, provider=self.name, source=Source.AUTHORED_DEMO,
                        conflicts=demo.conflicts, consequences=demo.consequences)

    def branches(self, scene: Scene) -> list[Branch]:
        branches = self._demo(scene).branches
        if not branches:
            raise ProviderError(f"scene {scene.id!r} has no authored branches")
        return branches


SYSTEM = """You continue a scene script for ACM, the Action-Consequence Model.
You receive the scene as JSON. Propose up to 4 distinct, plausible next scenes.
Rules:
- Use only the actor ids, object ids and mark ids given. Do not invent people.
- Do not claim facts the scene does not establish (for example legal ownership changes).
- Feelings and thoughts are possibilities, never facts.
- No probabilities or likelihood numbers.
Reply with JSON only: {"branches": [{
  "title": str, "assumptions": [str, ...], "summary": str,
  "events": [{"actor": id, "type": "action"|"dialogue", "verb": one of %s or null,
              "target": id or null, "object": id or null, "description": str, "dialogue": str or null}],
  "goal_changes": [{"actor": id, "change": str, "effect": "positive"|"negative"|"mixed"|"undetermined"}],
  "inferences": {"<actor id>": [{"kind": "thought"|"feeling"|"behaviour"|"reaction", "text": str}]},
  "unknowns": [str], "plausibility": str }]}"""


def _script(scene: Scene) -> dict[str, Any]:
    data = scene.model_dump(mode="json", by_alias=True, exclude={"demo", "scopes"})
    return data


def parse_generated(raw: dict[str, Any], scene: Scene) -> tuple[list[Branch], list[str]]:
    """Turn a model reply into validated branches. Returns (branches, rejected reasons)."""
    items = raw.get("branches") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise ProviderError("the model reply has no 'branches' list")
    start = max(e.order for e in scene.events) + 1
    branches: list[Branch] = []
    rejected: list[str] = []
    for i, item in enumerate(items[:4]):
        if not isinstance(item, dict):
            rejected.append(f"item {i}: not an object")
            continue
        bid = f"G{i + 1}"
        try:
            events = []
            for j, ev in enumerate(item.get("events") or []):
                verb = ev.get("verb")
                events.append(Event(
                    id=f"{bid.lower()}_e{j + 1}", order=start + j, actor=ev.get("actor"),
                    type=EventType(ev.get("type", "action")), verb=verb if verb in VERBS else None,
                    target=ev.get("target") or None, object=ev.get("object") or None,
                    description=str(ev.get("description") or "").strip() or "(no description)",
                    dialogue=ev.get("dialogue") or None, source=Source.GENERATED_INFERENCE,
                ))
            inferences = {
                actor: [Inference(kind=x.get("kind", "reaction"), text=str(x.get("text", "")), status=Status.POSSIBLE,
                                  source=Source.GENERATED_INFERENCE) for x in (lst or []) if isinstance(x, dict)]
                for actor, lst in (item.get("inferences") or {}).items()
            }
            branch = Branch(
                id=bid, title=str(item.get("title") or f"Generated branch {i + 1}"), parent=scene.id,
                assumptions=[str(a) for a in item.get("assumptions") or []], summary=str(item.get("summary") or ""),
                events=events,
                goal_changes=[GoalChange(actor=g.get("actor"), change=str(g.get("change", "")),
                                         effect=Valence(g.get("effect", "undetermined")))
                              for g in item.get("goal_changes") or [] if isinstance(g, dict)],
                inferences=inferences, unknowns=[str(u) for u in item.get("unknowns") or []],
                plausibility=str(item.get("plausibility") or "not given by the model"),
                source=Source.GENERATED_INFERENCE,
            )
            validate_branch(branch, scene)
        except (ValidationError, SceneError, ValueError, TypeError, AttributeError) as exc:
            rejected.append(f"item {i}: {str(exc).splitlines()[0][:200]}")
            continue
        branches.append(branch)
    if not branches:
        raise ProviderError("the model returned no valid branch" + (f" ({'; '.join(rejected)})" if rejected else ""))
    return branches, rejected


class ModelProvider:
    name = "model"

    def __init__(self) -> None:
        self.rejected: list[str] = []
        self.model = ""

    def available(self) -> tuple[bool, str]:
        from acm import llm

        return llm.status()

    def analyze(self, scene: Scene) -> Analysis:
        raise ProviderError("the model provider generates branches only; use the demo provider for the analysis")

    def branches(self, scene: Scene) -> list[Branch]:
        from acm import llm

        ok, why = llm.status()
        if not ok:
            raise ProviderError(f"local model unavailable: {why}")
        self.model = why
        try:
            raw, _seconds = llm.chat_json(SYSTEM % sorted(VERBS), json.dumps(_script(scene), ensure_ascii=False))
        except llm.LLMUnavailable as exc:
            raise ProviderError(str(exc)) from exc
        branches, self.rejected = parse_generated(raw, scene)
        return branches


def get_provider(name: str) -> ScenarioProvider:
    if name == "demo":
        return DemoProvider()
    if name == "model":
        return ModelProvider()
    raise ProviderError(f"unknown provider {name!r} (demo | model)")


def generate_branches(scene: Scene, provider: str = "demo", fallback: bool = True) -> dict[str, Any]:
    """Branches from a provider. With ``fallback``, a failing model provider falls back to the
    authored demo branches and the result says so; it is never relabelled as generated."""
    try:
        p = get_provider(provider)
        branches = p.branches(scene)
        return {"provider": p.name, "branches": branches, "fallback": None,
                "rejected": getattr(p, "rejected", []), "model": getattr(p, "model", None)}
    except ProviderError as exc:
        if not fallback or provider == "demo":
            raise
        return {"provider": "demo", "branches": DemoProvider().branches(scene),
                "fallback": f"{exc} - showing the prewritten demo branches instead", "rejected": [], "model": None}
