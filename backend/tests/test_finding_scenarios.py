"""Proposed experimental feature regressions. NOT EXECUTED for this revision.

All model responses below are explicit test doubles; no live provider is called.
"""
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import build_engine
from app.core.demo_bootstrap import bootstrap
from app.core.security import Actor, get_actor
from app.main import create_app
from app.models import AiExecution, AnalysisJob, AuditEvent, Case, CaseAccess, Challenge, Document, DocumentPage, EvidenceRef, Finding, GenerationLease, IdempotencyRecord
from app.models.base import now
from app.services.ai.decisions import DecisionFailure, DecisionResult
from app.services.assurance.finding_scenarios.evidence import deterministic_checks
from app.services.assurance.finding_scenarios.migration import migrate
from app.services.assurance.finding_scenarios.models import FindingScenario
from app.services.assurance.finding_scenarios.router import router


class ScenarioStub:
    def __init__(self, mode=None, during=None):
        self.mode, self.during, self.calls = mode, during, []

    def generate(self, context):
        self.calls.append(context)
        if self.during:
            self.during()
        if self.mode == "timeout":
            raise DecisionFailure("AI_PROVIDER_TIMEOUT")
        if self.mode == "rate":
            raise DecisionFailure("RATE_LIMITED", True, "7")
        ref = dict(context["evidence"][0])
        if self.mode == "foreign_evidence":
            ref["document_id"] = str(uuid4())
        output = {"title": "Evidence reconciliation scenario", "baseline": {
            "description": "The cited source record contains an unresolved concern.", "assumptions": context["user_assumptions"], "evidence": [ref]},
            "alternatives": [{"title": "Request attributable supporting evidence", "change": "Provide the missing source explanation without replacing the original record.",
                "expected_effect": "If an attributable explanation is supplied, the concern may be clarified.",
                "limitations": ["Human source review remains required."], "evidence": [ref]}],
            "remaining_uncertainties": ["The appropriate correction remains subject to evidence review."]}
        if self.mode == "invalid_schema":
            output["unknown_field"] = True
        if self.mode == "numeric_prediction":
            output["alternatives"][0]["expected_effect"] = "If adopted, it will save 42 percent."
        return DecisionResult(json.dumps(output), "mock-scenario-model", {"input_tokens": 100, "output_tokens": 80}, "completed")


@pytest.fixture
def scenario_qa(tmp_path):
    url = "sqlite:///" + (tmp_path / "scenarios.db").as_posix()
    engine = build_engine(url)
    bootstrap(engine)
    migrate(engine)
    actor_id = uuid4()
    with Session(engine, expire_on_commit=False) as db:
        def save(row):
            db.add(row); db.flush(); return row
        case = save(Case(case_number="EXPERIMENTAL-SYNTHETIC", title="Explicit test fixture", category="IT_EQUIPMENT", quantity=50,
            budget_ceiling_idr=900000000, case_status="UNDER_ASSESSMENT", assurance_status="ACTION_REQUIRED"))
        db.add(CaseAccess(case_id=case.id, actor_id=actor_id))
        doc = save(Document(case_id=case.id, document_type="TECHNICAL_SPECIFICATION", filename="synthetic-evidence.pdf", storage_key="synthetic-scenario-evidence",
            sha256="a" * 64, size_bytes=100, page_count=1, uploaded_at=now(), processing_status="COMPLETED"))
        save(DocumentPage(document_id=doc.id, page_number=1, normalized_text="Synthetic exact requirement excerpt."))
        job = save(AnalysisJob(case_id=case.id, analysis_types=["CONTRADICTION_DETECTION"], input_document_ids_json=[str(doc.id)],
            processing_status="PROCESSING", progress_percent=50))
        execution = save(AiExecution(case_id=case.id, job_id=job.id, provider="synthetic-test-fixture", model="not-live",
            operation="TEST_ONLY", prompt_version="test-only", input_document_ids_json=[str(doc.id)], schema_valid=True,
            evidence_validation_passed=True, evidence_checks_json={"checked": 1, "passed": 1, "failed": 0}, latency_ms=0))
        finding = save(Finding(case_id=case.id, analysis_job_id=job.id, ai_execution_id=execution.id, type="EVIDENCE_CONTRADICTION",
            severity="HIGH", title="Synthetic warranty evidence concern", summary="Synthetic fixture only", confidence=1.0, evidence_status="VERIFIED"))
        save(EvidenceRef(finding_id=finding.id, document_id=doc.id, page_number=1, excerpt="Synthetic exact requirement excerpt.", verification_status="VERIFIED"))
        challenge = save(Challenge(case_id=case.id, finding_id=finding.id, status="DRAFT", question="Which source evidence explains the concern?",
            risk_rationale="Synthetic test fixture only", requested_evidence_json=["TECHNICAL_JUSTIFICATION"], human_edits=True))
        job.result_json = {"finding_ids": [str(finding.id)]}; job.processing_status = "COMPLETED"; job.progress_percent = 100
        db.commit()
    settings = Settings(database_url=url, demo_mode=True, demo_actor_id=actor_id, demo_role="REVIEWER", demo_display_name="Synthetic scenario reviewer",
        demo_scopes=frozenset({"simulation:read", "simulation:write"}))
    app = create_app(settings)
    app.include_router(router, prefix="/api/v1/experimental")
    stub = ScenarioStub(); app.state.finding_scenario_provider = stub
    with TestClient(app) as client:
        yield SimpleNamespace(engine=engine, app=app, client=client, stub=stub, actor_id=actor_id, case=case, doc=doc, finding=finding, challenge=challenge,
            path=f"/api/v1/experimental/cases/{case.id}/finding-simulations",
            payload={"finding_id": str(finding.id), "expected_case_version": 1, "expected_finding_version": 1, "assumptions": []})
    engine.dispose()


