"""Integration tests against real shared tables; all seeded records are test-only."""
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError

from app.api.routes.simulations import get_simulation_service
from app.core.config import Settings
from app.core.database import build_engine, session_factory
from app.core.security import Actor, get_actor
from app.main import create_app
from app.models import Base, Case, AnalysisJob, AiExecution, Finding, Simulation, AuditEvent, IdempotencyRecord
from app.services.simulation.engine import SupplierCatalog, canonical_json
from app.services.simulation.migrate import install_simulation_guards
from app.services.simulation.service import SimulationService
from app.services.simulation.shared_repository import SharedSimulationRepository

CASE = UUID('11111111-1111-4111-8111-111111111111')
FINDING = UUID('22222222-2222-4222-8222-222222222222')
OTHER_CASE = UUID('33333333-3333-4333-8333-333333333333')
OTHER_FINDING = UUID('44444444-4444-4444-8444-444444444444')
ACTOR = Actor(UUID('55555555-5555-4555-8555-555555555555'), 'Test analyst', 'ANALYST', frozenset({'simulation:read', 'simulation:write'}))


def body(**changes):
    return {'finding_id': str(FINDING), 'baseline': {'minimum_ram_gb': 32},
            'alternative': {'minimum_ram_gb': 16}, 'supplier_data_version': 'synthetic-suppliers-v1', **changes}


class TestPolicy:
    __test__ = False
    """Explicit test-only ACL; persisted relationship checks are not overridden."""
    def __init__(self):
        self.allowed_cases = {CASE, OTHER_CASE}

    def require_case(self, case_id):
        from app.services.simulation.engine import SimulationError
        if case_id not in self.allowed_cases:
            raise SimulationError('Access denied', code='FORBIDDEN', status_code=403)

    def require_finding(self, case_id, finding_id):
        self.require_case(case_id)


@contextmanager
def make_api(tmp_path, case_id=CASE, finding_id=FINDING, other_case_id=OTHER_CASE,
             other_finding_id=OTHER_FINDING, policy=None):
    engine = build_engine(f"sqlite:///{tmp_path / 'shared.db'}")
    # Explicit test setup only; production never creates tables from API requests.
    Base.metadata.create_all(engine)
    install_simulation_guards(engine)
    factory = session_factory(engine)
    with factory() as session, session.begin():
        for index, (cid, fid) in enumerate(((case_id, finding_id), (other_case_id, other_finding_id))):
            session.add(Case(id=cid, case_number=f"SIM-TEST-{index}", title="Synthetic test case",
                             category="IT_EQUIPMENT", quantity=50, budget_ceiling_idr=900000000))
            session.flush()
            job = AnalysisJob(case_id=cid, analysis_types=["REQUIREMENT_EXTRACTION"])
            session.add(job)
            session.flush()
            execution = AiExecution(case_id=cid, job_id=job.id, provider="test-only", model="test-only",
                operation="TEST", prompt_version="test-v1", input_document_ids_json=[], schema_valid=True,
                evidence_validation_passed=True, evidence_checks_json={}, latency_ms=0)
            session.add(execution)
            session.flush()
            session.add(Finding(id=fid, case_id=cid, analysis_job_id=job.id, ai_execution_id=execution.id,
                type="REQUIREMENT_CONTRADICTION", severity="HIGH", title="Synthetic finding",
                summary="Test fixture only", confidence=1.0, evidence_status="VERIFIED"))
    service = SimulationService(SharedSimulationRepository(factory), SupplierCatalog.packaged())
    access = policy or TestPolicy()
    app = create_app(Settings(database_url="sqlite:///:memory:"))
    actor_state = {"actor": ACTOR}
    app.dependency_overrides[get_actor] = lambda: actor_state["actor"]

    @app.middleware("http")
    async def trusted_test_policy(request, call_next):
        request.state.simulation_access = access
        return await call_next(request)

    try:
        with TestClient(app) as client:
            app.state.session_factory = factory
            client.headers["Idempotency-Key"] = "test-default-key"
            yield client, service, access, factory, actor_state, app
    finally:
        engine.dispose()


