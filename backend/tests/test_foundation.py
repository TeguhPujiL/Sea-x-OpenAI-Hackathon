import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.response import ApiError
from app.core.config import Settings
from app.core.database import build_engine
from app.core.security import check_version, get_actor, require_idempotency_key
from app.main import create_app
from app.models import Base, Case, AiExecution, AuditEvent, AnalysisJob, Finding, Simulation, RepairProposal, Review
from app.schemas import shared


def test_health_openapi_and_safe_errors():
    app = create_app(Settings(database_url="sqlite:///:memory:"))

    @app.post("/test-validation")
    def validate(payload: shared.VersionedMutation):
        return payload

    @app.get("/test-crash")
    def crash():
        raise RuntimeError("private-provider-secret")

    with TestClient(app) as client:
        r = client.get("/api/v1/health", headers={"X-Request-ID": "req_test"})
        body = r.json()
        assert r.status_code == 200
        assert set(body) == {"success", "data", "error", "meta"}
        assert body["success"] and body["error"] is None
        assert body["meta"]["request_id"] == "req_test"
        assert body["meta"]["timestamp"].endswith("Z")
        assert body["meta"]["api_version"] == "v1"
        assert body["data"]["demo_mode"] is False
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert schema.json()["openapi"].startswith("3.1")
        bad = client.post("/test-validation", json={"expected_version": 1, "reviewer": "forged"})
        assert bad.status_code == 400
        assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "forged" not in bad.text
        assert client.get("/missing").json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        failure = client.get("/test-crash")
        assert failure.status_code == 500
        assert "private-provider-secret" not in failure.text


def test_registered_routes_follow_contract_inventory():
    paths = create_app().openapi()["paths"]
    snapshot = json.loads((Path(__file__).resolve().parents[2] / "docs/contract_snapshot.json").read_text())
    contracted = {
        (endpoint["method"].lower(), snapshot["base_path"] + endpoint["path"]): endpoint["success_code"]
        for endpoint in snapshot["endpoints"]
    }
    # Health is an explicit foundation exception, separate from business APIs.
    assert "get" in paths["/api/v1/health"]
    assert "200" in paths["/api/v1/health"]["get"]["responses"]
    assert {
        "/api/v1/cases/{case_id}/reviews", "/api/v1/reviews/{review_id}",
        "/api/v1/cases/{case_id}/audit", "/api/v1/audit-events/{event_id}",
        "/api/v1/cases/{case_id}/simulations", "/api/v1/simulations/{simulation_id}",
    } <= set(paths)
    http_methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
    for path, operations in paths.items():
        for method in http_methods.intersection(operations):
            if (method, path) == ("get", "/api/v1/health"):
                continue
            assert (method, path) in contracted, f"Uncontracted endpoint: {method.upper()} {path}"
            expected_status = str(contracted[(method, path)])
            assert expected_status in operations[method]["responses"], (
                f"{method.upper()} {path} must declare success status {expected_status}"
            )


def test_enum_sets_match_checked_contract():
    snapshot = json.loads((Path(__file__).resolve().parents[2] / "docs/contract_snapshot.json").read_text())
    for name, values in snapshot["enums"].items():
        assert [e.value for e in getattr(shared, name)] == values
    assert "APPROVE_CASE" not in {e.value for e in shared.ReviewDecision}


@pytest.mark.parametrize("value", [1.5, "100", True, -1])
def test_idr_rejects_non_integer_and_negative(value):
    with pytest.raises(ValidationError):
        TypeAdapter(shared.IdrAmount).validate_python(value)


def test_uuid_time_and_closed_models():
    assert TypeAdapter(shared.ResourceId).validate_python(uuid4()).version == 4
    with pytest.raises(ValidationError):
        TypeAdapter(shared.ResourceId).validate_python("11111111-1111-1111-8111-111111111111")
    adapter = TypeAdapter(shared.UtcTimestamp)
    assert adapter.dump_json(adapter.validate_python(datetime.now(timezone.utc))).endswith(b'Z"')
    with pytest.raises(ValidationError):
        adapter.validate_python(datetime(2026, 11, 7))
    with pytest.raises(ValidationError):
        shared.StrictModel(unknown=True)