def post(qa, key="scenario-test-key", payload=None):
    return qa.client.post(qa.path, json=payload or qa.payload, headers={"Idempotency-Key": key})


def count(qa, model):
    with Session(qa.engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def test_qualitative_scenario_has_real_stub_provenance_and_immutable_reads(scenario_qa):
    qa = scenario_qa
    response = post(qa)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert response.headers["X-Experimental-Contract"] == "PROPOSED-v1.2"
    assert data["status"] == "NEEDS_REVIEW"  # Unknown quantitative methods remain explicit.
    assert data["ai_execution"]["model"] == "mock-scenario-model"
    assert data["ai_execution"]["evidence_checks"] == {"checked": 2, "passed": 2, "failed": 0}
    assert data["created_at"].endswith("Z")
    assert data["alternatives"][0]["evidence"][0]["document_id"] == str(qa.doc.id)
    detail = f"/api/v1/experimental/finding-simulations/{data['scenario_id']}"
    assert qa.client.get(detail).json()["data"] == data
    assert qa.client.get(qa.path + "?limit=1&offset=0").json()["data"]["pagination"]["total"] == 1
    assert qa.client.patch(detail, json={}).status_code == 405
    assert qa.client.delete(detail).status_code == 405
    with Session(qa.engine) as db:
        events = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "FINDING_SCENARIO_CREATED")).all()
        assert len(events) == 1 and events[0].actor_id == qa.actor_id
        assert events[0].resource_id == UUID(data["scenario_id"])


def test_idempotency_replays_before_versions_but_never_bypasses_authorization(scenario_qa):
    qa = scenario_qa
    first = post(qa); assert first.status_code == 201
    with Session(qa.engine) as db:
        db.get(Case, qa.case.id).version = 2; db.commit()
    assert post(qa).json() == first.json()
    assert len(qa.stub.calls) == 1 and count(qa, FindingScenario) == 1
    assert post(qa, payload={**qa.payload, "assumptions": ["Hypothetical source correction"]}).status_code == 409
    with Session(qa.engine) as db:
        db.delete(db.get(CaseAccess, (qa.case.id, qa.actor_id))); db.commit()
    assert post(qa).status_code == 404
    assert len(qa.stub.calls) == 1


@pytest.mark.parametrize("field", ["expected_case_version", "expected_finding_version"])
def test_stale_versions_fail_before_provider(scenario_qa, field):
    qa = scenario_qa
    response = post(qa, payload={**qa.payload, field: 2})
    assert response.status_code == 409 and response.json()["error"]["code"] == "VERSION_CONFLICT"
    assert qa.stub.calls == [] and count(qa, FindingScenario) == 0


def test_scope_cross_case_unknown_identity_and_unknown_query_are_rejected(scenario_qa):
    qa = scenario_qa
    assert qa.client.post(qa.path.replace(str(qa.case.id), str(uuid4())), json=qa.payload, headers={"Idempotency-Key": "foreign-case"}).status_code == 404
    assert post(qa, payload={**qa.payload, "actor_id": str(qa.actor_id)}).status_code == 400
    assert qa.client.get(qa.path + "?unknown=1").status_code == 400
    qa.app.dependency_overrides[get_actor] = lambda: Actor(qa.actor_id, "Trusted restricted actor", "VIEWER", frozenset({"simulation:read"}))
    assert post(qa).status_code == 403
    assert qa.stub.calls == []


