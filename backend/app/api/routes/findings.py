from app.schemas.shared import Envelope
from app.schemas.p0 import FindingView, DismissalView, ListData
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from pydantic import UUID4
from sqlalchemy import func, select

from app.api.response import ApiError, success
from app.api.presenters import finding_data, page
from app.core.security import Actor, require_scope, check_version
from app.core.transactions import audit, case_for, resource_for, write_transaction, wire
from app.models import Finding, CaseAccess
from app.models.base import now
from app.schemas.shared import FindingStatus
from app.schemas.p0 import FindingPatch, DismissalRequest

router = APIRouter(tags=["findings"])


@router.get("/cases/{case_id}/findings", response_model=Envelope[ListData[FindingView]])
def list_findings(case_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("finding:read"))],
    status: FindingStatus | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0):
    if set(request.query_params) - {"status", "limit", "offset"}:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown query field")
    with request.app.state.session_factory() as db:
        case_for(db, actor, case_id)
        query = select(Finding).where(Finding.case_id == case_id)
        if status:
            query = query.where(Finding.status == status)
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(Finding.created_at, Finding.id).limit(limit).offset(offset)).all()
        return success(page([finding_data(db, r) for r in rows], total, limit, offset), request.state.request_id)


@router.get("/findings/{finding_id}", response_model=Envelope[FindingView])
def get_finding(finding_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("finding:read"))]):
    with request.app.state.session_factory() as db:
        return success(finding_data(db, resource_for(db, actor, Finding, finding_id)), request.state.request_id)


@router.patch("/findings/{finding_id}", response_model=Envelope[FindingView])
def patch_finding(finding_id: UUID4, payload: FindingPatch, request: Request,
    actor: Annotated[Actor, Depends(require_scope("finding:write"))]):
    with write_transaction(request) as db:
        row = resource_for(db, actor, Finding, finding_id)
        check_version(row.version, payload.expected_version)
        if row.status in {"DISMISSED", "RESOLVED"}:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "A disposed finding cannot be edited")
        if payload.status == "DISMISSED":
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Use the dismissal command with rationale")
        if payload.status == "RESOLVED":
            # PROPOSED conservative precondition until disposition-evidence shape is clarified.
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Resolution requires a disposition-evidence command")
        if payload.assignee_id is not None and db.get(CaseAccess, (row.case_id, payload.assignee_id)) is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Assignee is not a case member")
        for name, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
            setattr(row, name, value)
        row.version += 1
        db.flush()
        audit(db, actor, request.state.request_id, row.case_id, "FINDING_UPDATED", "finding", row.id, row.version)
        data = finding_data(db, row)
    return success(data, request.state.request_id)


@router.post("/findings/{finding_id}/dismissals", status_code=201, response_model=Envelope[DismissalView])
def dismiss_finding(finding_id: UUID4, payload: DismissalRequest, request: Request,
    actor: Annotated[Actor, Depends(require_scope("finding:decide"))]):
    with write_transaction(request) as db:
        row = resource_for(db, actor, Finding, finding_id)
        check_version(row.version, payload.expected_version)
        if row.status not in {"OPEN", "UNDER_REVIEW"}:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Finding cannot be dismissed in its current state")
        row.status = "DISMISSED"
        row.version += 1
        dismissed_at = now()
        audit(db, actor, request.state.request_id, row.case_id, "FINDING_DISMISSED", "finding", row.id, row.version,
            {"reason_code": payload.reason_code, "rationale": payload.rationale, "dismissed_at": wire(dismissed_at)})
        data = {"finding_id": str(row.id), "status": "DISMISSED", "dismissed_by": str(actor.actor_id),
            "dismissed_at": wire(dismissed_at), "version": row.version}
    return success(data, request.state.request_id, 201)
