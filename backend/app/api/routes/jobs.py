from app.schemas.shared import Envelope
from app.schemas.p0 import JobView, ListData
from typing import Annotated
from uuid import UUID, uuid4
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import UUID4
from sqlalchemy import func, select

from app.api.response import ApiError, success
from app.api.presenters import job_data, page
from app.api.routes.analyses import validate_documents
from app.core.security import Actor, require_scope
from app.core.transactions import audit, case_for, resource_for, write_transaction
from app.models import AnalysisJob
from app.schemas.p0 import RetryRequest
from app.services.ai.jobs import execute_job

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=Envelope[JobView])
def get_job(job_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("analysis:read"))]):
    with request.app.state.session_factory() as db:
        return success(job_data(db, resource_for(db, actor, AnalysisJob, job_id)), request.state.request_id)


@router.get("/cases/{case_id}/jobs", response_model=Envelope[ListData[JobView]])
def list_jobs(case_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("analysis:read"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0):
    if set(request.query_params) - {"limit", "offset"}:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown query field")
    with request.app.state.session_factory() as db:
        case_for(db, actor, case_id)
        query = select(AnalysisJob).where(AnalysisJob.case_id == case_id)
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(AnalysisJob.created_at, AnalysisJob.id).limit(limit).offset(offset)).all()
        return success(page([job_data(db, r) for r in rows], total, limit, offset), request.state.request_id)


@router.post("/jobs/{job_id}/retries", status_code=202, response_model=Envelope[JobView])
def retry_job(job_id: UUID4, payload: RetryRequest, request: Request, background: BackgroundTasks,
    actor: Annotated[Actor, Depends(require_scope("analysis:write"))]):
    with write_transaction(request) as db:
        original = resource_for(db, actor, AnalysisJob, job_id)
        from sqlalchemy import inspect
        if "p1_checks" in inspect(db.bind).get_table_names():
            from app.models.p1 import AssessmentCheck
            if db.scalar(select(AssessmentCheck.id).where(AssessmentCheck.job_id == original.id)):
                raise ApiError(409, "INVALID_STATE_TRANSITION", "Create a new P1 assessment or revalidation instead of a P0 retry")
        if original.processing_status not in {"FAILED", "NEEDS_REVIEW"}:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Only FAILED or NEEDS_REVIEW jobs may be retried")
        case = case_for(db, actor, original.case_id)
        if case.case_status in {"REVIEW_COMPLETED", "ARCHIVED"}:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Case cannot be reassessed in its current state")
        validate_documents(db, actor, original.case_id, [UUID(i) for i in original.input_document_ids_json])
        row = AnalysisJob(id=uuid4(), case_id=original.case_id, analysis_types=list(original.analysis_types),
            input_document_ids_json=list(original.input_document_ids_json), retry_of_job_id=original.id,
            actor_id=actor.actor_id, request_id=request.state.request_id)
        db.add(row)
        db.flush()
        audit(db, actor, request.state.request_id, row.case_id, "ANALYSIS_RETRIED", "analysis_job", row.id, 1,
            {"reason": payload.reason, "retry_of_job_id": str(original.id)})
        response = success(job_data(db, row), request.state.request_id, 202)
        new_id = row.id
    background.add_task(execute_job, request.app, new_id)
    return response
