"""ACM's world model as a layer stack, and the consequence router.

The stack is read bottom-up, like the OSI network model it borrows its shape from: an action
or event is the source; it happens in the physical world, is perceived, is routed to the world
models that should examine it, and from there its consequences are examined for people,
digital systems, institutions, society and the planet.

    0  Action or event            who acts, why, their goal and desired outcome, what happens
    1  Physical world             objects, materials, movement, forces, location, energy
    2  Perception and observation images, video, audio, speech, sensors, observations
    3  Consequence routing        which world models, actors and systems examine an event
    4  Human and social           goals, behaviour, dialogue, relationships, group reactions
    5  Digital and information    applications, records, calculations, permissions, workflows
    6  Business and institutions  organisations, operations, processes, finance, policies
    7  Society and collective     economy, markets, society, public governance, politics
    8  Planetary and ecosystem    resources, pollution, biodiversity, sustainability

Layers are a second axis next to the scene's scopes (the radius rings): a layer says which
kind of system a consequence is about and which model examines it; a scope says how far it
reaches. Every consequence has one layer (1-2 or 4-8); levels 0 and 3 carry events and routes.

The OSI column is an analogy for the shape of the stack, not a claim that networking concepts
apply. ``engine`` says honestly what in ACM examines each layer today.
"""

from __future__ import annotations

from typing import Any

from acm.scene.schema import CONSEQUENCE_LAYERS, Event, EventType, Layer, Scene

__all__ = ["CONSEQUENCE_LAYERS", "LAYERS", "LAYER_IDS", "Layer", "route", "route_event"]

#: status: working · partial (some of it is modelled) · planned (not integrated)
LAYERS: list[dict[str, Any]] = [
    {"level": 0, "id": "action", "icon": "🎬", "name": "Action or event",
     "examines": "Who acts, why, their goal and desired outcome, and what happens",
     "osi": "Source", "osi_role": "A networking application creates or receives information",
     "engine": "The scene script (acm.scene): actors, goals, ordered events and their state changes; "
               "single sentences are parsed by MLM's phrase model",
     "status": "working"},
    {"level": 1, "id": "physical", "icon": "⚙️", "name": "Physical world",
     "examines": "Objects, materials, movement, forces, location and energy",
     "osi": "Physical", "osi_role": "Transmits raw bits as signals over a physical medium",
     "engine": "Scene state tracks positions, holders and owners (2D player). Forces and materials: a 2D matter.js "
               "stand-in in the Image/Video chat; a 3D physics engine (Unreal Engine 5, Chaos) is planned",
     "status": "partial"},
    {"level": 2, "id": "perception", "icon": "👁️", "name": "Perception and observation",
     "examines": "Images, video, audio, speech, sensors and observations",
     "osi": "Data Link", "osi_role": "Transfers frames across a local network link",
     "engine": "Scene observations and who can see or hear each event. Image/video recognition in the Image/Video chat "
               "uses replayed detections; a vision-language model and detector are planned",
     "status": "partial"},
    {"level": 3, "id": "routing", "icon": "🧭", "name": "Consequence routing",
     "examines": "Determines which world models, actors and systems should examine an event",
     "osi": "Network", "osi_role": "Addresses and routes packets across networks (routing)",
     "engine": "acm.scene.layers.route: explicit rules over each event's verb, type, objects and effects, plus the "
               "events each consequence cites as evidence",
     "status": "working"},
    {"level": 4, "id": "human_social", "icon": "🧠", "name": "Human and social",
     "examines": "Goals, behaviour, dialogue, relationships and group reactions",
     "osi": "Transport", "osi_role": "Provides end-to-end data transport between applications",
     "engine": "The script model (goals, stated positions, possible feelings, conflicts) and next scenes from the "
               "authored demo or the local next-action model",
     "status": "working"},
    {"level": 5, "id": "digital", "icon": "💻", "name": "Digital and information systems",
     "examines": "Applications, records, calculations, permissions and workflows",
     "osi": "Session", "osi_role": "Establishes, manages and ends communication sessions",
     "engine": "Explicit state changes and calculations (rule engine: has(x, y), amounts). No external system "
               "(registry, bank) is connected",
     "status": "partial"},
    {"level": 6, "id": "business", "icon": "🏭", "name": "Business and institutions",
     "examines": "Organisations, operations, processes, finance and policies",
     "osi": "Presentation", "osi_role": "Represents or transforms data, including formats and encoding",
     "engine": "Obligations in the scene (debts, agreements) and the rule engine's organisation-scoped impact rules",
     "status": "partial"},
    {"level": 7, "id": "society", "icon": "🏛️", "name": "Society and collective systems",
     "examines": "Economy, markets, society, public governance and politics",
     "osi": "Application", "osi_role": "Provides network services used by applications, such as web and email",
     "engine": "The rule engine's society- and country-scoped impact rules. No economic or political model yet",
     "status": "partial"},
    {"level": 8, "id": "planetary", "icon": "🌍", "name": "Planetary and ecosystem",
     "examines": "Resources, pollution, biodiversity and sustainability",
     "osi": "Beyond the stack", "osi_role": "(no OSI layer: the outermost system every other one depends on)",
     "engine": "The rule engine's earth-scoped impact rules (e.g. flying and emissions). No ecosystem model yet",
     "status": "partial"},
]

