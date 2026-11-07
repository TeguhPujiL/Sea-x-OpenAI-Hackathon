import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from importlib.resources import files
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routes.simulations import get_simulation_access
from app.main import create_app
from app.core.config import Settings
from app.schemas.shared import Envelope
from app.services.simulation.engine import (
    ENGINE_VERSION, SimulationError, SupplierCatalog, canonical_json, evaluate, interpret,
)
from app.services.simulation.manifest import FIXTURES
from app.services.simulation.models import SimulationInput, SupplierDataset
from app.services.simulation.repository import SimulationRepository
from app.services.simulation.service import SimulationService

CASE_ID = UUID("11111111-1111-4111-8111-111111111111")
FINDING_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_CASE_ID = UUID("33333333-3333-4333-8333-333333333333")
OTHER_FINDING_ID = UUID("44444444-4444-4444-8444-444444444444")
GOLDEN = {
    "baseline": {"eligible_supplier_count": 1, "lowest_total_offer_idr": 825000000},
    "alternative": {"eligible_supplier_count": 3, "lowest_total_offer_idr": 660000000},
    "delta": {"eligible_supplier_count": 2, "lowest_total_offer_idr": -165000000},
}


def payload(**changes):
    return {
        "finding_id": str(FINDING_ID), "baseline": {"minimum_ram_gb": 32},
        "alternative": {"minimum_ram_gb": 16},
        "supplier_data_version": "synthetic-suppliers-v1", **changes,
    }


@dataclass
class TestAccess:
    # Test-only stand-in for the trusted case/finding ACL adapter.
    __test__ = False
    allowed_cases: set = field(default_factory=lambda: {CASE_ID, OTHER_CASE_ID})
    findings: dict = field(default_factory=lambda: {FINDING_ID: CASE_ID, OTHER_FINDING_ID: OTHER_CASE_ID})

    def require_case(self, case_id):
        if case_id not in self.allowed_cases:
            raise SimulationError("Access denied", code="FORBIDDEN", status_code=403)

    def require_finding(self, case_id, finding_id):
        if self.findings.get(finding_id) != case_id:
            raise SimulationError("Finding is unavailable for case", code="FORBIDDEN", status_code=403)


@pytest.fixture
def setup_service(tmp_path):
    path = tmp_path / "simulations.db"
    repository = SimulationRepository(path)
    repository.provision()
    service = SimulationService(repository, SupplierCatalog.packaged())
    yield service, path
    repository.close()


@pytest.fixture
def api(tmp_path):
    from test_simulation_shared import make_api
    with make_api(tmp_path, CASE_ID, FINDING_ID, OTHER_CASE_ID, OTHER_FINDING_ID, TestAccess()) as values:
        yield values[:3]


