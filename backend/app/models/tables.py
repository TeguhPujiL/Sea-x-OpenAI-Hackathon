"""Shared persistence declarations, not feature services or wire response schemas.

No tables are created on application startup. Use init_db only for an empty demo DB.
Feature owners must supply reviewed migrations and transactional commands.
"""
from sqlalchemy import CheckConstraint, Column, DDL, Enum as SqlEnum, ForeignKey, Integer, Float, JSON, String, Text, UniqueConstraint, Boolean, event
from sqlalchemy.orm import Session

from app.models.base import Base, Created, Identity, Mutable, SoftDeleted, UtcDateTime, UuidV4
from app.schemas.shared import (AnalysisType, AssuranceStatus, CaseStatus, ChallengeStatus,
    DocumentType, EvidenceStatus, FindingSeverity, FindingStatus, ProcessingStatus,
    RepairActionType, RepairStatus, ReviewDecision)


def enum_type(enum):
    return SqlEnum(enum, values_callable=lambda cls: [e.value for e in cls],
                   native_enum=False, create_constraint=True, validate_strings=True)


class Case(Identity, Mutable, SoftDeleted, Base):
    __tablename__ = "cases"
    case_number = Column(String, nullable=False, unique=True)
    title = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    quantity = Column(Integer, nullable=False)
    budget_ceiling_idr = Column(Integer, nullable=False)
    currency = Column(String, nullable=False, default="IDR")
    case_status = Column(enum_type(CaseStatus), nullable=False, default=CaseStatus.DRAFT)
    assurance_status = Column(enum_type(AssuranceStatus), nullable=False, default=AssuranceStatus.ACTION_REQUIRED)
    __table_args__ = (CheckConstraint("quantity > 0", name="positive_quantity"), CheckConstraint("budget_ceiling_idr >= 0 AND typeof(budget_ceiling_idr) = 'integer'", name="integer_budget"), CheckConstraint("version >= 1", name="positive_version"), CheckConstraint("currency = 'IDR'", name="idr_currency"))


class Document(Identity, Mutable, SoftDeleted, Base):
    __tablename__ = "documents"
    case_id = Column(UuidV4, ForeignKey("cases.id"), nullable=False, index=True)
    document_type = Column(enum_type(DocumentType), nullable=False)
    filename = Column(Text, nullable=False)
    description = Column(Text)
    storage_key = Column(String, nullable=False, unique=True)
    sha256 = Column(String(64), nullable=False)
    mime_type = Column(String, nullable=False, default="application/pdf")
    size_bytes = Column(Integer, nullable=False)
    page_count = Column(Integer, nullable=False)
    processing_status = Column(enum_type(ProcessingStatus), nullable=False, default=ProcessingStatus.QUEUED)
    uploaded_at = Column(UtcDateTime, nullable=False)
    __table_args__ = (CheckConstraint("page_count >= 1", name="positive_pages"), CheckConstraint("size_bytes > 0", name="positive_bytes"), CheckConstraint("version >= 1", name="positive_version"))


