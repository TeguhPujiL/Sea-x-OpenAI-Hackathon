"""Typed integration seams; no simulation calculation or review decision logic."""
from dataclasses import dataclass
import json
from typing import Protocol
from uuid import UUID
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.response import ApiError
from app.core.security import Actor, check_version
from app.core.transactions import append_core_audit, case_for, resource_for
from app.models import Simulation, Review, RepairProposal, Finding, SubmittedRepairSnapshot


@dataclass(frozen=True)
class AuditCommand:
    actor: Actor
    request_id: str
    case_id: UUID
    event_type: str
    resource_type: str
    resource_id: UUID
    version: int
    details_json: str = "{}"


class AuditService(Protocol):
    def record(self, session: Session, command: AuditCommand) -> None:
        """Participate in caller transaction; never commit or roll back it."""
        ...


class CoreAuditAdapter:
    """Explicit default delegation to Prompt A's existing atomic core writer.

    Fazhima can supply an AuditService adapter at composition time.
    """
    def record(self, session: Session, command: AuditCommand) -> None:
        append_core_audit(session, command.actor, command.request_id, command.case_id,
            command.event_type, command.resource_type, command.resource_id, command.version,
            json.loads(command.details_json))


@dataclass(frozen=True)
class SimulationSnapshot:
    simulation_id: UUID
    case_id: UUID
    finding_id: UUID
    engine_version: str
    supplier_data_version: str
    input_snapshot_json: str
    result_json: str
    interpretation: str
    created_at: datetime

    def as_context(self) -> dict:
        # Return independent copies, never a mutable ORM JSON object.
        return {"simulation_id": str(self.simulation_id), "engine_version": self.engine_version,
            "supplier_data_version": self.supplier_data_version,
            "input_snapshot": json.loads(self.input_snapshot_json), "result": json.loads(self.result_json)}


class SimulationLookup(Protocol):
    def get(self, session: Session, actor: Actor, case_id: UUID, finding_id: UUID,
            simulation_id: UUID) -> SimulationSnapshot: ...


class StoredSimulationLookup:
    """Read-only default adapter; Aris can replace it without changing routes."""
    def get(self, session, actor, case_id, finding_id, simulation_id):
        finding = resource_for(session, actor, Finding, finding_id)
        if finding.case_id != case_id:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Simulation not found for this finding")
        row = resource_for(session, actor, Simulation, simulation_id)
        if row.case_id != case_id or row.finding_id != finding_id:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Simulation not found for this finding")
        return SimulationSnapshot(row.id, row.case_id, row.finding_id, row.engine_version,
            row.supplier_data_version, json.dumps(row.input_snapshot_json, sort_keys=True),
            json.dumps(row.result_json, sort_keys=True), row.interpretation, row.created_at)


class ReferenceLookup(Protocol):
    def challenge_in_use(self, session: Session, challenge) -> bool: ...
    def repair_in_use(self, session: Session, repair) -> bool: ...


class StoredReferenceLookup:
    def challenge_in_use(self, session, challenge):
        # v1.1 has no challenge FK in downstream requests. Honor any explicit
        # stored snapshot reference; integrators extend this seam for new links.
        for row in session.scalars(select(Simulation).where(Simulation.case_id == challenge.case_id)):
            snapshot = row.input_snapshot_json
            if not isinstance(snapshot, dict):
                return True  # Fail closed on invalid downstream provenance.
            if snapshot.get("challenge_id") == str(challenge.id) or str(challenge.id) in snapshot.get("challenge_ids", []):
                return True
        return False

    def repair_in_use(self, session, repair):
        return session.scalar(select(Review.id).where(Review.repair_proposal_id == repair.id).limit(1)) is not None


@dataclass(frozen=True)
class ReviewCandidate:
    case_id: UUID
    case_version: int
    repair_proposal_id: UUID
    submitted_version: int
    submitted_snapshot_json: str
    simulation: SimulationSnapshot


class ReviewPreconditionValidator(Protocol):
    def validate(self, session: Session, actor: Actor, case_id: UUID,
        repair_proposal_id: UUID, expected_case_version: int) -> ReviewCandidate: ...


class SubmittedRepairPreconditions:
    """Read-only handoff checks. No review, assurance status or audit mutation."""
    def __init__(self, simulations: SimulationLookup):
        self.simulations = simulations

    def validate(self, session, actor, case_id, repair_proposal_id, expected_case_version):
        case = case_for(session, actor, case_id)
        check_version(case.version, expected_case_version)
        repair = resource_for(session, actor, RepairProposal, repair_proposal_id)
        if repair.case_id != case_id:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Repair proposal not found for this case")
        if repair.status != "SUBMITTED":
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Review requires a submitted repair proposal")
        finding = resource_for(session, actor, Finding, repair.finding_id)
        if finding.evidence_status != "VERIFIED" or finding.status not in {"OPEN", "UNDER_REVIEW"}:
            raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Finding evidence is not ready for review")
        from app.services.decision_evidence import sources_for
        sources_for(session, actor, case_id, finding.id)  # Recheck active document/page evidence.
        snapshot = session.get(SubmittedRepairSnapshot, (repair.id, repair.version))
        if snapshot is None:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Submitted snapshot is unavailable")
        simulation = self.simulations.get(session, actor, case_id, finding.id, repair.simulation_id)
        return ReviewCandidate(case_id, case.version, repair.id, snapshot.version,
            json.dumps(snapshot.snapshot_json, sort_keys=True), simulation)
