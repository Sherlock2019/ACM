"""Local SQLite persistence: the simulated environment state and the experience history of runs."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "afm.db"


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or os.environ.get("AFM_DB_PATH") or DEFAULT_DB)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS environment (id TEXT PRIMARY KEY, version INTEGER NOT NULL, state TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS usecases (id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS project_tests (id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self._conn.commit()

    # real-project tests (local only) -------------------------------------------------------------
    def save_project(self, pid: str, updated_at: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO project_tests (id, updated_at, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at, payload = excluded.payload",
                (pid, updated_at, json.dumps(payload)),
            )
            self._conn.commit()

    def get_project(self, pid: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM project_tests WHERE id = ?", (pid,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_projects(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM project_tests ORDER BY updated_at DESC").fetchall()
        return [json.loads(r[0]) for r in rows]

    def delete_project(self, pid: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM project_tests WHERE id = ?", (pid,))
            self._conn.commit()
        return cur.rowcount > 0

    # use cases (builder + chat history; local only, never used for training) ------------------
    def save_usecase(self, uc_id: str, updated_at: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO usecases (id, updated_at, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at, payload = excluded.payload",
                (uc_id, updated_at, json.dumps(payload)),
            )
            self._conn.commit()

    def get_usecase(self, uc_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM usecases WHERE id = ?", (uc_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_usecases(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM usecases ORDER BY updated_at DESC").fetchall()
        return [json.loads(r[0]) for r in rows]

    def delete_usecase(self, uc_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM usecases WHERE id = ?", (uc_id,))
            self._conn.commit()
        return cur.rowcount > 0

    # environment ------------------------------------------------------------------------------
    def load_environment(self, env_id: str) -> tuple[int, dict[str, Any]] | None:
        with self._lock:
            row = self._conn.execute("SELECT version, state FROM environment WHERE id = ?", (env_id,)).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def save_environment(self, env_id: str, version: int, state: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO environment (id, version, state) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET version = excluded.version, state = excluded.state",
                (env_id, version, json.dumps(state)),
            )
            self._conn.commit()

    # runs (experience history) ----------------------------------------------------------------
    def save_run(self, run_id: str, created_at: str, status: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs (run_id, created_at, status, payload) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET status = excluded.status, payload = excluded.payload",
                (run_id, created_at, status, json.dumps(payload)),
            )
            self._conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM runs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]