class DocumentPage(Identity, Base):
    __tablename__ = "document_pages"
    document_id = Column(UuidV4, ForeignKey("documents.id"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    normalized_text = Column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("document_id", "page_number"), CheckConstraint("page_number >= 1", name="one_based_page"))


class AnalysisJob(Identity, Created, Base):
    __tablename__ = "analysis_jobs"
    case_id = Column(UuidV4, ForeignKey("cases.id"), nullable=False, index=True)
    analysis_types = Column(JSON, nullable=False)
    input_document_ids_json = Column(JSON, nullable=False, default=list)
    requirements_json = Column(JSON)
    actor_id = Column(UuidV4)
    request_id = Column(String)
    processing_status = Column(enum_type(ProcessingStatus), nullable=False, default=ProcessingStatus.QUEUED)
    progress_percent = Column(Integer, nullable=False, default=0)
    result_json = Column(JSON)
    warnings_json = Column(JSON, nullable=False, default=list)
    error_json = Column(JSON)
    retry_of_job_id = Column(UuidV4, ForeignKey("analysis_jobs.id"))
    started_at = Column(UtcDateTime)
    completed_at = Column(UtcDateTime)
    __table_args__ = (CheckConstraint("progress_percent BETWEEN 0 AND 100", name="valid_progress"),)


class AiExecution(Identity, Created, Base):
    __tablename__ = "ai_executions"
    job_id = Column(UuidV4, ForeignKey("analysis_jobs.id"))
    case_id = Column(UuidV4, ForeignKey("cases.id"), nullable=False)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=True)  # Null when no provider response was received.
    requested_model = Column(String)
    operation = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    input_document_ids_json = Column(JSON, nullable=False)
    schema_valid = Column(Boolean, nullable=False)
    evidence_validation_passed = Column(Boolean, nullable=False)
    evidence_checks_json = Column(JSON, nullable=False)
    warnings_json = Column(JSON, nullable=False, default=list)
    latency_ms = Column(Integer, nullable=False)
    usage_json = Column(JSON)
    __table_args__ = (CheckConstraint("latency_ms >= 0", name="nonnegative_latency"),)


