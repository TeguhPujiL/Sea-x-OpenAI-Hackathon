"""Contract v1.1 section 6.9: authorized append-only history reads."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.response import success
from app.core.database import get_session
from app.core.security import Actor, require_scope
from app.schemas.shared import Envelope, ResourceId
from app.services.assurance.access import CaseGrants
from app.services.assurance.schemas import ERROR_RESPONSES, AuditQuery, AuditView, Page
from app.services.assurance import audit

router = APIRouter(tags=["audit"])


@router.get("/cases/{case_id}/audit", response_model=Envelope[Page[AuditView]], responses=ERROR_RESPONSES)
def list_audit(case_id: ResourceId, request: Request,
               session: Annotated[Session, Depends(get_session)], grants: CaseGrants,
               actor: Annotated[Actor, Depends(require_scope("audit:read"))],
               query: Annotated[AuditQuery, Query()]):
    return success(audit.list_audit(session, case_id, actor, grants, query.limit, query.offset), request.state.request_id)


@router.get("/audit-events/{event_id}", response_model=Envelope[AuditView], responses=ERROR_RESPONSES)
def get_audit(event_id: ResourceId, request: Request,
              session: Annotated[Session, Depends(get_session)], grants: CaseGrants,
              actor: Annotated[Actor, Depends(require_scope("audit:read"))]):
    return success(audit.get_audit(session, event_id, actor, grants), request.state.request_id)
