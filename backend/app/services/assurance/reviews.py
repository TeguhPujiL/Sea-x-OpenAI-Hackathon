"""Review commands. All business, audit and replay rows share one transaction."""
import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session, aliased

from app.api.response import ApiError
from app.core.security import Actor, check_version
from app.models import (
    AiExecution, AnalysisJob, Case, Document, DocumentPage, EvidenceRef, Finding,
    IdempotencyRecord, RepairProposal, Review, Simulation,
)
from app.models.base import now
from app.schemas.shared import AssuranceStatus, CaseStatus, EvidenceStatus, FindingStatus, ProcessingStatus, RepairStatus, ReviewDecision
from app.services.assurance.access import case_for_actor
from app.services.assurance.audit import actor_snapshot, append_audit
from app.services.assurance.schemas import Page, ReviewCreate, ReviewView


def not_found(message: str = "Referenced resource not found"):
    raise ApiError(404, "RESOURCE_NOT_FOUND", message)


def invalid_state(message: str):
    raise ApiError(409, "INVALID_STATE_TRANSITION", message)


def review_view(row: Review) -> ReviewView:
    return ReviewView(review_id=row.id, case_id=row.case_id,
        repair_proposal_id=row.repair_proposal_id, decision=row.decision,
        decision_reason=row.decision_reason, review_status=row.review_status,
        reviewer=row.reviewer_snapshot_json, assurance_status_after=row.assurance_status_after,
        created_at=row.created_at)


def validate_references(session: Session, repair: RepairProposal, case_id: UUID) -> Finding:
    finding = session.get(Finding, repair.finding_id)
    if finding is None or finding.case_id != case_id:
        not_found()
    job = session.get(AnalysisJob, finding.analysis_job_id)
    execution = session.get(AiExecution, finding.ai_execution_id)
    if job is None or job.case_id != case_id or execution is None or execution.case_id != case_id:
        not_found()
    if execution.job_id is not None and execution.job_id != job.id:
        not_found()
    if repair.simulation_id:
        simulation = session.get(Simulation, repair.simulation_id)
        if simulation is None or simulation.case_id != case_id or simulation.finding_id != finding.id:
            not_found()
    if repair.ai_execution_id:
        repair_execution = session.get(AiExecution, repair.ai_execution_id)
        if repair_execution is None or repair_execution.case_id != case_id:
            not_found()
    for ref in session.scalars(select(EvidenceRef).where(EvidenceRef.finding_id == finding.id)):
        doc = session.get(Document, ref.document_id)
        if doc is None or doc.case_id != case_id or doc.deleted_at is not None:
            not_found()
        page = session.scalar(select(DocumentPage).where(DocumentPage.document_id == doc.id,
                                                       DocumentPage.page_number == ref.page_number))
        if page is None or not 1 <= ref.page_number <= doc.page_count:
            raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Evidence page is unavailable")
    return finding


def completion_ready(session: Session, case_id: UUID) -> bool:
    """Conservative G05/G09 policy; never auto-resolve findings from approval.

    Every finding blocks until independently RESOLVED (with disposition) or
    DISMISSED (with rationale). Non-dismissed evidence must be verified. A
    historical failed job superseded by a retry does not block its replacement.
    """
    findings = session.scalars(select(Finding).where(Finding.case_id == case_id)).all()
    if not findings:
        return False  # G01: no clean-case completion command exists in v1.1.
    retry = aliased(AnalysisJob)
    leaves = session.scalars(select(AnalysisJob).where(AnalysisJob.case_id == case_id,
        ~exists(select(retry.id).where(retry.retry_of_job_id == AnalysisJob.id)))).all()
    if not leaves or any(j.processing_status != ProcessingStatus.COMPLETED or j.result_json is None or j.warnings_json for j in leaves):
        return False
    for finding in findings:
        if finding.status not in {FindingStatus.RESOLVED, FindingStatus.DISMISSED} or not (finding.resolution_note or "").strip():
            return False
        if finding.status == FindingStatus.DISMISSED:
            continue
        if finding.evidence_status != EvidenceStatus.VERIFIED:
            return False
        execution = session.get(AiExecution, finding.ai_execution_id)
        if (execution is None or execution.case_id != case_id or not execution.schema_valid
                or not execution.evidence_validation_passed or execution.warnings_json):
            return False
        refs = session.scalars(select(EvidenceRef).where(EvidenceRef.finding_id == finding.id)).all()
        if not refs:
            return False
        for ref in refs:
            doc = session.get(Document, ref.document_id)
            page = session.scalar(select(DocumentPage).where(DocumentPage.document_id == ref.document_id,
                                                            DocumentPage.page_number == ref.page_number))
            if (ref.verification_status != EvidenceStatus.VERIFIED or doc is None
                    or doc.case_id != case_id or doc.deleted_at is not None
                    or page is None or not 1 <= ref.page_number <= doc.page_count
                    or not ref.excerpt.strip()
                    or " ".join(ref.excerpt.split()) not in " ".join(page.normalized_text.split())):
                return False
    return True


