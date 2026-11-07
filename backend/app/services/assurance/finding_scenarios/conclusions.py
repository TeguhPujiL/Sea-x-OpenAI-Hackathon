"""Opt-in local procurement conclusions, separate from v1.1 human reviews.

No CaseStatus, AssuranceStatus or finding disposition is changed here.
"""
import re
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, Request
from pydantic import Field, StrictBool, field_validator, model_validator
from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event, inspect, select
from sqlalchemy.orm import Session

from app.api.response import ApiError, success
from app.core.security import Actor, require_idempotency_key, require_scope
from app.core.transactions import audit, case_for, idempotent_replay, idempotent_response, resource_for, wire, write_transaction
from app.models import AnalysisJob, Case, Document
from app.models.base import Created, Identity, UuidV4, now
from app.schemas.shared import PositiveVersion, StrictModel
from app.services.assurance.audit import actor_snapshot
from .models import FeatureBase
from .vendor_summary import vendor_summary


class ProcurementConclusion(Identity, Created, FeatureBase):
    __tablename__ = "procurement_conclusions"
    case_id = Column(UuidV4, ForeignKey(Case.__table__.c.id), nullable=False)
    analysis_job_id = Column(UuidV4, ForeignKey(AnalysisJob.__table__.c.id), nullable=False)
    decision = Column(String, nullable=False)
    selected_vendor_id = Column(String)
    decision_reason = Column(Text, nullable=False)
    source_case_version = Column(Integer, nullable=False)
    reviewer_json = Column(JSON, nullable=False)
    request_id = Column(String, nullable=False)
    snapshot_json = Column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint("case_id", "analysis_job_id"),
        CheckConstraint("decision IN ('GO','NO_GO')", name="decision"),
        CheckConstraint("(decision='GO' AND selected_vendor_id IS NOT NULL AND length(selected_vendor_id)>0) OR (decision='NO_GO' AND selected_vendor_id IS NULL)", name="vendor_disposition"),
        CheckConstraint("source_case_version >= 1", name="positive_version"),
        CheckConstraint("length(trim(decision_reason)) BETWEEN 20 AND 4000", name="meaningful_reason"),
        CheckConstraint("json_valid(reviewer_json) AND json_valid(snapshot_json)", name="valid_snapshots"),
    )


@event.listens_for(Session, "before_flush")
def immutable_conclusions(session, _context, _instances):
    if any(isinstance(row, ProcurementConclusion) for row in list(session.deleted) +
           [row for row in session.dirty if session.is_modified(row)]):
        raise ValueError("Procurement conclusions are immutable")


class ConclusionCreate(StrictModel):
    analysis_job_id: UUID
    decision: Literal["GO", "NO_GO"]
    selected_vendor_id: Annotated[str, Field(pattern=r"^[A-Z0-9]{1,40}$")] | None
    decision_reason: Annotated[str, Field(min_length=20, max_length=4000)]
    expected_case_version: PositiveVersion
    vendor_review_confirmed: StrictBool

    @field_validator("analysis_job_id")
    @classmethod
    def uuid4_only(cls, value):
        if value.version != 4:
            raise ValueError("UUID v4 required")
        return value

    @field_validator("decision_reason")
    @classmethod
    def meaningful(cls, value):
        value = value.strip()
        if len(value) < 20 or len(value.split()) < 4 or len(set(value.lower())) < 8:
            raise ValueError("Explain the procurement decision in at least four words and 20 characters")
        return value

    @model_validator(mode="after")
    def disposition(self):
        if self.decision == "NO_GO" and self.selected_vendor_id is not None:
            raise ValueError("NO_GO must have no selected vendor")
        if self.decision == "GO" and (not self.selected_vendor_id or not self.vendor_review_confirmed):
            raise ValueError("GO requires a selected vendor and confirmation of the evidence review")
        return self