def test_golden_fixture_manifest_and_repeatability():
    catalog = SupplierCatalog.packaged()
    dataset = catalog.get("synthetic-suppliers-v1")
    assert dataset.quantity == 50
    assert [(s.supplier_id, s.ram_gb, s.unit_price_idr, s.unit_price_idr * dataset.quantity)
            for s in dataset.suppliers] == [
        ("SYN-A", 16, 13200000, 660000000),
        ("SYN-B", 16, 13800000, 690000000),
        ("SYN-C", 32, 16500000, 825000000),
    ]
    fixture = FIXTURES[dataset.supplier_data_version]
    raw = files("app.services.simulation").joinpath("fixtures", fixture.filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == fixture.sha256
    scenario = SimulationInput.model_validate(payload())
    assert evaluate(scenario, dataset) == GOLDEN
    assert ENGINE_VERSION == "supplier-eligibility-v1"
    reordered = dict(reversed(list(payload().items())))
    normalized = SimulationInput.model_validate(reordered)
    assert canonical_json(scenario.model_dump(mode="json")) == canonical_json(normalized.model_dump(mode="json"))
    for _ in range(10):
        assert canonical_json(evaluate(normalized, dataset)) == canonical_json(GOLDEN)
    assert interpret(GOLDEN) == (
        "The alternative expands synthetic eligibility. The price delta is illustrative "
        "and is not evidence of actual savings, loss, overpricing, collusion, or wrongdoing."
    )


def test_persistence_reopen_replay_and_new_record(setup_service):
    service, path = setup_service
    scenario = SimulationInput.model_validate(payload())
    first = service.create(CASE_ID, scenario, TestAccess())
    second = service.create(CASE_ID, scenario, TestAccess())
    changed = service.create(CASE_ID, SimulationInput.model_validate(
        payload(alternative={"minimum_ram_gb": 32})), TestAccess())
    assert len({first["simulation_id"], second["simulation_id"], changed["simulation_id"]}) == 3
    assert first["input_snapshot"] == second["input_snapshot"]
    assert first["result"] == second["result"] == GOLDEN
    assert UUID(first["simulation_id"]).version == 4
    assert first["created_at"].endswith("Z")
    persisted = SimulationRepository(path)
    try:
        restored = persisted.get(UUID(first["simulation_id"]))
        assert restored == first
        snapshot = restored["input_snapshot"]
        request = SimulationInput.model_validate({key: snapshot[key] for key in payload()})
        dataset = SupplierDataset.model_validate({key: snapshot[key] for key in (
            "supplier_data_version", "quantity", "suppliers")})
        assert evaluate(request, dataset) == GOLDEN
        restored["result"]["baseline"]["lowest_total_offer_idr"] = 0
        assert persisted.get(UUID(first["simulation_id"])) == first
        assert service.detail(UUID(first["simulation_id"]), TestAccess()) == first
    finally:
        persisted.close()


@pytest.mark.parametrize("statement", [
    "UPDATE simulations SET interpretation='tampered'",
    "DELETE FROM simulations",
    "INSERT OR REPLACE INTO simulations SELECT * FROM simulations",
    "REPLACE INTO simulations SELECT * FROM simulations",
    "INSERT OR REPLACE INTO simulations SELECT sequence, 'replacement-id', case_id, finding_id, engine_version, supplier_data_version, input_snapshot, result, interpretation, created_at FROM simulations",
])
def test_database_rejects_mutation(setup_service, statement):
    service, path = setup_service
    record = service.create(CASE_ID, SimulationInput.model_validate(payload()), TestAccess())
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(statement)
    assert service.repository.get(UUID(record["simulation_id"])) == record


def test_api_create_list_detail_and_no_mutation_routes(api):
    client, _, _ = api
    url = f"/api/v1/cases/{CASE_ID}/simulations"
    response = client.post(url, json=payload())
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"success", "data", "error", "meta"}
    Envelope[dict].model_validate(body)
    assert body["success"] is True and body["error"] is None
    assert body["meta"]["request_id"] == response.headers["X-Request-ID"]
    assert body["meta"]["timestamp"].endswith("Z")
    assert body["meta"]["api_version"] == "v1"
    record = body["data"]
    assert record["result"] == GOLDEN
    assert client.get(url).json()["data"]["items"] == [record]
    detail_url = f"/api/v1/simulations/{record['simulation_id']}"
    assert client.get(detail_url).json()["data"] == record
    assert client.patch(detail_url, json={"baseline": {"minimum_ram_gb": 16}}).status_code == 405
    assert client.delete(detail_url).status_code == 405
    assert client.get(detail_url).json()["data"] == record
    assert client.get(f"/api/v1/cases/{OTHER_CASE_ID}/simulations").json()["data"]["items"] == []
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"][detail_url.rsplit("/", 1)[0] + "/{simulation_id}"]) == {"get"}


