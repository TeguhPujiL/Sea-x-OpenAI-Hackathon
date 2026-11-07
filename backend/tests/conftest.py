"""File-backed, migrated fixtures. These are synthetic test setup, not live AI."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import build_engine
from app.main import create_app
from app.models import (
    AiExecution, AnalysisJob, Case, Challenge, Document, DocumentPage, EvidenceRef,
    Finding, RepairProposal, Simulation,
)
from app.models.base import now
from app.services.assurance.access import get_case_grants
from app.core.demo_bootstrap import bootstrap


def seed_chain(session, *, suffix="1", clean=False, blocker=None):
    def save(row):
        session.add(row)
        session.flush()
        return row
    case = save(Case(case_number=f"SYNTHETIC-QA-{suffix}", title="Synthetic review fixture",
        category="IT_EQUIPMENT", quantity=50, budget_ceiling_idr=900000000,
        case_status="UNDER_REVIEW", assurance_status="READY_FOR_REVIEW"))
    docs = [save(Document(case_id=case.id, document_type="TECHNICAL_SPECIFICATION",
        filename=f"synthetic-{i}.pdf", storage_key=f"synthetic-{suffix}-{i}", sha256="a" * 64,
        size_bytes=100, page_count=1, uploaded_at=now(), processing_status="COMPLETED")) for i in range(2)]
    for doc in docs:
        save(DocumentPage(document_id=doc.id, page_number=1, normalized_text="Synthetic exact requirement excerpt."))
    job = save(AnalysisJob(case_id=case.id, analysis_types=["CONTRADICTION_DETECTION"],
        processing_status="PROCESSING", progress_percent=50, result_json=None))
    execution = save(AiExecution(case_id=case.id, job_id=job.id, provider="synthetic-test-fixture",
        model="not-a-live-model", operation="TEST_ONLY", prompt_version="test-v1",
        input_document_ids_json=[str(d.id) for d in docs], schema_valid=True,
        evidence_validation_passed=True, evidence_checks_json={"checked": 2, "passed": 2, "failed": 0},
        latency_ms=0, usage_json=None))
    chain = SimpleNamespace(case=case, docs=docs, job=job, execution=execution,
                            finding=None, challenge=None, simulation=None, repair=None)
    if not clean:
        finding = save(Finding(case_id=case.id, analysis_job_id=job.id, ai_execution_id=execution.id,
            type="REQUIREMENT_CONTRADICTION", severity="HIGH", title="Synthetic contradiction",
            summary="Fixture only", confidence=1.0, evidence_status=(blocker.upper()
                if blocker in {"unverified", "conflicting", "insufficient"} else "VERIFIED")))
        for doc in docs:
            save(EvidenceRef(finding_id=finding.id, document_id=doc.id, page_number=1,
                excerpt=("Not present on source page" if blocker == "bad_excerpt"
                         else "Synthetic exact requirement excerpt."), verification_status="VERIFIED"))
        challenge = save(Challenge(case_id=case.id, finding_id=finding.id, status="READY",
            question="Synthetic human-reviewed question?", risk_rationale="Fixture only",
            requested_evidence_json=[], human_edits=True))
        simulation = save(Simulation(case_id=case.id, finding_id=finding.id,
            engine_version="supplier-eligibility-v1", supplier_data_version="synthetic-suppliers-v1",
            input_snapshot_json={"quantity": 50, "baseline": {"minimum_ram_gb": 32},
                                 "alternative": {"minimum_ram_gb": 16}},
            result_json={"baseline": {"eligible_supplier_count": 1, "lowest_total_offer_idr": 825000000},
                         "alternative": {"eligible_supplier_count": 3, "lowest_total_offer_idr": 660000000},
                         "delta": {"eligible_supplier_count": 2, "lowest_total_offer_idr": -165000000}},
            interpretation="Synthetic fixture only; no live simulation was executed."))
        repair = save(RepairProposal(case_id=case.id, finding_id=finding.id, action_type="REVISE_REQUIREMENT",
            before_text="32 GB", proposed_text="16 GB with documented exception",
            justification="Synthetic draft", simulation_id=simulation.id, ai_execution_id=execution.id))
        repair.status = "SUBMITTED"
        repair.version = 2
        session.flush()
        chain.finding, chain.challenge, chain.simulation, chain.repair = finding, challenge, simulation, repair
    # Negative test scenarios are assembled before terminal execution freezes.
    # A FAILED job is the valid persisted representation of an unusable result.
    job.result_json = None if blocker == "unusable_job" else {"finding_ids": [] if clean else [str(chain.finding.id)]}
    job.warnings_json = [{"code": "EVIDENCE_EXCERPT_NOT_FOUND"}] if blocker == "job_warning" else []
    job.processing_status = "FAILED" if blocker == "unusable_job" else "NEEDS_REVIEW" if blocker == "job_warning" else "COMPLETED"
    job.progress_percent = 100
    session.commit()
    return chain


@pytest.fixture
def qa(tmp_path, request):
    url = "sqlite:///" + (tmp_path / "qa.db").as_posix()
    engine = build_engine(url)
    bootstrap(engine)
    actor_id = uuid4()
    settings = Settings(database_url=url, demo_mode=True, demo_actor_id=actor_id,
        demo_display_name="Synthetic QA Reviewer", demo_role="REVIEWER",
        demo_scopes=frozenset({"review:decide", "review:read", "audit:read"}))
    with Session(engine, expire_on_commit=False) as session:
        chain = seed_chain(session, blocker=getattr(request, "param", None))
    grants = {actor_id: frozenset({chain.case.id})}
    def make_app():
        app = create_app(settings)
        app.dependency_overrides[get_case_grants] = lambda: grants
        return app
    app = make_app()
    with TestClient(app) as client:
        yield SimpleNamespace(engine=engine, client=client, app=app, settings=settings,
            actor_id=actor_id, chain=chain, grants=grants, make_app=make_app,
            payload={"repair_proposal_id": str(chain.repair.id), "decision": "APPROVE_DRAFT",
                "decision_reason": "The verified draft addresses the documented contradiction.",
                "expected_case_version": 1},
            path=f"/api/v1/cases/{chain.case.id}/reviews")
    engine.dispose()


def post_review(qa, *, payload=None, key="qa-transport-key", **kwargs):
    headers = {"X-Request-ID": "req_qa"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return qa.client.post(qa.path, json=qa.payload if payload is None else payload, headers=headers, **kwargs)


def assert_envelope(response, status, code=None):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"success", "data", "error", "meta"}
    assert set(body["meta"]) == {"request_id", "timestamp", "api_version"}
    assert body["meta"]["timestamp"].endswith("Z")
    assert body["meta"]["api_version"] == "v1"
    assert response.headers["X-Request-ID"] == body["meta"]["request_id"]
    if code:
        assert body["success"] is False and body["data"] is None
        assert set(body["error"]) == {"code", "message", "details", "retryable"}
        assert body["error"]["code"] == code
    else:
        assert body["success"] is True and body["error"] is None
    return body