def create_review(session: Session, *, case_id: UUID, payload: ReviewCreate,
                  actor: Actor, grants: dict, key: str, request_id: str) -> ReviewView:
    if len(key) > 200:
        raise ApiError(400, "VALIDATION_ERROR", "Idempotency-Key exceeds 200 characters")
    route = f"/api/v1/cases/{case_id}/reviews"
    normalized = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    request_hash = hashlib.sha256(normalized.encode()).hexdigest()
    with session.begin():
        if session.bind.dialect.name != "sqlite":
            raise RuntimeError("Assurance transaction locking is validated for SQLite only")
        # Reserve the SQLite writer before *any* business reads. Independent
        # processes serialize both key lookup and expected-version evaluation.
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        case = case_for_actor(session, case_id, actor, grants, writing=True)
        replay = session.scalar(select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == actor.actor_id, IdempotencyRecord.method == "POST",
            IdempotencyRecord.route == route, IdempotencyRecord.key == key))
        if replay:
            if replay.request_hash != request_hash:
                raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was used for another request")
            # A transport retry precedes stale-version/state checks, but never
            # bypasses current authorization. Response meta uses this request ID.
            return ReviewView.model_validate(replay.response_body["data"])
        check_version(case.version, payload.expected_case_version)
        if case.case_status != CaseStatus.UNDER_REVIEW:
            invalid_state("Case must be UNDER_REVIEW")
        repair = session.get(RepairProposal, payload.repair_proposal_id)
        if repair is None or repair.case_id != case_id or repair.deleted_at is not None:
            not_found("Repair proposal not found")
        if repair.status != RepairStatus.SUBMITTED:
            invalid_state("Repair proposal must be SUBMITTED")
        validate_references(session, repair, case_id)
        after = AssuranceStatus.ACTION_REQUIRED
        if payload.decision == ReviewDecision.APPROVE_DRAFT and completion_ready(session, case_id):
            after = AssuranceStatus.REVIEW_COMPLETED
        before = case.assurance_status
        version_before = case.version
        changed = session.execute(update(Case).where(Case.id == case_id, Case.version == version_before,
            Case.deleted_at.is_(None)).values(assurance_status=after, version=version_before + 1,
                                             updated_at=now()), execution_options={"synchronize_session": False})
        if changed.rowcount != 1:
            raise ApiError(409, "VERSION_CONFLICT", "The case version has changed")
        review = Review(id=uuid4(), case_id=case_id, repair_proposal_id=repair.id,
            decision=payload.decision, decision_reason=payload.decision_reason,
            review_status="COMPLETED", reviewer_actor_id=actor.actor_id,
            reviewer_snapshot_json=actor_snapshot(actor), assurance_status_after=after,
            created_at=now())
        session.add(review)
        session.flush()
        append_audit(session, actor=actor, case_id=case_id, request_id=request_id,
            event_type="REVIEW_COMPLETED", resource_type="review", resource_id=review.id,
            resource_version=1, details={"decision": payload.decision.value,
                "assurance_status_after": after.value, "repair_proposal_id": str(repair.id),
                "case_version_before": version_before, "case_version_after": version_before + 1})
        append_audit(session, actor=actor, case_id=case_id, request_id=request_id,
            event_type="CASE_ASSURANCE_CHANGED", resource_type="case", resource_id=case_id,
            resource_version=version_before + 1, details={"assurance_status_before": before.value,
                "assurance_status_after": after.value, "review_id": str(review.id),
                "case_version_before": version_before, "case_version_after": version_before + 1})
        view = review_view(review)
        session.add(IdempotencyRecord(actor_id=actor.actor_id, method="POST", route=route,
            key=key, request_hash=request_hash, response_status=201,
            response_body={"data": view.model_dump(mode="json")}))
        session.flush()
        return view


def list_reviews(session: Session, case_id: UUID, actor: Actor, grants: dict,
                 limit: int, offset: int) -> Page[ReviewView]:
    with session.begin():
        case_for_actor(session, case_id, actor, grants)
        total = session.scalar(select(func.count()).select_from(Review).where(Review.case_id == case_id))
        rows = session.scalars(select(Review).where(Review.case_id == case_id)
            .order_by(Review.created_at, Review.id).limit(limit).offset(offset))
        return Page[ReviewView](items=[review_view(r) for r in rows],
                                pagination={"limit": limit, "offset": offset, "total": total})


def get_review(session: Session, review_id: UUID, actor: Actor, grants: dict) -> ReviewView:
    with session.begin():
        row = session.get(Review, review_id)
        if row is None:
            not_found("Review not found")
        case_for_actor(session, row.case_id, actor, grants)
        return review_view(row)