@pytest.mark.parametrize("changes", [
    {"supplier_data_version": "unknown"}, {"supplier_data_version": "../../etc/passwd"},
    {"supplier_data_version": None}, {"supplier_data_version": ""},
    {"baseline": {"minimum_ram_gb": 0}}, {"baseline": {"minimum_ram_gb": -1}},
    {"baseline": {"minimum_ram_gb": 16.0}}, {"baseline": {"minimum_ram_gb": "16"}},
    {"baseline": {"minimum_ram_gb": True}}, {"baseline": {}},
    {"baseline": {"minimum_ram_gb": 16, "operator": "<="}},
    {"alternative": {"minimum_ram_gb": 64}}, {"baseline": {"minimum_ram_gb": 64}},
    {"suppliers": []}, {"unit_price_idr": 1}, {"quantity": 50},
    {"operator": ">="}, {"finding_id": str(UUID(int=0))}, {"finding_id": "broken"},
])
def test_invalid_requests_have_stable_error_and_no_writes(api, changes):
    client, service, _ = api
    response = client.post(f"/api/v1/cases/{CASE_ID}/simulations", json=payload(**changes))
    structural = any(k in changes for k in ("suppliers", "unit_price_idr", "quantity", "operator", "finding_id")) or "operator" in changes.get("baseline", {})
    assert response.status_code == (400 if structural else 422)
    body = response.json()
    Envelope[dict].model_validate(body)
    assert body["success"] is False and body["data"] is None
    assert body["error"]["code"] == ("VALIDATION_ERROR" if structural else "SIMULATION_INPUT_INVALID")
    assert isinstance(body["error"]["details"], list) and body["error"]["retryable"] is False
    assert body["meta"]["request_id"] == response.headers["X-Request-ID"]
    assert service.repository.list_for_case(CASE_ID) == []