@pytest.fixture
def integrated(tmp_path):
    with make_api(tmp_path) as values:
        yield values


def counts(factory):
    with factory() as session:
        return tuple(session.scalar(select(func.count()).select_from(model)) for model in (Simulation, AuditEvent, IdempotencyRecord))


def test_atomic_idempotency_replay_and_changed_input(integrated):
    client, service, _, factory, _, _ = integrated
    url = f"/api/v1/cases/{CASE}/simulations"
    first = client.post(url, json=body(), headers={"X-Request-ID": "req_original"})
    assert first.status_code == 201
    replay = client.post(url, json=dict(reversed(list(body().items()))))
    assert replay.status_code == 201 and replay.json() == first.json()
    assert counts(factory) == (1, 1, 1)
    conflict = client.post(url, json=body(alternative={"minimum_ram_gb": 32}))
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    invalid_reuse = client.post(url, json=body(supplier_data_version="unknown"))
    assert invalid_reuse.status_code == 409
    assert invalid_reuse.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert counts(factory) == (1, 1, 1)
    changed = client.post(url, json=body(alternative={"minimum_ram_gb": 32}), headers={"Idempotency-Key": "new-input"})
    assert changed.status_code == 201
    assert changed.json()["data"]["simulation_id"] != first.json()["data"]["simulation_id"]
    assert counts(factory) == (2, 2, 2)
    with factory() as session:
        audit = session.scalar(select(AuditEvent).where(AuditEvent.request_id == "req_original"))
        assert audit.actor_id == ACTOR.actor_id
        assert audit.resource_id == UUID(first.json()["data"]["simulation_id"])
    row = service.repository.get(UUID(first.json()["data"]["simulation_id"]))
    assert row["supplier_data_version"] == row["input_snapshot"]["supplier_data_version"] == "synthetic-suppliers-v1"
    assert row["engine_version"] == "supplier-eligibility-v1"
    assert "supplier_data_version" not in first.json()["data"]  # Contract gap G07.


