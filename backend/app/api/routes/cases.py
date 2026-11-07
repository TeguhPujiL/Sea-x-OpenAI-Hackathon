from app.schemas.shared import Envelope
from app.schemas.p0 import CaseView, CaseDeleted, ListData
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from pydantic import UUID4
from sqlalchemy import func, select

from app.api.response import ApiError, success
from app.api.presenters import case_data, page
from app.core.security import Actor, require_scope, require_idempotency_key, check_version
from app.core.transactions import audit, case_for, idempotent_replay, idempotent_response, write_transaction, wire
from app.models import Case, CaseAccess, Review, AnalysisJob
from app.models.base import now
from app.schemas.p0 import CaseCreate, CasePatch, DeleteRequest

router = APIRouter(tags=["cases"])


@router.post("/cases", status_code=201, response_model=Envelope[CaseView])
def create_case(payload: CaseCreate, request: Request,
    actor: Annotated[Actor, Depends(require_scope("case:write"))],
    key: Annotated[str, Depends(require_idempotency_key)]):
    data = payload.model_dump(mode="json")
    with write_transaction(request) as db:
        replay = idempotent_replay(db, actor, "POST", request.url.path, key, data)
        if replay:
            return replay
        ordinal = db.scalar(select(func.count()).select_from(Case)) + 1
        row = Case(id=uuid4(), case_number=f"PROC-{now().year}-{ordinal:03d}", **data)
        db.add(row)
        db.flush()
        db.add(CaseAccess(case_id=row.id, actor_id=actor.actor_id))
        audit(db, actor, request.state.request_id, row.id, "CASE_CREATED", "case", row.id, row.version)
        response = idempotent_response(db, actor, request, key, data, case_data(row), 201)
    return response


@router.get("/cases", response_model=Envelope[ListData[CaseView]])
def list_cases(request: Request, actor: Annotated[Actor, Depends(require_scope("case:read"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0,
    include_deleted: bool = False):
    if set(request.query_params) - {"limit", "offset", "include_deleted"}:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown query field")
    if include_deleted and actor.role != "ADMIN":
        raise ApiError(403, "FORBIDDEN", "Deleted case access requires an administrator")
    with request.app.state.session_factory() as db:
        query = select(Case).join(CaseAccess).where(CaseAccess.actor_id == actor.actor_id)
        if not include_deleted:
            query = query.where(Case.deleted_at.is_(None))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(Case.created_at, Case.id).limit(limit).offset(offset)).all()
        return success(page([case_data(r) for r in rows], total, limit, offset), request.state.request_id)


@router.get("/cases/{case_id}", response_model=Envelope[CaseView])
def get_case(case_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("case:read"))]):
    with request.app.state.session_factory() as db:
        return success(case_data(case_for(db, actor, case_id)), request.state.request_id)


@router.patch("/cases/{case_id}", response_model=Envelope[CaseView])
def patch_case(case_id: UUID4, payload: CasePatch, request: Request,
    actor: Annotated[Actor, Depends(require_scope("case:write"))]):
    with write_transaction(request) as db:
        row = case_for(db, actor, case_id)
        check_version(row.version, payload.expected_version)
        for name, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
            setattr(row, name, value)
        row.version += 1
        db.flush()
        audit(db, actor, request.state.request_id, row.id, "CASE_UPDATED", "case", row.id, row.version)
        data = case_data(row)
    return success(data, request.state.request_id)


@router.delete("/cases/{case_id}", response_model=Envelope[CaseDeleted])
def delete_case(case_id: UUID4, payload: DeleteRequest, request: Request,
    actor: Annotated[Actor, Depends(require_scope("case:delete"))]):
    with write_transaction(request) as db:
        row = case_for(db, actor, case_id)
        check_version(row.version, payload.expected_version)
        if db.scalar(select(Review.id).where(Review.case_id == case_id).limit(1)):
            raise ApiError(409, "INVALID_STATE_TRANSITION", "A reviewed case cannot be deleted")
        if db.scalar(select(AnalysisJob.id).where(AnalysisJob.case_id == case_id,
                AnalysisJob.processing_status.in_(["QUEUED", "PROCESSING"])).limit(1)):
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Analysis is still active")
        row.deleted_at = now()
        row.version += 1
        audit(db, actor, request.state.request_id, row.id, "CASE_DELETED", "case", row.id, row.version, {"reason": payload.reason})
        data = {"case_id": str(row.id), "deleted_at": wire(row.deleted_at)}
    return success(data, request.state.request_id)
