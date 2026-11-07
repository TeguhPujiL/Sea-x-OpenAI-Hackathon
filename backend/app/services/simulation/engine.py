"""Pure, integer-only counterfactual calculations over versioned server data."""
import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import Mapping

from pydantic import ValidationError

from app.services.simulation.models import SimulationInput, SupplierDataset

ENGINE_VERSION = "simulation-engine-v1"
INPUT_INVALID = "SIMULATION_INPUT_INVALID"


class SimulationError(Exception):
    def __init__(self, message: str, *, code: str = INPUT_INVALID, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class FixtureSource:
    filename: str
    sha256: str


class SupplierCatalog:
    """An immutable registry: version keys select data, never filesystem paths."""

    def __init__(self, datasets: Mapping[str, SupplierDataset]):
        checked = {}
        for version, dataset in datasets.items():
            try:
                dataset = SupplierDataset.model_validate(dataset.model_dump())
            except (AttributeError, ValidationError) as exc:
                raise SimulationError("Invalid supplier dataset") from exc
            if version != dataset.supplier_data_version:
                raise SimulationError("Supplier data version does not match its registry key")
            if len({s.supplier_id for s in dataset.suppliers}) != len(dataset.suppliers):
                raise SimulationError("Supplier identifiers must be unique")
            checked[version] = dataset
        self._datasets = MappingProxyType(checked)

    def get(self, version: str) -> SupplierDataset:
        try:
            return self._datasets[version]
        except KeyError as exc:
            raise SimulationError("Unknown supplier_data_version") from exc

    @classmethod
    def packaged(cls) -> "SupplierCatalog":
        # Explicit registry plus digest prevents silent replacement under the same version.
        from app.services.simulation.manifest import FIXTURES

        datasets = {}
        for version, source in FIXTURES.items():
            payload = files("app.services.simulation").joinpath("fixtures", source.filename).read_bytes()
            if hashlib.sha256(payload).hexdigest() != source.sha256:
                raise SimulationError("Supplier fixture integrity check failed")
            try:
                datasets[version] = SupplierDataset.model_validate_json(payload)
            except ValidationError as exc:
                raise SimulationError("Invalid supplier dataset") from exc
        return cls(datasets)


def evaluate(scenario: SimulationInput, dataset: SupplierDataset) -> dict:
    if scenario.supplier_data_version != dataset.supplier_data_version:
        raise SimulationError("Supplier data version mismatch")

    def metrics(minimum_ram_gb: int) -> dict:
        eligible = [s for s in dataset.suppliers if s.ram_gb >= minimum_ram_gb]
        if not eligible:
            # PROPOSED pending full section 8: never invent a zero or null price.
            raise SimulationError("Scenario has no eligible synthetic suppliers")
        return {
            "eligible_supplier_count": len(eligible),
            "lowest_total_offer_idr": min(s.unit_price_idr * dataset.quantity for s in eligible),
        }

    baseline = metrics(scenario.baseline.minimum_ram_gb)
    alternative = metrics(scenario.alternative.minimum_ram_gb)
    return {
        "baseline": baseline,
        "alternative": alternative,
        "delta": {key: alternative[key] - baseline[key] for key in baseline},
    }


def interpret(result: dict) -> str:
    count_delta = result["delta"]["eligible_supplier_count"]
    change = ("expands" if count_delta > 0 else "reduces" if count_delta < 0 else "preserves")
    return (
        f"The alternative {change} synthetic eligibility. "
        "The price delta is illustrative and is not evidence of actual savings, loss, "
        "overpricing, collusion, or wrongdoing."
    )