class Finding(Identity, Mutable, Base):
    __tablename__ = "findings"
    case_id = Column(UuidV4, ForeignKey("cases.id"), nullable=False, index=True)
    analysis_job_id = Column(UuidV4, ForeignKey("analysis_jobs.id"), nullable=False)
    ai_execution_id = Column(UuidV4, ForeignKey("ai_executions.id"), nullable=False)
    type = Column(String, nullable=False)
    severity = Column(enum_type(FindingSeverity), nullable=False)
    status = Column(enum_type(FindingStatus), nullable=False, default=FindingStatus.OPEN)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    evidence_status = Column(enum_type(EvidenceStatus), nullable=False)
    assignee_id = Column(UuidV4)
    resolution_note = Column(Text)
    __table_args__ = (CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"), CheckConstraint("version >= 1", name="positive_version"))


class EvidenceRef(Identity, Base):
    __tablename__ = "evidence_refs"
    finding_id = Column(UuidV4, ForeignKey("findings.id"), nullable=False)
    document_id = Column(UuidV4, ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    excerpt = Column(Text, nullable=False)
    verification_status = Column(enum_type(EvidenceStatus), nullable=False)
    __table_args__ = (CheckConstraint("page_number >= 1", name="one_based_page"),)


class Challenge(Identity, Mutable, SoftDeleted, Base):
    __tablename__ = "challenges"
    case_id = Column(UuidV4, ForeignKey("cases.id"), nullable=False)
    finding_id = Column(UuidV4, ForeignKey("findings.id"), nullable=False)
    status = Column(enum_type(ChallengeStatus), nullable=False, default=ChallengeStatus.DRAFT)
    question = Column(Text, nullable=False)
    risk_rationale = Column(Text, nullable=False)
    requested_evidence_json = Column(JSON, nullable=False)
    ai_execution_id = Column(UuidV4, ForeignKey("ai_executions.id"))
    human_edits = Column(Boolean, nullable=False, default=False)
    __table_args__ = (CheckConstraint("version >= 1", name="positive_version"),)


class SupplierFixture(Base):
    __tablename__ = "supplier_fixtures"
    data_version = Column(String, primary_key=True)
    supplier_ref = Column(String, primary_key=True)
    ram_gb = Column(Integer, nullable=False)
    unit_price_idr = Column(Integer, nullable=False)
    __table_args__ = (CheckConstraint("ram_gb > 0", name="positive_ram"), CheckConstraint("unit_price_idr >= 0 AND typeof(unit_price_idr) = 'integer'", name="integer_price"))


class Simulation(Identity, Created, Base):
    __tablename__ = "simulations"
    case_id = Column(UuidV4, ForeignKey("cases.id"), nullable=False)
    finding_id = Column(UuidV4, ForeignKey("findings.id"), nullable=False)
    engine_version = Column(String, nullable=False)
    supplier_data_version = Column(String, nullable=False)
    input_snapshot_json = Column(JSON, nullable=False)
    result_json = Column(JSON, nullable=False)
    interpretation = Column(Text, nullable=False)


class RepairProposal(Identity, Mutable, SoftDeleted, Base):
    __tablename__ = "repair_proposals"
    case_id = Column(UuidV4, ForeignKey("cases.id"), nullable=False)
    finding_id = Column(UuidV4, ForeignKey("findings.id"), nullable=False)
    status = Column(enum_type(RepairStatus), nullable=False, default=RepairStatus.DRAFT)
    action_type = Column(enum_type(RepairActionType), nullable=False)
    before_text = Column(Text, nullable=False)
    proposed_text = Column(Text, nullable=False)
    justification = Column(Text, nullable=False)
    simulation_id = Column(UuidV4, ForeignKey("simulations.id"))
    ai_execution_id = Column(UuidV4, ForeignKey("ai_executions.id"))
    human_edits = Column(Boolean, nullable=False, default=False)
    __table_args__ = (CheckConstraint("version >= 1", name="positive_version"),)


class Review(Identity, Created, Base):
    __tablename__ = "reviews"
    case_id = Column(UuidV4, ForeignKey("cases.id"), nullable=False)
    repair_proposal_id = Column(UuidV4, ForeignKey("repair_proposals.id"), nullable=False)
    decision = Column(enum_type(ReviewDecision), nullable=False)
    decision_reason = Column(Text, nullable=False)
    review_status = Column(String, nullable=False, default="COMPLETED")
    reviewer_actor_id = Column(UuidV4, nullable=False)
    reviewer_snapshot_json = Column(JSON, nullable=False)
    assurance_status_after = Column(enum_type(AssuranceStatus), nullable=False)
    __table_args__ = (CheckConstraint("review_status = 'COMPLETED'", name="completed_review"),)


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    case_id = Column(UuidV4, ForeignKey("cases.id"), nullable=False)
    actor_id = Column(UuidV4, nullable=False)
    request_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(UuidV4, nullable=False)
    resource_version = Column(Integer, nullable=False)
    details_json = Column(JSON, nullable=False)
    occurred_at = Column(UtcDateTime, nullable=False)
    previous_hash = Column(String)
    event_hash = Column(String)
    __table_args__ = (CheckConstraint("resource_version >= 1", name="positive_version"),)


class IdempotencyRecord(Identity, Created, Base):
    __tablename__ = "idempotency_records"
    actor_id = Column(UuidV4, nullable=False)
    method = Column(String, nullable=False)
    route = Column(String, nullable=False)
    key = Column(String, nullable=False)
    request_hash = Column(String(64), nullable=False)
    response_status = Column(Integer, nullable=False)
    response_body = Column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("actor_id", "method", "route", "key"),)


# Shared integrity guard only: owner services still implement atomic workflow writes.
IMMUTABLE_MODELS = (AiExecution, Simulation, Review, AuditEvent)


@event.listens_for(Session, "before_flush")
def protect_immutable_records(session, _context, _instances):
    for row in session.deleted:
        if isinstance(row, IMMUTABLE_MODELS):
            raise ValueError("Immutable records cannot be deleted")
    for row in session.dirty:
        if isinstance(row, IMMUTABLE_MODELS) and session.is_modified(row, include_collections=True):
            raise ValueError("Immutable records cannot be updated")


# SQLite guards also cover bulk/raw SQL updates on tables initialized by metadata.
for model in IMMUTABLE_MODELS:
    table = model.__table__
    for operation in ("UPDATE", "DELETE"):
        event.listen(table, "after_create", DDL(
            f"CREATE TRIGGER protect_{table.name}_{operation.lower()} BEFORE {operation} ON {table.name} "
            "BEGIN SELECT RAISE(ABORT, 'immutable record'); END"
        ).execute_if(dialect="sqlite"))