LAYER_IDS = [l["id"] for l in LAYERS]
assert LAYER_IDS == [l.value for l in Layer]

PHYSICAL_VERBS = {"move", "hold", "offer", "place", "take", "gesture"}


def _add(routes: dict[str, dict[str, Any]], layer: Layer, reason: str, actors=(), objects=()) -> None:
    r = routes.setdefault(layer.value, {"layer": layer.value, "actors": [], "objects": [], "reasons": []})
    for a in actors:
        if a and a not in r["actors"]:
            r["actors"].append(a)
    for o in objects:
        if o and o not in r["objects"]:
            r["objects"].append(o)
    if reason not in r["reasons"]:
        r["reasons"].append(reason)


def route_event(scene: Scene, event: Event, consequences: list | None = None) -> list[dict[str, Any]]:
    """Which world layers, actors and objects should examine ``event``, and why.

    Rules (each route lists the ones that fired):
      physical      a physical verb, a physical object, or a change of position or holder
      perception    every event is seen or heard by the others present (speech: heard)
      human_social  dialogue, or an action aimed at a person
      human_social  an object owned by someone other than the actor: the owner is involved
      digital       a change to an owned object or an obligation: records and calculations
      business      an obligation (debt, agreement) is involved
      any layer     a consequence at that layer cites this event as evidence
    """
    actors = {a.id for a in scene.actors}
    objects = {o.id: o for o in scene.objects}
    others = [a.id for a in scene.actors if a.id != event.actor]
    touched = [x for x in (event.object, event.target) if x in objects]
    touched += [c.subject for c in event.effects if c.subject in objects and c.subject not in touched]
    routes: dict[str, dict[str, Any]] = {}

    physical_objects = [o for o in touched if objects[o].kind == "physical"]
    moves = [c for c in event.effects if c.attribute in ("position", "holder")]
    if event.verb in PHYSICAL_VERBS or physical_objects or moves:
        why = (f"physical verb '{event.verb}'" if event.verb in PHYSICAL_VERBS
               else "changes a position or holder" if moves else "involves a physical object")
        _add(routes, Layer.PHYSICAL, why, actors=[event.actor] if event.actor else [],
             objects=physical_objects + [c.subject for c in moves if c.subject in objects])

    if event.type == EventType.DIALOGUE:
        _add(routes, Layer.PERCEPTION, "speech: heard by the others present", actors=others)
    elif event.type == EventType.OBSERVATION:
        _add(routes, Layer.PERCEPTION, "an observation of the scene", actors=sorted(actors))
    else:
        _add(routes, Layer.PERCEPTION, "visible to the others present", actors=others)

    if event.type == EventType.DIALOGUE:
        _add(routes, Layer.HUMAN_SOCIAL, "dialogue between people",
             actors=[event.actor, event.target if event.target in actors else None])
    elif event.target in actors:
        _add(routes, Layer.HUMAN_SOCIAL, "an action aimed at a person", actors=[event.actor, event.target])

    for o in touched:
        obj = objects[o]
        if obj.owner and obj.owner != event.actor and event.actor:
            _add(routes, Layer.HUMAN_SOCIAL, f"{obj.label} belongs to someone other than the actor",
                 actors=[obj.owner, event.actor], objects=[o])
        if obj.kind == "obligation":
            _add(routes, Layer.BUSINESS, f"involves an obligation ({obj.label})", objects=[o])
            _add(routes, Layer.DIGITAL, f"amounts and records of {obj.label}", objects=[o])
        elif obj.owner and any(c.subject == o for c in event.effects):
            _add(routes, Layer.DIGITAL, f"changes the status of an owned object ({obj.label}): records may apply",
                 objects=[o])

    for c in consequences or []:
        if event.id in c.evidence:
            layer = Layer(c.layer)
            _add(routes, layer, f"consequence {c.id} cites it",
                 actors=[a for a in c.affected if a in actors], objects=[a for a in c.affected if a in objects])

    order = {l: i for i, l in enumerate(LAYER_IDS)}
    return sorted(routes.values(), key=lambda r: order[r["layer"]])


def route(scene: Scene, events: list[Event] | None = None, consequences: list | None = None) -> list[dict[str, Any]]:
    """The routing table: for each event, the layers (with actors, objects, reasons) it goes to."""
    return [{"event": e.id, "routes": route_event(scene, e, consequences)} for e in (events or scene.events)]
