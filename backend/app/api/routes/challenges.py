from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from pydantic import UUID4
from sqlalchemy import func, select

from app.api.response import ApiError, success
from app.api.presenters import page
from app.api.decision_presenters import challenge_data
from app.core.security import Actor, require_scope, check_version
from app.core.transactions import write_transaction, case_for, resource_for, wire
from app.models import Challenge
from app.models.base import now
from app.schemas.shared import Envelope
from app.schemas.p0 import DeleteRequest, ListData
from app.schemas.decisions import ChallengeCreate, ChallengePatch, ChallengeView, ChallengeDeleted, ChallengeOutput
from app.services.decision_generation import generate_decision, delegate_audit
from app.services.decision_evidence import sources_for, validate_challenge

router = APIRouter(tags=["challenges"])


@router.post("/cases/{case_id}/challenges", status_code=201, response_model=Envelope[ChallengeView])
def create_challenge(case_id: UUID4, payload: ChallengeCreate, request: Request,
    actor: Annotated[Actor, Depends(require_scope("challenge:write"))]):
    return generate_decision(request, actor, payload.finding_id, payload, "challenge", case_id=case_id)


@router.get("/cases/{case_id}/challenges", response_model=Envelope[ListData[ChallengeView]])
def list_challenges(case_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("challenge:read"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0):
    if set(request.query_params) - {"limit", "offset"}:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown query field")
    with request.app.state.session_factory() as db:
        case_for(db, actor, case_id)
        query = select(Challenge).where(Challenge.case_id == case_id, Challenge.deleted_at.is_(None))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(Challenge.created_at, Challenge.id).limit(limit).offset(offset)).all()
        return success(page([challenge_data(r) for r in rows], total, limit, offset), request.state.request_id)


@router.get("/challenges/{challenge_id}", response_model=Envelope[ChallengeView])
def get_challenge(challenge_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("challenge:read"))]):
    with request.app.state.session_factory() as db:
        return success(challenge_data(resource_for(db, actor, Challenge, challenge_id)), request.state.request_id)


@router.patch("/challenges/{challenge_id}", response_model=Envelope[ChallengeView])
def patch_challenge(challenge_id: UUID4, payload: ChallengePatch, request: Request,
    actor: Annotated[Actor, Depends(require_scope("challenge:write"))]):
    with write_transaction(request) as db:
        row = resource_for(db, actor, Challenge, challenge_id)
        check_version(row.version, payload.expected_version)
        if row.status not in {"DRAFT", "READY"}:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Only DRAFT or READY challenges may be edited")
        if payload.question is not None or payload.status == "READY":
            _, _, context = sources_for(db, actor, row.case_id, row.finding_id)
            # Human edits retain the same independently verified finding sources.
            output = ChallengeOutput(question=payload.question or row.question,
                risk_rationale=row.risk_rationale, evidence=context["evidence"])
            validate_challenge(output, context)
        if payload.question is not None:
            row.human_edits = row.human_edits or payload.question != row.question
            row.question = payload.question
        if payload.status is not None:
            row.status = payload.status
        row.version += 1
        db.flush()
        delegate_audit(request, db, actor, row.case_id, "CHALLENGE_UPDATED", "challenge", row.id, row.version,
            {"status": row.status})
        data = challenge_data(row)
    return success(data, request.state.request_id)


@router.delete("/challenges/{challenge_id}", response_model=Envelope[ChallengeDeleted])
def delete_challenge(challenge_id: UUID4, payload: DeleteRequest, request: Request,
    actor: Annotated[Actor, Depends(require_scope("challenge:delete"))]):
    with write_transaction(request) as db:
        row = resource_for(db, actor, Challenge, challenge_id)
        check_version(row.version, payload.expected_version)
        if row.status != "DRAFT" or request.app.state.reference_lookup.challenge_in_use(db, row):
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Only an unreferenced DRAFT challenge may be deleted")
        row.deleted_at = now()
        row.version += 1
        delegate_audit(request, db, actor, row.case_id, "CHALLENGE_DELETED", "challenge", row.id, row.version,
            {"reason": payload.reason})
        data = {"challenge_id": str(row.id), "deleted_at": wire(row.deleted_at)}
    return success(data, request.state.request_id)
