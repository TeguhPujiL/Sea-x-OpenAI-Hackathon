"""Contract v1.1 section 6.8: immutable human decisions."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.response import success
from app.core.database import get_session
from app.core.security import Actor, require_scope
from app.schemas.shared import Envelope, ResourceId
from app.services.assurance.access import CaseGrants, review_idempotency_key
from app.services.assurance.schemas import ERROR_RESPONSES, ListQuery, Page, ReviewCreate, ReviewView
from app.services.assurance import reviews

router = APIRouter(tags=["reviews"])


@router.post("/cases/{case_id}/reviews", status_code=201,
             response_model=Envelope[ReviewView], responses=ERROR_RESPONSES)
def create_review(case_id: ResourceId, payload: ReviewCreate, request: Request,
                  session: Annotated[Session, Depends(get_session)], grants: CaseGrants,
                  actor: Annotated[Actor, Depends(require_scope("review:decide"))],
                  key: Annotated[str, Depends(review_idempotency_key)]):
    view = reviews.create_review(session, case_id=case_id, payload=payload, actor=actor,
        grants=grants, key=key, request_id=request.state.request_id)
    return success(view, request.state.request_id, status=201)


@router.get("/cases/{case_id}/reviews", response_model=Envelope[Page[ReviewView]], responses=ERROR_RESPONSES)
def list_reviews(case_id: ResourceId, request: Request,
                 session: Annotated[Session, Depends(get_session)], grants: CaseGrants,
                 actor: Annotated[Actor, Depends(require_scope("review:read"))],
                 query: Annotated[ListQuery, Query()]):
    return success(reviews.list_reviews(session, case_id, actor, grants, query.limit, query.offset), request.state.request_id)


@router.get("/reviews/{review_id}", response_model=Envelope[ReviewView], responses=ERROR_RESPONSES)
def get_review(review_id: ResourceId, request: Request,
                session: Annotated[Session, Depends(get_session)], grants: CaseGrants,
                actor: Annotated[Actor, Depends(require_scope("review:read"))]):
    return success(reviews.get_review(session, review_id, actor, grants), request.state.request_id)
