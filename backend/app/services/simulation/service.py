from datetime import datetime, timezone
import hashlib
from typing import Protocol

from pydantic import TypeAdapter
from uuid import UUID, uuid4

from app.schemas.shared import UtcTimestamp
from app.services.simulation.engine import (
    ENGINE_VERSION, SimulationError, SupplierCatalog, canonical_json, evaluate, interpret,
)
from app.services.simulation.models import SimulationInput, to_wire_record
from app.services.simulation.repository import SimulationRepository
from app.services.simulation.shared_repository import SharedSimulationRepository


class SimulationAccess(Protocol):
    """Trusted backend adapter, never built from browser identity or fixture data.

    Methods must raise SimulationError on denial or absence. require_finding must
    check both finding access and its persisted relationship to case_id. A no-op
    adapter is not authorization. HTTP status/code mapping awaits shared review.
    """

    def require_case(self, case_id: UUID) -> None: ...

    def require_finding(self, case_id: UUID, finding_id: UUID) -> None: ...


class SimulationService:
    def __init__(self, repository: SimulationRepository | SharedSimulationRepository, catalog: SupplierCatalog):
        self.repository = repository
        self.catalog = catalog

    def build_record(self, case_id: UUID, scenario: SimulationInput, access: SimulationAccess) -> dict:
        access.require_case(case_id)
        access.require_finding(case_id, scenario.finding_id)
        dataset = self.catalog.get(scenario.supplier_data_version)
        result = evaluate(scenario, dataset)
        snapshot = {
            "case_id": str(case_id),
            **scenario.model_dump(mode="json"),
            "quantity": dataset.quantity,
            "suppliers": [s.model_dump(by_alias=True) for s in sorted(dataset.suppliers, key=lambda s: s.supplier_id)],
        }
        input_hash = hashlib.sha256(canonical_json({
            "engine_version": ENGINE_VERSION, "input": snapshot,
        }).encode()).hexdigest()
        snapshot["provenance"] = {
            "input_hash": input_hash,
            "assumptions": [
                "Synthetic supplier data; no live market coverage is implied.",
                "Quantity is fixed by the selected supplier dataset version.",
                "Eligibility uses only the minimum RAM threshold.",
            ],
            "eligible_supplier_ids": {
                name: sorted(s.supplier_id for s in dataset.suppliers if s.ram_gb >= threshold)
                for name, threshold in (
                    ("baseline", scenario.baseline.minimum_ram_gb),
                    ("alternative", scenario.alternative.minimum_ram_gb),
                )
            },
        }
        record = {
            "simulation_id": str(uuid4()), "case_id": str(case_id),
            "finding_id": str(scenario.finding_id), "engine_version": ENGINE_VERSION,
            "supplier_data_version": dataset.supplier_data_version,
            "input_snapshot": snapshot, "result": result,
            "interpretation": interpret(result), "created_at": TypeAdapter(UtcTimestamp).dump_python(datetime.now(timezone.utc), mode="json"),
        }
        return record

    def create(self, case_id: UUID, scenario: SimulationInput, access: SimulationAccess) -> dict:
        """Standalone legacy-store entry point. HTTP creation uses create_response."""
        record = self.build_record(case_id, scenario, access)
        self.repository.add(record)
        return record

    def create_response(self, case_id, scenario, access, context):
        access.require_case(case_id)
        access.require_finding(case_id, scenario.finding_id)
        request_hash = hashlib.sha256(canonical_json({
            "case_id": str(case_id), **scenario.model_dump(mode="json"),
        }).encode()).hexdigest()
        replay = self.repository.replay_if_present(case_id, scenario.finding_id, context, request_hash)
        if replay is not None:
            return replay
        record = self.build_record(case_id, scenario, access)
        return self.repository.create_atomic(record, context, request_hash)

    def list_page(self, case_id, access, limit, offset):
        access.require_case(case_id)
        records, total = self.repository.page_for_case(case_id, limit, offset)
        for record in records:
            access.require_finding(case_id, UUID(record["finding_id"]))
        return {
            "items": [self.wire_record(record) for record in records],
            "pagination": {"limit": limit, "offset": offset, "total": total},
        }

    @staticmethod
    def wire_record(record):
        return to_wire_record(record)

    def list_for_case(self, case_id: UUID, access: SimulationAccess) -> list[dict]:
        access.require_case(case_id)
        records = self.repository.list_for_case(case_id)
        for record in records:
            access.require_finding(case_id, UUID(record["finding_id"]))
        return records

    def detail(self, simulation_id: UUID, access: SimulationAccess) -> dict:
        record = self.repository.get(simulation_id)
        if record is None:
            raise SimulationError("Simulation not found", code="RESOURCE_NOT_FOUND", status_code=404)
        case_id = UUID(record["case_id"])
        access.require_case(case_id)
        access.require_finding(case_id, UUID(record["finding_id"]))
        return record
