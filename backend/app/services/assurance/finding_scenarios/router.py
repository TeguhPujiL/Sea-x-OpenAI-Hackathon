"""Mount ONLY at /api/v1/experimental behind explicit local opt-in."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import UUID4
from sqlalchemy import func, select

from app.api.presenters import page
from app.api.response import ApiError, success
from app.core.security import Actor, require_idempotency_key, require_scope
from app.core.transactions import case_for, resource_for
from app.schemas.p0 import ListData
from app.schemas.shared import Envelope
from . import EXPERIMENTAL_CONTRACT
from .models import FindingScenario
from .schemas import FindingScenarioCreate, FindingScenarioView
from .service import create_scenario, ensure_migrated, scenario_data
from .vendor_summary import vendor_summary
from .conclusions import ConclusionCreate, create_conclusion, get_conclusion
from .conclusion_validation import ConclusionValidationRoute

conclusion_router = APIRouter(route_class=ConclusionValidationRoute)

router = APIRouter(tags=["experimental-finding-scenarios"], responses={
    status: {"description": f"PROPOSED-v1.2 experimental failure: {code}"} for status, code in {
        400: "VALIDATION_ERROR", 401: "AUTHENTICATION_REQUIRED", 403: "FORBIDDEN", 404: "RESOURCE_NOT_FOUND",
        409: "VERSION_CONFLICT / INVALID_STATE_TRANSITION / IDEMPOTENCY_KEY_REUSED", 422: "EVIDENCE_VALIDATION_FAILED",
        429: "RATE_LIMITED", 500: "INTERNAL_ERROR", 502: "AI_PROVIDER_ERROR", 504: "AI_PROVIDER_TIMEOUT"}.items()})


def label(response):
    response.headers["X-Experimental-Contract"] = EXPERIMENTAL_CONTRACT
    return response


@router.post("/cases/{case_id}/finding-simulations", status_code=201, response_model=Envelope[FindingScenarioView],
             description="PROPOSED-v1.2 local experimental qualitative what-if scenarios; not a v1.1 RAM simulation or approval.")
def post_scenario(case_id: UUID4, payload: FindingScenarioCreate, request: Request,
                  actor: Annotated[Actor, Depends(require_scope("simulation:write"))],
                  key: Annotated[str, Depends(require_idempotency_key)]):
    return label(create_scenario(request, actor, case_id, payload, key))


@router.get("/cases/{case_id}/finding-simulations", response_model=Envelope[ListData[FindingScenarioView]])
def list_scenarios(case_id: UUID4, request: Request,
                   actor: Annotated[Actor, Depends(require_scope("simulation:read"))],
                   limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0):
    if set(request.query_params) - {"limit", "offset"}:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown query field")
    with request.app.state.session_factory() as db:
        ensure_migrated(db)
        case_for(db, actor, case_id)
        query = select(FindingScenario).where(FindingScenario.case_id == case_id)
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(FindingScenario.created_at, FindingScenario.id).limit(limit).offset(offset)).all()
        return label(success(page([scenario_data(db, row) for row in rows], total, limit, offset), request.state.request_id))


@router.get("/finding-simulations/{scenario_id}", response_model=Envelope[FindingScenarioView])
def get_scenario(scenario_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("simulation:read"))]):
    with request.app.state.session_factory() as db:
        ensure_migrated(db)
        row = resource_for(db, actor, FindingScenario, scenario_id)
        return label(success(scenario_data(db, row), request.state.request_id))


@router.get("/cases/{case_id}/vendor-assurance-summary",
    description="Experimental read-only source-labelled vendor facts and original-finding repair history.")
def get_vendor_summary(case_id: UUID4, analysis_job_id: UUID4, request: Request,
                       actor: Annotated[Actor, Depends(require_scope("case:read"))]):
    for scope in ("document:read", "analysis:read", "finding:read", "repair:read", "review:read"):
        require_scope(scope)(actor)
    if set(request.query_params) - {"analysis_job_id"}:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown query field")
    with request.app.state.session_factory() as db:
        return label(success(vendor_summary(db, actor, case_id, analysis_job_id), request.state.request_id))


@conclusion_router.get("/cases/{case_id}/procurement-conclusions",
    description="PROPOSED-v1.2 immutable internal conclusion for one assessment; no v1.1 case approval.")
def read_procurement_conclusion(case_id: UUID4, analysis_job_id: UUID4, request: Request,
                               actor: Annotated[Actor, Depends(require_scope("review:read"))]):
    for scope in ("case:read", "document:read", "analysis:read", "finding:read", "repair:read"):
        require_scope(scope)(actor)
    if set(request.query_params) - {"analysis_job_id"}:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown query field")
    with request.app.state.session_factory() as db:
        return label(success(get_conclusion(db, actor, case_id, analysis_job_id), request.state.request_id))


@conclusion_router.post("/cases/{case_id}/procurement-conclusions", status_code=201,
    description="PROPOSED-v1.2 local internal GO/NO_GO conclusion; does not approve or close the v1.1 case.")
def record_procurement_conclusion(case_id: UUID4, payload: ConclusionCreate, request: Request,
                                  actor: Annotated[Actor, Depends(require_scope("review:decide"))],
                                  key: Annotated[str, Depends(require_idempotency_key)]):
    for scope in ("case:read", "document:read", "analysis:read", "finding:read", "repair:read", "review:read"):
        require_scope(scope)(actor)
    if request.query_params:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown query field")
    return label(create_conclusion(request, actor, case_id, payload, key))


router.include_router(conclusion_router)
