"""Explicitly provisioned SQLite append-only store; no shared metadata changes."""
import json
import sqlite3
from pathlib import Path
from threading import RLock
from uuid import UUID

from app.services.simulation.engine import canonical_json


class SimulationRepository:
    """Call provision() in deployment setup, never implicitly from an API request.

    INSERT-only application API and SQL triggers reject UPDATE, DELETE and REPLACE.
    A database administrator can still alter schema; production DB roles are an
    integration responsibility. Values returned to callers are fresh JSON copies.
    """

    def __init__(self, path: str | Path):
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._connection.execute("PRAGMA recursive_triggers=ON")

    def provision(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS simulations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    simulation_id TEXT NOT NULL UNIQUE,
                    case_id TEXT NOT NULL,
                    finding_id TEXT NOT NULL,
                    engine_version TEXT NOT NULL,
                    supplier_data_version TEXT NOT NULL,
                    input_snapshot TEXT NOT NULL,
                    result TEXT NOT NULL,
                    interpretation TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS simulations_case_idx ON simulations(case_id, sequence);
                CREATE TRIGGER IF NOT EXISTS simulations_no_update
                    BEFORE UPDATE ON simulations BEGIN
                    SELECT RAISE(ABORT, 'simulation records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS simulations_no_delete
                    BEFORE DELETE ON simulations BEGIN
                    SELECT RAISE(ABORT, 'simulation records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS simulations_no_replace
                    BEFORE INSERT ON simulations
                    WHEN EXISTS (SELECT 1 FROM simulations
                                 WHERE simulation_id=NEW.simulation_id OR sequence=NEW.sequence)
                    BEGIN SELECT RAISE(ABORT, 'simulation records are immutable'); END;
            """)

    def add(self, record: dict) -> None:
        values = {key: canonical_json(value) if key in {"input_snapshot", "result"} else value
                  for key, value in record.items()}
        with self._lock, self._connection:
            self._connection.execute("""
                INSERT INTO simulations
                (simulation_id, case_id, finding_id, engine_version, supplier_data_version,
                 input_snapshot, result, interpretation, created_at)
                VALUES (:simulation_id, :case_id, :finding_id, :engine_version,
                        :supplier_data_version, :input_snapshot, :result, :interpretation, :created_at)
            """, values)

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        record = dict(row)
        record.pop("sequence")
        for key in ("input_snapshot", "result"):
            record[key] = json.loads(record[key])
        return record

    def get(self, simulation_id: UUID) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM simulations WHERE simulation_id=?", (str(simulation_id),)
            ).fetchone()
        return None if row is None else self._decode(row)

    def list_for_case(self, case_id: UUID) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM simulations WHERE case_id=? ORDER BY sequence", (str(case_id),)
            ).fetchall()
        return [self._decode(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()