def test_identity_idempotency_and_version_primitives():
    with pytest.raises(ApiError) as exc:
        get_actor(Settings())
    assert exc.value.status == 401
    actor_id = uuid4()
    actor = get_actor(Settings(demo_mode=True, demo_actor_id=actor_id))
    assert actor.actor_id == actor_id
    assert not actor.scopes
    with pytest.raises(ValidationError):
        Settings(demo_mode=True)
    with pytest.raises(ApiError) as exc:
        require_idempotency_key(None)
    assert exc.value.status == 400
    assert require_idempotency_key("transport-retry-key") == "transport-retry-key"
    with pytest.raises(ApiError) as exc:
        check_version(2, 1)
    assert exc.value.code == "VERSION_CONFLICT"


def test_sqlite_schema_and_constraints():
    engine = build_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as conn:
            assert conn.scalar(text("PRAGMA foreign_keys")) == 1
            assert conn.scalar(text("SELECT count(*) FROM sqlite_master WHERE type='trigger'")) == 8
        with Session(engine) as session:
            session.add(Case(case_number="TEST-1", title="Synthetic", category="IT_EQUIPMENT", quantity=1,
                             budget_ceiling_idr=-1))
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()
    finally:
        engine.dispose()


def populate_immutable_rows(session):
    def save(obj):
        session.add(obj)
        session.flush()
        return obj
    case = save(Case(case_number="TEST-1", title="Synthetic", category="IT_EQUIPMENT", quantity=1, budget_ceiling_idr=0))
    job = save(AnalysisJob(case_id=case.id, analysis_types=["REQUIREMENT_EXTRACTION"]))
    execution = save(AiExecution(case_id=case.id, job_id=job.id, provider="test-only", model="test-only",
        operation="TEST", prompt_version="test-v1", input_document_ids_json=[], schema_valid=True,
        evidence_validation_passed=True, evidence_checks_json={}, latency_ms=0))
    finding = save(Finding(case_id=case.id, analysis_job_id=job.id, ai_execution_id=execution.id,
        type="REQUIREMENT_CONTRADICTION", severity="HIGH", title="Test only", summary="Test only",
        confidence=1.0, evidence_status="VERIFIED"))
    simulation = save(Simulation(case_id=case.id, finding_id=finding.id, engine_version="test-v1",
        supplier_data_version="test-v1", input_snapshot_json={}, result_json={}, interpretation="Test only"))
    repair = save(RepairProposal(case_id=case.id, finding_id=finding.id, action_type="REVISE_REQUIREMENT",
        before_text="Before", proposed_text="After", justification="Test only"))
    review = save(Review(case_id=case.id, repair_proposal_id=repair.id, decision="REQUEST_EVIDENCE",
        decision_reason="Test only", reviewer_actor_id=uuid4(), reviewer_snapshot_json={}, assurance_status_after="ACTION_REQUIRED"))
    audit = save(AuditEvent(case_id=case.id, actor_id=uuid4(), request_id="req_test", event_type="TEST",
        resource_type="case", resource_id=case.id, resource_version=1, details_json={}, occurred_at=datetime.now(timezone.utc)))
    session.commit()
    return [execution, simulation, review, audit]


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_immutable_records_block_orm_and_sql_changes(index):
    engine = build_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            row = populate_immutable_rows(session)[index]
            column = {"ai_executions": "model", "simulations": "interpretation", "reviews": "decision_reason", "audit_events": "event_type"}[row.__tablename__]
            setattr(row, column, "changed")
            with pytest.raises(ValueError):
                session.flush()
            session.rollback()
            table_name = row.__tablename__
            for operation in (f"UPDATE {table_name} SET id=id", f"DELETE FROM {table_name}"):
                with pytest.raises(IntegrityError):
                    session.execute(text(operation))
                session.rollback()
            session.delete(row)
            with pytest.raises(ValueError):
                session.flush()
            session.rollback()
    finally:
        engine.dispose()
