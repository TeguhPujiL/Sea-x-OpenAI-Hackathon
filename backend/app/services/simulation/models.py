"""Simulation-local types, pending shared wire-schema review by Teguh."""
from typing import Annotated

from pydantic import ConfigDict, Field, UUID4

from app.schemas.shared import IdrAmount, StrictModel

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
    supplier_id: NonEmptyString
    ram_gb: PositiveInteger
    unit_price_idr: NonNegativeIdr


class SupplierDataset(FrozenModel):
    supplier_data_version: NonEmptyString
    quantity: PositiveInteger
    suppliers: tuple[Supplier, ...] = Field(min_length=1)
