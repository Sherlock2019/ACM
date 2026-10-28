"""A small graph + vector database for action graphs.

Every analysed action can be remembered: its nodes (with vectors) and edges go
into SQLite, so ARM can later ask "which past actions looked like this one?" or
"what has ever happened to Sarah?" across everything it has seen.

Search is exact cosine similarity over all stored vectors with numpy. That is fine
for thousands of nodes; a real vector index (FAISS, pgvector) is the upgrade path
once the store outgrows it, behind the same methods.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from acm.schema import ConsequenceReport

SCHEMA = """
CREATE TABLE IF NOT EXISTS graphs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    language TEXT,
    concept TEXT,
    actor TEXT,
    report TEXT NOT NULL,
    created TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS nodes (
    graph_id INTEGER NOT NULL REFERENCES graphs(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    vector TEXT NOT NULL,
    PRIMARY KEY (graph_id, node_id)
);
CREATE TABLE IF NOT EXISTS edges (
    graph_id INTEGER NOT NULL REFERENCES graphs(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    relation TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS nodes_id ON nodes(node_id);
"""


class GraphVectorStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    # -- writing -----------------------------------------------------------

    def add(self, report: ConsequenceReport) -> int:
        """Store one report's graph; returns its graph id."""
        cursor = self._db.execute(
            "INSERT INTO graphs (text, language, concept, actor, report) VALUES (?, ?, ?, ?, ?)",
            (
                report.action_text,
                report.language,
                report.concept,
                report.actor,
                report.model_dump_json(exclude={"graph"}),
            ),
        )
        graph_id = int(cursor.lastrowid)
        self._db.executemany(
            "INSERT INTO nodes (graph_id, node_id, kind, label, vector) VALUES (?, ?, ?, ?, ?)",
            [
                (graph_id, node["id"], node["kind"], node["label"], json.dumps(node["vector"]))
                for node in report.graph.get("nodes", [])
            ],
        )
        self._db.executemany(
            "INSERT INTO edges (graph_id, source, target, relation) VALUES (?, ?, ?, ?)",
            [
                (graph_id, edge["source"], edge["target"], edge["relation"])
                for edge in report.graph.get("edges", [])
            ],
        )
        self._db.commit()
        return graph_id

    # -- reading -----------------------------------------------------------

    def search(
        self, vector: Sequence[float], *, k: int = 5, kind: str | None = None
    ) -> list[dict[str, Any]]:
        """The ``k`` stored nodes most similar to ``vector`` (cosine)."""
        query = "SELECT n.graph_id, n.node_id, n.kind, n.label, n.vector, g.text FROM nodes n JOIN graphs g ON g.id = n.graph_id"
        params: tuple[Any, ...] = ()
        if kind:
            query += " WHERE n.kind = ?"
            params = (kind,)
        rows = self._db.execute(query, params).fetchall()
        if not rows:
            return []
        matrix = np.array([json.loads(row["vector"]) for row in rows], dtype=float)
        target = np.asarray(vector, dtype=float)
        norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(target) or 1.0)
        scores = matrix @ target / np.where(norms == 0, 1.0, norms)
        best = np.argsort(-scores)[:k]
        return [
            {
                "graph_id": rows[i]["graph_id"],
                "node_id": rows[i]["node_id"],
                "kind": rows[i]["kind"],
                "label": rows[i]["label"],
                "text": rows[i]["text"],
                "score": round(float(scores[i]), 4),
            }
            for i in best
        ]

    def similar_actions(self, report: ConsequenceReport, *, k: int = 5) -> list[dict[str, Any]]:
        """Stored actions whose action node is closest to this report's."""
        action = next((n for n in report.graph.get("nodes", []) if n["id"] == "action"), None)
        return [] if action is None else self.search(action["vector"], k=k, kind="action")

    def history(self, entity_key: str) -> list[dict[str, Any]]:
        """Every stored state change or relation that touched an entity."""
        rows = self._db.execute(
            """
            SELECT g.id AS graph_id, g.text, e.relation, n.label
            FROM edges e
            JOIN graphs g ON g.id = e.graph_id
            JOIN nodes n ON n.graph_id = e.graph_id AND n.node_id = e.source
            WHERE e.target = ? OR e.source = ?
            ORDER BY g.id
            """,
            (f"e:{entity_key}", f"e:{entity_key}"),
        ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, int]:
        count = lambda table: int(self._db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: E731
        return {"graphs": count("graphs"), "nodes": count("nodes"), "edges": count("edges")}