def test_audit_failure_rolls_back_simulation_and_idempotency(integrated):
    client, _, _, factory, _, _ = integrated
    engine = factory.kw["bind"]

    def fail_audit(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise RuntimeError("injected-test-only-audit-failure")

    event.listen(engine, "before_cursor_execute", fail_audit)
    try:
        response = client.post(f"/api/v1/cases/{CASE}/simulations", json=body())
        assert response.status_code == 500
        assert "injected-test-only" not in response.text
        assert counts(factory) == (0, 0, 0)
    finally:
        event.remove(engine, "before_cursor_execute", fail_audit)


def test_persisted_relationship_and_soft_deleted_case(integrated):
    client, _, _, factory, _, _ = integrated
    url = f"/api/v1/cases/{CASE}/simulations"
    for fid in (OTHER_FINDING, uuid4()):
        response = client.post(url, json=body(finding_id=str(fid)))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert counts(factory) == (0, 0, 0)
    created = client.post(url, json=body()).json()["data"]
    with factory() as session, session.begin():
        session.get(Case, CASE).deleted_at = datetime.now(timezone.utc)
    for response in (client.post(url, json=body()), client.get(url),
                     client.get(f"/api/v1/simulations/{created['simulation_id']}")):
        assert response.status_code == 404
        assert response.json()["data"] is None
    assert counts(factory) == (1, 1, 1)


def test_read_write_scope_and_missing_key(integrated):
    client, _, _, factory, actor_state, _ = integrated
    url = f"/api/v1/cases/{CASE}/simulations"
    actor_state["actor"] = Actor(ACTOR.actor_id, ACTOR.display_name, ACTOR.role, frozenset())
    for response in (client.get(url), client.post(url, json=body()), client.get(f"/api/v1/simulations/{uuid4()}")):
        assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"
    actor_state["actor"] = ACTOR
    del client.headers["Idempotency-Key"]
    response = client.post(url, json=body())
    assert response.status_code == 400 and response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert counts(factory) == (0, 0, 0)


def test_pagination_and_reopen(integrated):
    client, service, _, factory, _, _ = integrated
    url = f"/api/v1/cases/{CASE}/simulations"
    records = [client.post(url, json=body(), headers={"Idempotency-Key": f"page-{n}"}).json()["data"] for n in range(3)]
    page = client.get(url, params={"limit": 1, "offset": 1}).json()["data"]
    assert page["pagination"] == {"limit": 1, "offset": 1, "total": 3}
    assert page["items"] == [records[1]]
    empty = client.get(url, params={"offset": 99}).json()["data"]
    assert empty["items"] == [] and empty["pagination"]["total"] == 3
    for params in ({"limit": 0}, {"offset": -1}, {"limit": "bad"}):
        response = client.get(url, params=params)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    engine = build_engine(str(factory.kw["bind"].url))
    try:
        reopened = SharedSimulationRepository(session_factory(engine))
        assert reopened.get(UUID(records[0]["simulation_id"])) == service.repository.get(UUID(records[0]["simulation_id"]))
    finally:
        engine.dispose()


@pytest.mark.parametrize("sql", [
    "UPDATE simulations SET interpretation='changed'", "DELETE FROM simulations",
    "INSERT OR REPLACE INTO simulations SELECT * FROM simulations",
    "INSERT OR REPLACE INTO simulations (rowid,id,case_id,finding_id,engine_version,supplier_data_version,input_snapshot_json,result_json,interpretation,created_at) SELECT rowid,'66666666666646668666666666666666',case_id,finding_id,engine_version,supplier_data_version,input_snapshot_json,result_json,interpretation,created_at FROM simulations",
])
def test_shared_sqlite_guards_block_mutation(integrated, sql):
    client, service, _, factory, _, _ = integrated
    record = client.post(f"/api/v1/cases/{CASE}/simulations", json=body()).json()["data"]
    with factory.kw["bind"].connect() as connection:
        with pytest.raises(IntegrityError, match="immutable"):
            connection.execute(text(sql))
        connection.rollback()
    assert service.repository.get(UUID(record["simulation_id"]))["result"] == record["result"]


def test_access_is_rechecked_before_idempotency_replay(integrated):
    client, _, access, factory, _, _ = integrated
    url = f"/api/v1/cases/{CASE}/simulations"
    assert client.post(url, json=body()).status_code == 201
    access.allowed_cases.clear()
    replay = client.post(url, json=body())
    assert replay.status_code == 403 and replay.json()["data"] is None
    assert counts(factory) == (1, 1, 1)


def test_concurrent_same_key_creates_one_record(integrated):
    from concurrent.futures import ThreadPoolExecutor

    client, _, _, factory, _, _ = integrated
    url = f"/api/v1/cases/{CASE}/simulations"
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post(url, json=body()), range(4)))
    assert [r.status_code for r in responses] == [201] * 4
    assert all(r.json() == responses[0].json() for r in responses)
    assert counts(factory) == (1, 1, 1)


def test_idempotency_is_scoped_to_actor_and_case_route(integrated):
    client, _, _, factory, actor_state, _ = integrated
    first_url = f"/api/v1/cases/{CASE}/simulations"
    first = client.post(first_url, json=body())
    actor_state["actor"] = Actor(uuid4(), "Another test actor", "ANALYST", ACTOR.scopes)
    second = client.post(first_url, json=body())
    third = client.post(f"/api/v1/cases/{OTHER_CASE}/simulations", json=body(finding_id=str(OTHER_FINDING)))
    assert first.status_code == second.status_code == third.status_code == 201
    assert len({r.json()["data"]["simulation_id"] for r in (first, second, third)}) == 3
    assert counts(factory) == (3, 3, 3)


