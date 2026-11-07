"""Opt-in proposed readiness and append-only revalidation commands."""
from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, Query, Request
from pydantic import UUID4
from app.api.routes.evaluation_checks import Writer, Reader, Key, initiate, listing, detail
from app.schemas.shared import Envelope
from app.schemas.p0 import JobView, ListData
from app.schemas.evaluation import AssessmentView
from app.schemas.supplier_readiness import ReadinessCreate, RevalidationCreate
from app.services.integrity.assessments import check_for

router = APIRouter(tags=["p1-readiness-proposed"])


@router.post("/cases/{case_id}/supplier-readiness-checks", status_code=202, response_model=Envelope[JobView])
def create(case_id: UUID4, payload: ReadinessCreate, request: Request, background: BackgroundTasks, actor: Writer, key: Key):
    return initiate(request, background, actor, case_id, "READINESS", payload, key)


@router.get("/cases/{case_id}/supplier-readiness-checks", response_model=Envelope[ListData[AssessmentView]])
def list_checks(case_id: UUID4, request: Request, actor: Reader,
                limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0):
    return listing(request, actor, case_id, "READINESS", limit, offset)


@router.get("/supplier-readiness-checks/{check_id}", response_model=Envelope[AssessmentView])
def get_check(check_id: UUID4, request: Request, actor: Reader):
    return detail(request, actor, check_id, "READINESS")


@router.post("/supplier-readiness-checks/{check_id}/revalidations", status_code=202, response_model=Envelope[JobView])
def revalidate(check_id: UUID4, payload: RevalidationCreate, request: Request, background: BackgroundTasks, actor: Writer, key: Key):
    with request.app.state.session_factory() as db:
        prior = check_for(db, actor, check_id, "READINESS")
        case_id = prior.case_id
    return initiate(request, background, actor, case_id, "READINESS", payload, key, check_id)
