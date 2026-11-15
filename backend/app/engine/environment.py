"""Generic environment state + store. The store holds one adapter's simulated state and its version.

The catalog is a representation of the KNOWN environment. It never includes every real dependency.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..domain.models import EnvironmentView, EnvObject, Relationship
from ..storage.db import Database

if TYPE_CHECKING:
    from ..adapters.base import EnvironmentAdapter

COMPLETENESS_NOTE = (
    "This catalog lists the objects and relationships AFM knows about in this environment. "
    "It is not proof that every dependency has been discovered."
)


@dataclass
class EnvState:
    objects: dict[str, EnvObject]
    relationships: list[Relationship] = field(default_factory=list)

    def copy(self) -> "EnvState":
        return EnvState(
            objects={k: v.model_copy(deep=True) for k, v in self.objects.items()},
            relationships=[r.model_copy(deep=True) for r in self.relationships],
        )

    def to_dict(self) -> dict:
        return {
            "objects": [o.model_dump(mode="json") for o in self.objects.values()],
            "relationships": [r.model_dump(mode="json") for r in self.relationships],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EnvState":
        objs = [EnvObject.model_validate(o) for o in d["objects"]]
        rels = [Relationship.model_validate(r) for r in d["relationships"]]
        return cls(objects={o.id: o for o in objs}, relationships=rels)

    def fingerprint(self) -> str:
        """Hash of business state + relationships (not timestamps): detects any change since a prediction."""
        payload = {
            "objects": {k: o.state for k, o in sorted(self.objects.items())},
            "relationships": sorted(r.id for r in self.relationships),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


class EnvironmentStore:
    """Holds one environment's live simulated state. Version increases on every change (including reset)."""

    def __init__(self, db: Database, adapter: "EnvironmentAdapter"):
        self.adapter = adapter
        self.env_id = adapter.environment_id
        self.db = db
        self.lock = threading.RLock()
        saved = db.load_environment(self.env_id)
        if saved:
            self.version, data = saved
            self._state = EnvState.from_dict(data)
        else:
            self.version = 1
            self._state = adapter.initial_state()
            self._persist()

    def _persist(self) -> None:
        self.db.save_environment(self.env_id, self.version, self._state.to_dict())

    def snapshot(self) -> EnvState:
        with self.lock:
            return self._state.copy()

    def fingerprint(self) -> str:
        with self.lock:
            return self._state.fingerprint()

    def commit(self, new_state: EnvState) -> int:
        with self.lock:
            self._state = new_state.copy()
            self.version += 1
            self._persist()
            return self.version

    def reset(self) -> int:
        """Restore the adapter's initial scenario. Changes only this local simulated environment."""
        return self.commit(self.adapter.initial_state())

    def view(self) -> EnvironmentView:
        with self.lock:
            s = self._state
            return EnvironmentView(
                environment_id=self.env_id, name=self.adapter.name, kind=self.adapter.kind,
                version=self.version, fingerprint=s.fingerprint(),
                objects=[o.model_copy(deep=True) for o in s.objects.values()],
                relationships=[r.model_copy(deep=True) for r in s.relationships],
                completeness_note=COMPLETENESS_NOTE, layout=self.adapter.layout(),
            )
