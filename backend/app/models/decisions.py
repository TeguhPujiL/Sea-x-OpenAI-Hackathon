"""Decision-generation idempotency leases and immutable submitted content."""
from sqlalchemy import Column, ForeignKey, JSON, String, Integer, CheckConstraint, DDL, event
from sqlalchemy.orm import Session
from app.models.base import Base, Created, UuidV4, UtcDateTime


class GenerationLease(Base):
    __tablename__ = "generation_leases"
    actor_id = Column(UuidV4, primary_key=True)
    route = Column(String, primary_key=True)
    key = Column(String, primary_key=True)
    request_hash = Column(String(64), nullable=False)
    token = Column(UuidV4, nullable=False)
    expires_at = Column(UtcDateTime, nullable=False)


class SubmittedRepairSnapshot(Created, Base):
    __tablename__ = "submitted_repair_snapshots"
    repair_proposal_id = Column(UuidV4, ForeignKey("repair_proposals.id"), primary_key=True)
    version = Column(Integer, primary_key=True)
    snapshot_json = Column(JSON, nullable=False)
    __table_args__ = (CheckConstraint("version >= 1", name="positive_snapshot_version"),)


@event.listens_for(Session, "before_flush")
def immutable_snapshots(session, _context, _instances):
    for row in list(session.deleted) + [r for r in session.dirty if session.is_modified(r)]:
        if isinstance(row, SubmittedRepairSnapshot):
            raise ValueError("Submitted repair snapshots are immutable")


def install_decision_guards(connection):
    for operation in ("UPDATE", "DELETE"):
        connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS submitted_repair_no_{operation.lower()} BEFORE {operation} ON submitted_repair_snapshots BEGIN SELECT RAISE(ABORT, 'submitted repair immutable'); END")
    fields = ("proposed_text", "justification", "human_edits", "deleted_at")
    condition = " OR ".join(f"NEW.{field} IS NOT OLD.{field}" for field in fields)
    connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS repair_submitted_content BEFORE UPDATE ON repair_proposals WHEN OLD.status != 'DRAFT' AND ({condition}) BEGIN SELECT RAISE(ABORT, 'submitted repair content frozen'); END")
    for table, fields in {
        "repair_proposals": ("id", "case_id", "finding_id", "action_type", "before_text", "simulation_id", "ai_execution_id", "created_at"),
        "challenges": ("id", "case_id", "finding_id", "risk_rationale", "requested_evidence_json", "ai_execution_id", "created_at"),
    }.items():
        condition = " OR ".join(f"NEW.{field} IS NOT OLD.{field}" for field in fields)
        connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_source_frozen BEFORE UPDATE ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT, 'decision source frozen'); END")
        connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_no_physical_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'use eligible soft delete'); END")
    connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS challenge_closed_frozen BEFORE UPDATE ON challenges WHEN OLD.status='CLOSED' BEGIN SELECT RAISE(ABORT, 'closed challenge frozen'); END")