@pytest.mark.parametrize("body", [None, [], {}, "text", {"baseline": {"minimum_ram_gb": 32}}])
def test_missing_fields_and_wrong_body_type(api, body):
    client, _, _ = api
    response = client.post(f"/api/v1/cases/{CASE_ID}/simulations", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_json_and_ids(api):
    client, _, _ = api
    response = client.post(f"/api/v1/cases/{CASE_ID}/simulations", content="{", headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    for url in ("/api/v1/cases/not-a-uuid/simulations", "/api/v1/simulations/not-a-uuid"):
        assert client.get(url).status_code == 400
        assert client.get(url).json()["error"]["code"] == "VALIDATION_ERROR"


def test_case_finding_and_read_authorization(api):
    client, service, access = api
    url = f"/api/v1/cases/{CASE_ID}/simulations"
    for finding in (OTHER_FINDING_ID, uuid4()):
        assert client.post(url, json=payload(finding_id=str(finding))).status_code == 403
    assert service.repository.list_for_case(CASE_ID) == []
    record = client.post(url, json=payload()).json()["data"]
    access.allowed_cases.clear()
    for response in (
        client.post(url, json=payload()), client.get(url),
        client.get(f"/api/v1/simulations/{record['simulation_id']}"),
    ):
        assert response.status_code == 403
        assert response.json()["success"] is False
        assert response.json()["data"] is None
    assert len(service.repository.list_for_case(CASE_ID)) == 1
    access.allowed_cases.add(CASE_ID)
    access.findings.clear()
    assert client.get(url).status_code == 403
    assert client.get(f"/api/v1/simulations/{record['simulation_id']}").status_code == 403


def test_missing_simulation_and_unconfigured_integration(api):
    client, service, _ = api
    missing = client.get(f"/api/v1/simulations/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    app = create_app(Settings(database_url="sqlite:///:memory:"))
    with TestClient(app) as unconfigured:
        assert unconfigured.post(f"/api/v1/cases/{CASE_ID}/simulations", json=payload()).status_code == 401
        response = unconfigured.get(f"/api/v1/cases/{CASE_ID}/simulations", headers={"X-Actor-Id": str(uuid4())})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize("field,value", [
    ("unit_price_idr", -1), ("unit_price_idr", 1.5), ("unit_price_idr", "13200000"),
    ("unit_price_idr", True), ("unit_price_idr", None), ("ram_gb", 0),
    ("ram_gb", -16), ("ram_gb", 16.0), ("ram_gb", True),
])
def test_reject_malformed_server_suppliers(field, value):
    data = SupplierCatalog.packaged().get("synthetic-suppliers-v1").model_dump(mode="json")
    data["suppliers"][0][field] = value
    with pytest.raises(ValidationError):
        SupplierDataset.model_validate(data)


def test_zero_prices_and_arbitrary_precision_integer_math():
    data = SupplierCatalog.packaged().get("synthetic-suppliers-v1").model_dump(mode="json")
    data["suppliers"][0]["unit_price_idr"] = 0
    dataset = SupplierDataset.model_validate(data)
    request = SimulationInput.model_validate(payload())
    assert evaluate(request, dataset)["alternative"]["lowest_total_offer_idr"] == 0
    for supplier in data["suppliers"]:
        supplier["unit_price_idr"] = 2**63 + 1
    result = evaluate(request, SupplierDataset.model_validate(data))
    assert result["baseline"]["lowest_total_offer_idr"] == (2**63 + 1) * 50
    assert all(type(value) is int for metrics in result.values() for value in metrics.values())


def test_data_versions_are_isolated_and_mismatches_rejected(setup_service):
    service, _ = setup_service
    golden_data = service.catalog.get("synthetic-suppliers-v1")
    data = golden_data.model_dump(mode="json")
    # An independent, clearly test-only version; never the negative PDF price pack.
    data["supplier_data_version"] = "test-only-independent-v2"
    data["suppliers"][0]["unit_price_idr"] = 10000000
    other = SupplierDataset.model_validate(data)
    service.catalog = SupplierCatalog({golden_data.supplier_data_version: golden_data, other.supplier_data_version: other})
    before = service.create(CASE_ID, SimulationInput.model_validate(payload()), TestAccess())
    separate = service.create(CASE_ID, SimulationInput.model_validate(payload(supplier_data_version=other.supplier_data_version)), TestAccess())
    assert separate["result"]["alternative"]["lowest_total_offer_idr"] == 500000000
    assert service.create(CASE_ID, SimulationInput.model_validate(payload()), TestAccess())["result"] == GOLDEN
    assert service.detail(UUID(before["simulation_id"]), TestAccess())["result"] == GOLDEN
    with pytest.raises(SimulationError, match="version mismatch"):
        evaluate(SimulationInput.model_validate(payload()), other)
    with pytest.raises(SimulationError, match="registry key"):
        SupplierCatalog({"wrong": golden_data})
    data["suppliers"].append(data["suppliers"][0])
    with pytest.raises(SimulationError, match="unique"):
        SupplierCatalog({other.supplier_data_version: SupplierDataset.model_validate(data)})


@pytest.mark.parametrize("changes", [
    {"quantity": 0}, {"quantity": -50}, {"quantity": 50.0}, {"quantity": True},
    {"suppliers": []}, {"suppliers": None}, {"supplier_data_version": None},
])
def test_invalid_dataset_metadata(changes):
    data = SupplierCatalog.packaged().get("synthetic-suppliers-v1").model_dump(mode="json")
    with pytest.raises(ValidationError):
        SupplierDataset.model_validate({**data, **changes})


def test_fixture_checksum_detects_modified_bytes(monkeypatch):
    class ModifiedResource:
        def joinpath(self, *args):
            return self

        def read_bytes(self):
            return b'{"tampered": true}'

    monkeypatch.setattr("app.services.simulation.engine.files", lambda name: ModifiedResource())
    with pytest.raises(SimulationError, match="integrity"):
        SupplierCatalog.packaged()


@pytest.mark.parametrize("baseline,alternative,count_delta,price_delta,verb", [
    (16, 32, -2, 165000000, "reduces"),
    (16, 16, 0, 0, "preserves"),
])
def test_reverse_and_unchanged_scenarios(baseline, alternative, count_delta, price_delta, verb):
    dataset = SupplierCatalog.packaged().get("synthetic-suppliers-v1")
    request = SimulationInput.model_validate(payload(
        baseline={"minimum_ram_gb": baseline}, alternative={"minimum_ram_gb": alternative},
    ))
    result = evaluate(request, dataset)
    assert result["delta"] == {"eligible_supplier_count": count_delta, "lowest_total_offer_idr": price_delta}
    assert interpret(result).startswith(f"The alternative {verb} synthetic eligibility.")