def test_authenticated_scope_without_case_policy_fails_closed(integrated):
    _, _, _, _, _, _ = integrated
    app = create_app(Settings(database_url="sqlite:///:memory:"))
    app.dependency_overrides[get_actor] = lambda: ACTOR
    with TestClient(app) as client:
        response = client.get(f"/api/v1/cases/{CASE}/simulations")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert response.json()["data"] is None


def test_primary_contract_wire_shape_and_prd_provenance(integrated):
    import hashlib

    client, service, _, factory, _, _ = integrated
    url = f"/api/v1/cases/{CASE}/simulations"
    first = client.post(url, json=body()).json()["data"]
    second = client.post(url, json=body(), headers={"Idempotency-Key": "same-input-new-record"}).json()["data"]
    assert set(first) == {"simulation_id", "case_id", "finding_id", "engine_version", "input_snapshot", "result", "interpretation", "created_at"}
    assert set(first["input_snapshot"]) == {"quantity", "baseline", "alternative", "suppliers"}
    assert first["input_snapshot"]["suppliers"] == [
        {"supplier_ref": "SYN-A", "ram_gb": 16, "unit_price_idr": 13200000},
        {"supplier_ref": "SYN-B", "ram_gb": 16, "unit_price_idr": 13800000},
        {"supplier_ref": "SYN-C", "ram_gb": 32, "unit_price_idr": 16500000},
    ]
    stored = service.repository.get(UUID(first["simulation_id"]))
    again = service.repository.get(UUID(second["simulation_id"]))
    assert stored["result"] == again["result"]
    assert stored["input_snapshot"] == again["input_snapshot"]
    snapshot = dict(stored["input_snapshot"])
    provenance = snapshot.pop("provenance")
    expected_hash = hashlib.sha256(canonical_json({"engine_version": "supplier-eligibility-v1", "input": snapshot}).encode()).hexdigest()
    assert provenance["input_hash"] == expected_hash
    assert provenance["eligible_supplier_ids"] == {"baseline": ["SYN-C"], "alternative": ["SYN-A", "SYN-B", "SYN-C"]}
    assert len(provenance["assumptions"]) == 3
    stored["result"]["alternative"]["lowest_total_offer_idr"] = 0
    assert service.repository.get(UUID(first["simulation_id"]))["result"] == first["result"]
    assert counts(factory) == (2, 2, 2)


def test_shared_http_versions_remain_isolated(integrated):
    from app.services.simulation.models import SupplierDataset

    client, service, _, _, _, app = integrated
    golden = service.catalog.get("synthetic-suppliers-v1")
    other = golden.model_dump(mode="json")
    other["supplier_data_version"] = "test-only-independent-v2"
    other["suppliers"][0]["unit_price_idr"] = 10000000
    independent = SupplierDataset.model_validate(other)
    service.catalog = SupplierCatalog({golden.supplier_data_version: golden, independent.supplier_data_version: independent})
    app.dependency_overrides[get_simulation_service] = lambda: service
    url = f"/api/v1/cases/{CASE}/simulations"
    first = client.post(url, json=body()).json()["data"]
    separate = client.post(url, json=body(supplier_data_version=independent.supplier_data_version), headers={"Idempotency-Key": "independent-version"}).json()["data"]
    assert separate["result"]["alternative"]["lowest_total_offer_idr"] == 500000000
    assert first["result"]["alternative"]["lowest_total_offer_idr"] == 660000000
    assert client.get(f"/api/v1/simulations/{first['simulation_id']}").json()["data"] == first
    assert first["input_snapshot"]["suppliers"][0]["unit_price_idr"] == 13200000


def test_guard_migration_is_repeatable_on_existing_shared_tables(integrated):
    _, _, _, factory, _, _ = integrated
    engine = factory.kw["bind"]
    install_simulation_guards(engine)
    install_simulation_guards(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM sqlite_master WHERE type='trigger' AND tbl_name='simulations'")) == 3
    assert counts(factory) == (0, 0, 0)