def ensure_conclusions(db):
    from .conclusions_migration import checksum, TRIGGER_NAMES
    connection = db.connection()
    if not {"procurement_conclusions", "procurement_conclusion_schema_versions"}.issubset(inspect(connection).get_table_names()):
        raise ApiError(500, "INTERNAL_ERROR", "Run the explicit local procurement-conclusion migration")
    installed = connection.exec_driver_sql("SELECT checksum FROM procurement_conclusion_schema_versions WHERE version=1").scalar()
    guards = set(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='procurement_conclusions'").scalars())
    if installed != checksum(connection) or not TRIGGER_NAMES.issubset(guards):
        raise ApiError(500, "INTERNAL_ERROR", "Procurement-conclusion integrity guards require operator review")


def conclusion_data(row):
    return wire({"conclusion_id": row.id, "case_id": row.case_id, "analysis_job_id": row.analysis_job_id,
        "decision": row.decision, "selected_vendor_id": row.selected_vendor_id,
        "selected_vendor_label": f"Vendor {row.selected_vendor_id}" if row.selected_vendor_id else None,
        "decision_reason": row.decision_reason, "reviewer": row.reviewer_json,
        "source_case_version": row.source_case_version, "created_at": row.created_at,
        "scope": "INTERNAL_PROCUREMENT_CONCLUSION", "snapshot": row.snapshot_json})


def get_conclusion(db, actor, case_id, analysis_job_id):
    ensure_conclusions(db)
    case_for(db, actor, case_id)
    job = resource_for(db, actor, AnalysisJob, analysis_job_id)
    if job.case_id != case_id:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Analysis not found for this case")
    row = db.scalar(select(ProcurementConclusion).where(ProcurementConclusion.case_id == case_id,
        ProcurementConclusion.analysis_job_id == analysis_job_id))
    return {"conclusion": conclusion_data(row) if row else None}


def create_conclusion(request, actor, case_id, payload, key):
    if len(key) > 200:
        raise ApiError(400, "VALIDATION_ERROR", "Idempotency-Key exceeds 200 characters")
    normalized = payload.model_dump(mode="json")
    with write_transaction(request) as db:
        ensure_conclusions(db)
        case = case_for(db, actor, case_id)
        job = resource_for(db, actor, AnalysisJob, payload.analysis_job_id)
        if job.case_id != case_id:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Analysis not found for this case")
        replay = idempotent_replay(db, actor, "POST", request.url.path, key, normalized)
        if replay is not None:
            return replay
        if case.version != payload.expected_case_version:
            raise ApiError(409, "VERSION_CONFLICT", "Case changed; refresh before recording the conclusion")
        if wire(case.case_status) in {"ARCHIVED", "REVIEW_COMPLETED"}:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "The case is no longer open for a procurement conclusion")
        latest = db.scalar(select(AnalysisJob).where(AnalysisJob.case_id == case_id).order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc()))
        if latest.id != job.id or wire(job.processing_status) not in {"COMPLETED", "NEEDS_REVIEW"} or job.result_json is None:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Use the latest completed assessment with a usable result")
        if db.scalar(select(ProcurementConclusion.id).where(ProcurementConclusion.case_id == case_id, ProcurementConclusion.analysis_job_id == job.id)):
            raise ApiError(409, "INVALID_STATE_TRANSITION", "This assessment already has an immutable conclusion")
        documents = [resource_for(db, actor, Document, UUID(value)) for value in job.input_document_ids_json]
        if any(doc.case_id != case_id or wire(doc.processing_status) != "COMPLETED" for doc in documents):
            raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Assessment documents are no longer available")
        if payload.decision == "GO":
            pattern = re.compile(r"(?:^|[\s_.-])vendor[\s_-]+([a-z0-9]+)(?=[\s_.-]|$)", re.I)
            offers = [doc for doc in documents if wire(doc.document_type) == "SUPPLIER_QUOTATION"
                and (match := pattern.search(doc.filename)) and match[1].upper() == payload.selected_vendor_id]
            if not offers:
                raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Select a vendor with a readable quotation in this assessment")
        snapshot = vendor_summary(db, actor, case_id, job.id)
        snapshot["current_result"] = job.result_json
        snapshot["current_warnings"] = job.warnings_json
        snapshot["documents"] = [{"document_id": str(doc.id), "filename": doc.filename, "sha256": doc.sha256,
            "version": doc.version, "document_type": wire(doc.document_type)} for doc in documents]
        snapshot["vendor_review_confirmed"] = payload.vendor_review_confirmed
        snapshot["limitation"] = "Internal human conclusion only; unresolved findings and v1.1 case approval remain unchanged."
        row = ProcurementConclusion(id=uuid4(), case_id=case_id, analysis_job_id=job.id, decision=payload.decision,
            selected_vendor_id=payload.selected_vendor_id, decision_reason=payload.decision_reason,
            source_case_version=case.version, reviewer_json=actor_snapshot(actor), request_id=request.state.request_id,
            snapshot_json=snapshot, created_at=now())
        db.add(row)
        db.flush()
        audit(db, actor, request.state.request_id, case_id, "PROCUREMENT_CONCLUSION_RECORDED", "procurement_conclusion", row.id, 1,
            {"decision": row.decision, "selected_vendor_id": row.selected_vendor_id, "analysis_job_id": str(job.id), "source_case_version": case.version})
        return idempotent_response(db, actor, request, key, normalized, {"conclusion": conclusion_data(row)}, 201)
