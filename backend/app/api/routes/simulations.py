"""Aris-owned synchronous deterministic simulation API."""
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import UUID4

from app.api.response import ApiError, failure, success
from app.core.security import Actor, require_idempotency_key, require_scope
from app.schemas.shared import Envelope, ErrorDetail
from app.services.simulation.engine import SimulationError, SupplierCatalog
from app.services.simulation.models import SimulationInput, SimulationPage, SimulationWire
from app.services.simulation.service import SimulationAccess, SimulationService
from app.services.simulation.shared_repository import (
    CreationContext, PersistedSimulationAccess, SharedSimulationRepository,
)


class SimulationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def wrapped(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                errors = exc.errors()
                # Schema/transport errors use Appendix B's 400. Invalid scenario
                # parameters and missing versions use the user's explicit 422 rule.
                structural = any(
                    e["type"] in {"extra_forbidden", "json_invalid", "model_attributes_type"}
                    or e["loc"][0] in {"path", "query", "header"}
                    or len(e["loc"]) == 1
                    or "finding_id" in e["loc"]
                    for e in errors
                )
                error = ApiError(
                    400 if structural else 422,
                    "VALIDATION_ERROR" if structural else "SIMULATION_INPUT_INVALID",
                    "Invalid simulation request" if structural else "Invalid simulation scenario",
                    details=[ErrorDetail(field=".".join(map(str, e["loc"])), reason="Invalid or unknown field") for e in errors],
                )
                return failure(error, request.state.request_id)
            except SimulationError as exc:
                return failure(ApiError(exc.status_code, exc.code, str(exc)), request.state.request_id)

        return wrapped


def get_simulation_service(request: Request) -> SimulationService:
    return SimulationService(
        SharedSimulationRepository(request.app.state.session_factory), SupplierCatalog.packaged(),
    )


def get_simulation_access(request: Request) -> SimulationAccess:
    policy = getattr(request.state, "simulation_access", None)
    if policy is None:
        # Deployment configuration failure, not a new Appendix B business code.
        raise ApiError(500, "INTERNAL_ERROR", "Trusted simulation authorization is not configured")
    return PersistedSimulationAccess(request.app.state.session_factory, policy)


router = APIRouter(tags=["simulations"], route_class=SimulationRoute, responses={
    status: {"model": Envelope[None], "description": description}
    for status, description in {
        400: "VALIDATION_ERROR", 401: "AUTHENTICATION_REQUIRED", 403: "FORBIDDEN",
        404: "RESOURCE_NOT_FOUND", 409: "IDEMPOTENCY_KEY_REUSED",
        422: "SIMULATION_INPUT_INVALID", 500: "INTERNAL_ERROR",
    }.items()
})
Service = Annotated[SimulationService, Depends(get_simulation_service)]
Access = Annotated[SimulationAccess, Depends(get_simulation_access)]
WriteActor = Annotated[Actor, Depends(require_scope("simulation:write"))]
ReadActor = Annotated[Actor, Depends(require_scope("simulation:read"))]


def required_simulation_key(key: Annotated[str, Header(alias="Idempotency-Key")]) -> str:
    return require_idempotency_key(key)


Key = Annotated[str, Depends(required_simulation_key)]


@router.post("/cases/{case_id}/simulations", status_code=201, response_model=Envelope[SimulationWire])
def create_simulation(request: Request, case_id: UUID4, scenario: SimulationInput,
                      actor: WriteActor, key: Key, access: Access, service: Service):
    context = CreationContext(actor, key, request.url.path, request.state.request_id)
    body = service.create_response(case_id, scenario, access, context)
    return JSONResponse(body, status_code=201)


@router.get("/cases/{case_id}/simulations", response_model=Envelope[SimulationPage])
def list_simulations(request: Request, case_id: UUID4, actor: ReadActor,
                     access: Access, service: Service,
                     limit: Annotated[int, Query(ge=1)] = 20,
                     offset: Annotated[int, Query(ge=0)] = 0):
    return success(service.list_page(case_id, access, limit, offset), request.state.request_id)


@router.get("/simulations/{simulation_id}", response_model=Envelope[SimulationWire])
def get_simulation(request: Request, simulation_id: UUID4, actor: ReadActor,
                   access: Access, service: Service):
    record = service.detail(simulation_id, access)
    return success(service.wire_record(record), request.state.request_id)
