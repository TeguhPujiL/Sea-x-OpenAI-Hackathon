"""Aris-owned synchronous simulation routes; nested wire types await Teguh review."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import UUID4

from app.api.response import ApiError, failure, success
from app.services.simulation.engine import SimulationError
from app.services.simulation.models import SimulationInput
from app.services.simulation.service import SimulationAccess, SimulationService


class SimulationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def wrapped(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                return simulation_error(SimulationError("Invalid simulation input"), request)
            except SimulationError as exc:
                return simulation_error(exc, request)

        return wrapped


def simulation_error(exc: SimulationError, request: Request) -> JSONResponse:
    return failure(
        ApiError(exc.status_code, exc.code, str(exc)), request.state.request_id,
    )


def get_simulation_service(request: Request) -> SimulationService:
    service = getattr(request.app.state, "simulation_service", None)
    if service is None:
        raise SimulationError("Simulation storage is not configured",
                              code="SIMULATION_UNAVAILABLE", status_code=503)
    return service


def get_simulation_access(request: Request) -> SimulationAccess:
    access = getattr(request.state, "simulation_access", None)
    if access is None:
        raise SimulationError("Trusted simulation authorization is not configured",
                              code="SIMULATION_UNAVAILABLE", status_code=503)
    return access


router = APIRouter(tags=["simulations"], route_class=SimulationRoute)
Service = Annotated[SimulationService, Depends(get_simulation_service)]
Access = Annotated[SimulationAccess, Depends(get_simulation_access)]


@router.post("/cases/{case_id}/simulations", status_code=201)
def create_simulation(request: Request, case_id: UUID4, scenario: SimulationInput, service: Service, access: Access):
    return success(service.create(case_id, scenario, access), request.state.request_id, status=201)


@router.get("/cases/{case_id}/simulations")
def list_simulations(request: Request, case_id: UUID4, service: Service, access: Access):
    return success(service.list_for_case(case_id, access), request.state.request_id)


@router.get("/simulations/{simulation_id}")
def get_simulation(request: Request, simulation_id: UUID4, service: Service, access: Access):
    return success(service.detail(simulation_id, access), request.state.request_id)