def test_a_closed_or_missing_active_challenge_blocks_generation(scenario_qa):
    qa = scenario_qa
    with Session(qa.engine) as db:
        challenge = db.get(Challenge, qa.challenge.id); challenge.status = "CLOSED"; challenge.version += 1; db.commit()
    response = post(qa)
    assert response.status_code == 409 and response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert qa.stub.calls == [] and count(qa, FindingScenario) == 0


@pytest.mark.parametrize("mode,status,code", [("invalid_schema", 502, "AI_PROVIDER_ERROR"), ("foreign_evidence", 422, "EVIDENCE_VALIDATION_FAILED"),
    ("numeric_prediction", 422, "EVIDENCE_VALIDATION_FAILED"), ("timeout", 504, "AI_PROVIDER_TIMEOUT"), ("rate", 429, "RATE_LIMITED")])
def test_failures_preserve_attempt_and_audit_without_creating_scenarios(scenario_qa, mode, status, code):
    qa = scenario_qa; qa.stub.mode = mode
    response = post(qa)
    assert response.status_code == status and response.json()["error"]["code"] == code
    assert count(qa, FindingScenario) == 0 and count(qa, AiExecution) == 2
    assert count(qa, AuditEvent) == 1 and count(qa, GenerationLease) == 0
    assert post(qa).json() == response.json() and len(qa.stub.calls) == 1
    if mode == "rate":
        assert response.headers["Retry-After"] == "7"


def test_changed_source_version_during_provider_never_persists_a_stale_scenario(scenario_qa):
    qa = scenario_qa
    def change_case():
        with Session(qa.engine) as db:
            db.get(Case, qa.case.id).version += 1; db.commit()
    qa.stub.during = change_case
    response = post(qa)
    assert response.status_code == 409 and response.json()["error"]["code"] == "VERSION_CONFLICT"
    assert count(qa, FindingScenario) == 0 and count(qa, AiExecution) == 2


def test_audit_failure_rolls_back_execution_scenario_and_idempotency(scenario_qa):
    qa = scenario_qa
    original = qa.app.state.audit_service
    class FailingAudit:
        def record(self, db, command):
            original.record(db, command)
            raise RuntimeError("Explicit audit failure test double")
    qa.app.state.audit_service = FailingAudit()
    assert post(qa).status_code == 500
    assert count(qa, FindingScenario) == 0 and count(qa, AuditEvent) == 0
    assert count(qa, AiExecution) == 1 and count(qa, IdempotencyRecord) == 0
    # The pre-provider operational lease remains until expiry; it is not a business row.
    assert count(qa, GenerationLease) == 1


def test_explicit_migration_is_repeatable_and_sql_guards_prevent_rewriting(scenario_qa):
    qa = scenario_qa; migrate(qa.engine)
    assert post(qa).status_code == 201
    with qa.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert len(connection.exec_driver_sql("PRAGMA foreign_key_list(finding_scenarios)").all()) == 4
    for sql in ("UPDATE finding_scenarios SET status='DRAFT'", "DELETE FROM finding_scenarios"):
        with pytest.raises(IntegrityError):
            with qa.engine.begin() as connection:
                connection.execute(text(sql))


def test_deterministic_arithmetic_is_conservative_and_never_guesses_ambiguous_labels():
    source = "Line-item subtotal Rp760,000,000 VAT 11% x subtotal Rp83,600,000 Recomputed total Rp843,600,000 Displayed approved total Rp858,600,000"
    context = {"finding_title": "HPS arithmetic mismatch", "finding_summary": "Unreconciled owner estimate", "source_pages": [
        {"document_id": str(uuid4()), "page_number": 1, "text": source}], "document_index": []}
    checks = deterministic_checks(context, {"checked": 2, "passed": 2, "failed": 0})
    arithmetic = next(item for item in checks if item["check_type"] == "labeled_hps_integer_reconciliation")
    assert arithmetic["status"] == "CONCERN" and arithmetic["observations"]["displayed_minus_calculated_idr"] == 15000000
    context["source_pages"][0]["text"] += " Displayed approved total Rp858,600,000"
    arithmetic = next(item for item in deterministic_checks(context, {}) if item["check_type"] == "labeled_hps_integer_reconciliation")
    assert arithmetic["status"] == "UNKNOWN" and arithmetic["observations"] == {}
