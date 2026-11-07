"""Opt-in PROPOSED P1.1 routes. Poll existing /jobs; no duplicate uploads/audits."""
from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import UUID4
from sqlalchemy import select, func
from app.api.response import ApiError, success
from app.api.presenters import page
from app.core.security import Actor, require_scope, require_idempotency_key
from app.core.transactions import write_transaction, case_for
from app.models.p1 import AssessmentCheck
from app.schemas.shared import Envelope
from app.schemas.p0 import JobView, ListData
from app.schemas.evaluation import EvaluationCreate, AssessmentView
from app.services.integrity.assessments import create_check, check_for, view, run_check, require_migration

router = APIRouter(tags=["p1-evaluation-proposed"])
Writer = Annotated[Actor, Depends(require_scope("analysis:write"))]
Key = Annotated[str, Depends(require_idempotency_key)]


def reader(actor: Annotated[Actor, Depends(require_scope("analysis:read"))]):
    if actor.role not in {"ANALYST", "REVIEWER", "ADMIN", "AUDITOR"}:
        raise ApiError(403, "FORBIDDEN", "Supplier self-service access is not defined in the current contract")
    return actor


Reader = Annotated[Actor, Depends(reader)]


def initiate(request, background, actor, case_id, kind, payload, key, previous=None):
    with write_transaction(request) as db:
        prior = check_for(db, actor, previous, kind) if previous else None
        response, check_id = create_check(db, request, actor, case_id, kind, payload.model_dump(mode="json"), key, prior)
    if check_id:
        background.add_task(run_check, request.app, check_id)
    return response


def listing(request, actor, case_id, kind, limit, offset):
    if set(request.query_params) - {"limit", "offset"}:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown query field")
    with request.app.state.session_factory() as db:
        case_for(db, actor, case_id)
        require_migration(db)
        query = select(AssessmentCheck).where(AssessmentCheck.case_id == case_id, AssessmentCheck.kind == kind)
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(AssessmentCheck.created_at, AssessmentCheck.id).limit(limit).offset(offset)).all()
        return success(page([view(db, row) for row in rows], count, limit, offset), request.state.request_id)


def detail(request, actor, check_id, kind):
    with request.app.state.session_factory() as db:
        return success(view(db, check_for(db, actor, check_id, kind)), request.state.request_id)


@router.post("/cases/{case_id}/evaluation-checks", status_code=202, response_model=Envelope[JobView])
def create(case_id: UUID4, payload: EvaluationCreate, request: Request, background: BackgroundTasks, actor: Writer, key: Key):
    return initiate(request, background, actor, case_id, "EVALUATION", payload, key)


@router.get("/cases/{case_id}/evaluation-checks", response_model=Envelope[ListData[AssessmentView]])
def list_checks(case_id: UUID4, request: Request, actor: Reader,
                limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0):
    return listing(request, actor, case_id, "EVALUATION", limit, offset)


@router.get("/evaluation-checks/{check_id}", response_model=Envelope[AssessmentView])
def get_check(check_id: UUID4, request: Request, actor: Reader):
    return detail(request, actor, check_id, "EVALUATION")
