from app.schemas.shared import Envelope
from app.schemas.p0 import JobView
from typing import Annotated
from uuid import uuid4
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import UUID4

from app.api.presenters import job_data
from app.api.response import ApiError
from app.core.security import Actor, require_scope, require_idempotency_key
from app.core.transactions import audit, case_for, idempotent_replay, idempotent_response, write_transaction
from app.models import AnalysisJob, Document
from app.schemas.p0 import AnalysisCreate
from app.services.ai.jobs import execute_job

router = APIRouter(tags=["analyses"])


def validate_documents(db, actor, case_id, document_ids):
    case_for(db, actor, case_id)
    for document_id in document_ids:
        row = db.get(Document, document_id)
        if row is None or row.deleted_at or row.case_id != case_id:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Analysis document not found in this case")
        if row.processing_status != "COMPLETED":
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Document extraction is not complete")


@router.post("/cases/{case_id}/analyses", status_code=202, response_model=Envelope[JobView])
def create_analysis(case_id: UUID4, payload: AnalysisCreate, request: Request, background: BackgroundTasks,
    actor: Annotated[Actor, Depends(require_scope("analysis:write"))],
    key: Annotated[str, Depends(require_idempotency_key)]):
    normalized = payload.model_dump(mode="json")
    with write_transaction(request) as db:
        case = case_for(db, actor, case_id)
        replay = idempotent_replay(db, actor, "POST", request.url.path, key, normalized)
        if replay:
            return replay
        validate_documents(db, actor, case_id, payload.document_ids)
        if case.case_status in {"REVIEW_COMPLETED", "ARCHIVED"}:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Case cannot be assessed in its current state")
        job = AnalysisJob(id=uuid4(), case_id=case_id, analysis_types=normalized["analysis_types"],
            input_document_ids_json=normalized["document_ids"], actor_id=actor.actor_id, request_id=request.state.request_id)
        db.add(job)
        if case.case_status != "UNDER_ASSESSMENT":
            case.case_status = "UNDER_ASSESSMENT"
            case.version += 1
        db.flush()
        audit(db, actor, request.state.request_id, case_id, "ANALYSIS_QUEUED", "analysis_job", job.id, 1)
        response = idempotent_response(db, actor, request, key, normalized, job_data(db, job), 202)
        job_id = job.id
    # Commit job/idempotency/audit before executing any work.
    background.add_task(execute_job, request.app, job_id)
    return response
