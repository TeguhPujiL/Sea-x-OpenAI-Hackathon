from datetime import datetime, timezone
from typing import Protocol

from pydantic import TypeAdapter
from uuid import UUID, uuid4

from app.schemas.shared import UtcTimestamp
from app.services.simulation.engine import (
    ENGINE_VERSION, SimulationError, SupplierCatalog, evaluate, interpret,
)
from app.services.simulation.models import SimulationInput
from app.services.simulation.repository import SimulationRepository


class SimulationAccess(Protocol):
    """Trusted backend adapter, never built from browser identity or fixture data.

    Methods must raise SimulationError on denial or absence. require_finding must
    check both finding access and its persisted relationship to case_id. A no-op
    adapter is not authorization. HTTP status/code mapping awaits shared review.
    """

    def require_case(self, case_id: UUID) -> None: ...

    def require_finding(self, case_id: UUID, finding_id: UUID) -> None: ...


class SimulationService:
    def __init__(self, repository: SimulationRepository, catalog: SupplierCatalog):
        self.repository = repository
        self.catalog = catalog

    def create(self, case_id: UUID, scenario: SimulationInput, access: SimulationAccess) -> dict:
        access.require_case(case_id)
        access.require_finding(case_id, scenario.finding_id)
        dataset = self.catalog.get(scenario.supplier_data_version)
        result = evaluate(scenario, dataset)
        snapshot = {
            "case_id": str(case_id),
            **scenario.model_dump(mode="json"),
            "quantity": dataset.quantity,
            "suppliers": [s.model_dump() for s in sorted(dataset.suppliers, key=lambda s: s.supplier_id)],
        }
        record = {
            "simulation_id": str(uuid4()), "case_id": str(case_id),
            "finding_id": str(scenario.finding_id), "engine_version": ENGINE_VERSION,
            "supplier_data_version": dataset.supplier_data_version,
            "input_snapshot": snapshot, "result": result,
            "interpretation": interpret(result), "created_at": TypeAdapter(UtcTimestamp).dump_python(datetime.now(timezone.utc), mode="json"),
        }
        self.repository.add(record)
        return record

    def list_for_case(self, case_id: UUID, access: SimulationAccess) -> list[dict]:
        access.require_case(case_id)
        records = self.repository.list_for_case(case_id)
        for record in records:
            access.require_finding(case_id, UUID(record["finding_id"]))
        return records

    def detail(self, simulation_id: UUID, access: SimulationAccess) -> dict:
        record = self.repository.get(simulation_id)
        if record is None:
            raise SimulationError("Simulation not found", code="SIMULATION_NOT_FOUND", status_code=404)
        case_id = UUID(record["case_id"])
        access.require_case(case_id)
        access.require_finding(case_id, UUID(record["finding_id"]))
        return record
