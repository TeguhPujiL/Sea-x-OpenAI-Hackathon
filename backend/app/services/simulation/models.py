"""Simulation-local types, pending shared wire-schema review by Teguh."""
from typing import Annotated

from pydantic import AliasChoices, ConfigDict, Field, UUID4

from app.schemas.shared import IdrAmount, Pagination, SignedIdrDelta, StrictModel, UtcTimestamp

PositiveInteger = Annotated[int, Field(strict=True, gt=0)]
NonNegativeIdr = Annotated[IdrAmount, Field(ge=0)]
NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]


class FrozenModel(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Scenario(FrozenModel):
    minimum_ram_gb: PositiveInteger


class SimulationInput(FrozenModel):
    finding_id: UUID4
    baseline: Scenario
    alternative: Scenario
    supplier_data_version: NonEmptyString


class Supplier(FrozenModel):
    # Read the already published fixture bytes without rewriting its pinned version.
    supplier_id: NonEmptyString = Field(
        validation_alias=AliasChoices("supplier_id", "supplier_ref"),
        serialization_alias="supplier_ref",
    )
    ram_gb: PositiveInteger
    unit_price_idr: NonNegativeIdr


class SupplierDataset(FrozenModel):
    supplier_data_version: NonEmptyString
    quantity: PositiveInteger
    suppliers: tuple[Supplier, ...] = Field(min_length=1)


class SupplierWire(FrozenModel):
    supplier_ref: NonEmptyString
    ram_gb: PositiveInteger
    unit_price_idr: NonNegativeIdr


class InputSnapshotWire(FrozenModel):
    quantity: PositiveInteger
    baseline: Scenario
    alternative: Scenario
    suppliers: tuple[SupplierWire, ...]


class ScenarioMetrics(FrozenModel):
    eligible_supplier_count: Annotated[int, Field(strict=True, ge=0)]
    lowest_total_offer_idr: IdrAmount


class DeltaMetrics(FrozenModel):
    eligible_supplier_count: Annotated[int, Field(strict=True)]
    lowest_total_offer_idr: SignedIdrDelta


class SimulationResult(FrozenModel):
    baseline: ScenarioMetrics
    alternative: ScenarioMetrics
    delta: DeltaMetrics


class SimulationWire(FrozenModel):
    """Local Section 6.6 projection; no shared schema declaration is changed."""
    simulation_id: UUID4
    case_id: UUID4
    finding_id: UUID4
    engine_version: NonEmptyString
    input_snapshot: InputSnapshotWire
    result: SimulationResult
    interpretation: NonEmptyString
    created_at: UtcTimestamp


class SimulationPage(FrozenModel):
    items: list[SimulationWire]
    pagination: Pagination


def to_wire_record(record: dict) -> dict:
    snapshot = record["input_snapshot"]
    wire = {key: value for key, value in record.items() if key != "supplier_data_version"}
    wire["input_snapshot"] = {key: snapshot[key] for key in ("quantity", "baseline", "alternative")}
    wire["input_snapshot"]["suppliers"] = [
        {"supplier_ref": supplier.get("supplier_ref", supplier.get("supplier_id")),
         "ram_gb": supplier["ram_gb"], "unit_price_idr": supplier["unit_price_idr"]}
        for supplier in snapshot["suppliers"]
    ]
    return SimulationWire.model_validate(wire).model_dump(mode="json")
