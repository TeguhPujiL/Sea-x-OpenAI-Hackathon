"""Simulation-owned adapter using existing shared tables and one transaction."""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.response import success
from app.core.security import Actor
from app.models import AuditEvent, Case, Finding, IdempotencyRecord, Simulation
from app.schemas.shared import UtcTimestamp
from pydantic import TypeAdapter
from app.services.simulation.engine import SimulationError
from app.services.simulation.models import to_wire_record


@dataclass(frozen=True)
class CreationContext:
    actor: Actor
    key: str
    route: str
    request_id: str


def verify_references(session, case_id: UUID, finding_id: UUID | None = None):
    case = session.get(Case, case_id)
    if case is None or case.deleted_at is not None:
        raise SimulationError("Case not found", code="RESOURCE_NOT_FOUND", status_code=404)
    if finding_id is not None:
        finding = session.get(Finding, finding_id)
        if finding is None or finding.case_id != case_id:
            # Same mapping for missing and cross-case IDs avoids disclosing another case.
            raise SimulationError("Finding not found for case", code="RESOURCE_NOT_FOUND", status_code=404)


class PersistedSimulationAccess:
    """Combine a trusted ACL adapter with real persisted resource relationships."""

    def __init__(self, factory, policy):
        self.factory = factory
        self.policy = policy

    def require_case(self, case_id):
        self.policy.require_case(case_id)
        with self.factory() as session:
            verify_references(session, case_id)

    def require_finding(self, case_id, finding_id):
        self.policy.require_finding(case_id, finding_id)
        with self.factory() as session:
            verify_references(session, case_id, finding_id)


class SharedSimulationRepository:
    def __init__(self, factory):
        self.factory = factory

    @staticmethod
    def _decode(row):
        return {
            "simulation_id": str(row.id), "case_id": str(row.case_id),
            "finding_id": str(row.finding_id), "engine_version": row.engine_version,
            "supplier_data_version": row.supplier_data_version,
            "input_snapshot": json.loads(json.dumps(row.input_snapshot_json)),
            "result": json.loads(json.dumps(row.result_json)),
            "interpretation": row.interpretation,
            "created_at": TypeAdapter(UtcTimestamp).dump_python(row.created_at, mode="json"),
        }

    @staticmethod
    def _key_query(context):
        return select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == context.actor.actor_id,
            IdempotencyRecord.method == "POST", IdempotencyRecord.route == context.route,
            IdempotencyRecord.key == context.key,
        )

    @staticmethod
    def _replay(existing, request_hash):
        if existing.request_hash != request_hash:
            raise SimulationError("Idempotency key was used with different input",
                                  code="IDEMPOTENCY_KEY_REUSED", status_code=409)
        return json.loads(json.dumps(existing.response_body))

    def replay_if_present(self, case_id, finding_id, context, request_hash):
        with self.factory() as session:
            verify_references(session, case_id, finding_id)
            existing = session.scalar(self._key_query(context))
            return None if existing is None else self._replay(existing, request_hash)

    def create_atomic(self, record, context, request_hash):
        try:
            with self.factory() as session, session.begin():
                if session.bind.dialect.name == "sqlite":
                    # Serialize SQLite writers before reading the idempotency key.
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                # Recheck live references inside the write transaction, including replay.
                verify_references(session, UUID(record["case_id"]), UUID(record["finding_id"]))
                existing = session.scalar(self._key_query(context))
                if existing is not None:
                    return self._replay(existing, request_hash)
                session.add(Simulation(
                    id=UUID(record["simulation_id"]), case_id=UUID(record["case_id"]),
                    finding_id=UUID(record["finding_id"]), engine_version=record["engine_version"],
                    supplier_data_version=record["supplier_data_version"],
                    input_snapshot_json=record["input_snapshot"], result_json=record["result"],
                    interpretation=record["interpretation"],
                    created_at=datetime.fromisoformat(record["created_at"].replace("Z", "+00:00")),
                ))
                session.flush()
                session.add(AuditEvent(
                    case_id=UUID(record["case_id"]), actor_id=context.actor.actor_id,
                    request_id=context.request_id, event_type="SIMULATION_CREATED",
                    resource_type="simulation", resource_id=UUID(record["simulation_id"]),
                    resource_version=1, occurred_at=datetime.now(timezone.utc),
                    details_json={"engine_version": record["engine_version"],
                                  "supplier_data_version": record["supplier_data_version"],
                                  "finding_id": record["finding_id"],
                                  "input_hash": record["input_snapshot"]["provenance"]["input_hash"],
                                  "baseline": record["input_snapshot"]["baseline"],
                                  "alternative": record["input_snapshot"]["alternative"]},
                ))
                # G07: version is persisted in the snapshot; do not add it to outer wire fields.
                wire_record = to_wire_record(record)
                body = json.loads(success(wire_record, context.request_id, status=201).body)
                session.add(IdempotencyRecord(
                    actor_id=context.actor.actor_id, method="POST", route=context.route,
                    key=context.key, request_hash=request_hash,
                    response_status=201, response_body=body,
                ))
                session.flush()
                return body
        except IntegrityError:
            # Unique key race: after rollback read the committed winner. Never retry writes blindly.
            with self.factory() as session:
                existing = session.scalar(self._key_query(context))
                if existing is not None:
                    return self._replay(existing, request_hash)
            raise

    def get(self, simulation_id):
        with self.factory() as session:
            row = session.get(Simulation, simulation_id)
            return None if row is None else self._decode(row)

    def list_for_case(self, case_id):
        return self.page_for_case(case_id, limit=None, offset=0)[0]

    def page_for_case(self, case_id, limit=20, offset=0):
        with self.factory() as session:
            total = session.scalar(select(func.count()).select_from(Simulation).where(Simulation.case_id == case_id))
            query = select(Simulation).where(Simulation.case_id == case_id).order_by(Simulation.created_at, Simulation.id).offset(offset)
            if limit is not None:
                query = query.limit(limit)
            return [self._decode(row) for row in session.scalars(query)], total
