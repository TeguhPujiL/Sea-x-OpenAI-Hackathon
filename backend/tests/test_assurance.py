from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.models import AnalysisJob, AuditEvent, Case, Document, EvidenceRef, Finding, IdempotencyRecord, RepairProposal, Review
from app.services.assurance import reviews
from conftest import assert_envelope, post_review, seed_chain


def counts(qa):
    with Session(qa.engine) as session:
        return [session.scalar(select(func.count()).select_from(m)) for m in (Review, AuditEvent, IdempotencyRecord)]


def test_review_audit_golden_boundary_and_backend_identity(qa):
    data = assert_envelope(post_review(qa), 201)["data"]
    assert data["review_status"] == "COMPLETED"
    assert data["reviewer"] == {"actor_id": str(qa.actor_id), "display_name": "Synthetic QA Reviewer", "role": "REVIEWER"}
    # An approval does not invent disposition evidence or resolve an OPEN finding.
    assert data["assurance_status_after"] == "ACTION_REQUIRED"
    assert_envelope(qa.client.get(f"/api/v1/reviews/{data['review_id']}"), 200)["data"] == data
    listing = assert_envelope(qa.client.get(qa.path), 200)["data"]
    assert listing["items"] == [data]
    assert listing["pagination"] == {"limit": 20, "offset": 0, "total": 1}
    timeline = assert_envelope(qa.client.get(qa.path.replace("/reviews", "/audit")), 200)["data"]
    assert timeline["pagination"] == {"limit": 50, "offset": 0, "total": 2}
    assert {e["event_type"] for e in timeline["items"]} == {"REVIEW_COMPLETED", "CASE_ASSURANCE_CHANGED"}
    event = next(e for e in timeline["items"] if e["event_type"] == "REVIEW_COMPLETED")
    assert event["actor"] == data["reviewer"]
    assert event["resource"] == {"type": "review", "id": data["review_id"], "version": 1}
    assert event["request_id"] == "req_qa" and event["occurred_at"].endswith("Z")
    assert event["previous_hash"] is None and event["event_hash"] is None
    assert_envelope(qa.client.get(f"/api/v1/audit-events/{event['event_id']}"), 200)["data"] == event
    with Session(qa.engine) as session:
        case = session.get(Case, qa.chain.case.id)
        assert case.version == 2 and case.assurance_status == "ACTION_REQUIRED"
        assert session.get(Finding, qa.chain.finding.id).status == "OPEN"
        assert session.get(RepairProposal, qa.chain.repair.id).status == "SUBMITTED"
    assert counts(qa) == [1, 2, 1]


@pytest.mark.parametrize("decision", ["APPROVE_DRAFT", "REQUEST_REVISION", "REQUEST_EVIDENCE", "REJECT_DRAFT"])
def test_decision_semantics_with_resolved_verified_evidence(qa, decision):
    with Session(qa.engine) as session:
        finding = session.get(Finding, qa.chain.finding.id)
        finding.status = "RESOLVED"
        finding.resolution_note = "Disposition evidence: documented requirement revision verified against both source pages."
        session.commit()
    result = assert_envelope(post_review(qa, payload={**qa.payload, "decision": decision}), 201)["data"]
    expected = "REVIEW_COMPLETED" if decision == "APPROVE_DRAFT" else "ACTION_REQUIRED"
    assert result["assurance_status_after"] == expected


@pytest.mark.parametrize("change", ["unresolved", "unverified", "conflicting", "insufficient", "no_disposition", "bad_excerpt", "job_warning", "unusable_job", "other_finding"])
def test_assurance_cannot_complete_with_blockers(qa, change):
    with Session(qa.engine) as session:
        finding = session.get(Finding, qa.chain.finding.id)
        finding.status, finding.resolution_note = "RESOLVED", "Documented source disposition."
        if change == "unresolved":
            finding.status = "UNDER_REVIEW"
        elif change in {"unverified", "conflicting", "insufficient"}:
            finding.evidence_status = change.upper()
        elif change == "no_disposition":
            finding.resolution_note = None
        elif change == "bad_excerpt":
            session.scalars(select(EvidenceRef)).first().excerpt = "Not present on source page"
        elif change == "job_warning":
            job = session.get(AnalysisJob, qa.chain.job.id)
            job.processing_status, job.warnings_json = "NEEDS_REVIEW", [{"code": "EVIDENCE_EXCERPT_NOT_FOUND"}]
        elif change == "unusable_job":
            session.get(AnalysisJob, qa.chain.job.id).result_json = None
        elif change == "other_finding":
            session.add(Finding(case_id=finding.case_id, analysis_job_id=finding.analysis_job_id,
                ai_execution_id=finding.ai_execution_id, type="TEST_ONLY", severity="LOW",
                title="Another unresolved finding", summary="Synthetic", confidence=1.0, evidence_status="VERIFIED"))
        session.commit()
    assert assert_envelope(post_review(qa), 201)["data"]["assurance_status_after"] == "ACTION_REQUIRED"


@pytest.mark.parametrize("reason", ["", "   ", "ok", "..........", "a" * 100, "two words", "x" * 4001])
def test_meaningful_reason_required(qa, reason):
    assert_envelope(post_review(qa, payload={**qa.payload, "decision_reason": reason}), 400, "VALIDATION_ERROR")
    assert counts(qa) == [0, 0, 0]


@pytest.mark.parametrize("field", ["reviewer", "reviewer_actor_id", "actor_id", "assurance_status_after", "expected_version", "unknown"])
def test_client_identity_and_unknown_fields_rejected(qa, field):
    response = post_review(qa, payload={**qa.payload, field: "private-forged-value"})
    assert_envelope(response, 400, "VALIDATION_ERROR")
    assert "private-forged-value" not in response.text


@pytest.mark.parametrize("field", ["repair_proposal_id", "decision", "decision_reason", "expected_case_version"])
def test_missing_required_fields_rejected(qa, field):
    payload = dict(qa.payload)
    payload.pop(field)
    assert_envelope(post_review(qa, payload=payload), 400, "VALIDATION_ERROR")


@pytest.mark.parametrize("version", [0, -1, True, 1.0, "1", None])
def test_strict_case_version(qa, version):
    assert_envelope(post_review(qa, payload={**qa.payload, "expected_case_version": version}), 400, "VALIDATION_ERROR")


def test_idempotency_replay_hash_ordering_and_subsequent_immutable_decision(qa):
    first = assert_envelope(post_review(qa), 201)["data"]
    second = assert_envelope(post_review(qa, payload=dict(reversed(list(qa.payload.items())))), 201)["data"]
    assert second == first
    assert counts(qa) == [1, 2, 1]
    assert_envelope(post_review(qa, payload={**qa.payload, "decision": "REQUEST_EVIDENCE"}), 409, "IDEMPOTENCY_KEY_REUSED")
    assert_envelope(post_review(qa, key="new-key"), 409, "VERSION_CONFLICT")
    subsequent = assert_envelope(post_review(qa, key="new-key", payload={**qa.payload,
        "decision": "REQUEST_EVIDENCE", "expected_case_version": 2}), 201)["data"]
    assert subsequent["review_id"] != first["review_id"]
    assert qa.client.get(f"/api/v1/reviews/{first['review_id']}").json()["data"] == first
    assert counts(qa) == [2, 4, 2]


@pytest.mark.parametrize("key", [None, "", " " * 2, "x" * 201])
def test_invalid_idempotency_keys(qa, key):
    assert_envelope(post_review(qa, key=key), 400, "VALIDATION_ERROR")
    assert counts(qa) == [0, 0, 0]


def test_stale_version_and_case_state_have_no_side_effects(qa):
    assert_envelope(post_review(qa, payload={**qa.payload, "expected_case_version": 2}), 409, "VERSION_CONFLICT")
    with Session(qa.engine) as session:
        session.get(Case, qa.chain.case.id).case_status = "ARCHIVED"
        session.commit()
    assert_envelope(post_review(qa), 409, "INVALID_STATE_TRANSITION")
    assert counts(qa) == [0, 0, 0]


def test_cross_case_and_missing_repair_hidden(qa):
    with Session(qa.engine, expire_on_commit=False) as session:
        other = seed_chain(session, suffix="other")
    for resource_id in (other.repair.id, uuid4()):
        assert_envelope(post_review(qa, payload={**qa.payload, "repair_proposal_id": str(resource_id)}), 404, "RESOURCE_NOT_FOUND")
    assert counts(qa) == [0, 0, 0]


def test_scope_and_case_authorization_even_in_demo(qa):
    qa.grants.clear()
    assert_envelope(post_review(qa), 404, "RESOURCE_NOT_FOUND")
    for path in (qa.path, qa.path.replace("/reviews", "/audit")):
        assert_envelope(qa.client.get(path), 404, "RESOURCE_NOT_FOUND")
    config = qa.settings.model_copy(update={"demo_scopes": frozenset()})
    with TestClient(create_app(config)) as client:
        assert_envelope(client.post(qa.path, json=qa.payload, headers={"Idempotency-Key": "key"}), 403, "FORBIDDEN")
    with TestClient(create_app(Settings(database_url=qa.settings.database_url))) as client:
        assert_envelope(client.post(qa.path, json=qa.payload, headers={"Idempotency-Key": "key"}), 401, "AUTHENTICATION_REQUIRED")


def test_detail_and_replay_reauthorize_current_grants(qa):
    review = assert_envelope(post_review(qa), 201)["data"]
    timeline = qa.client.get(qa.path.replace("/reviews", "/audit")).json()["data"]["items"]
    qa.grants.clear()
    assert_envelope(qa.client.get(f"/api/v1/reviews/{review['review_id']}"), 404, "RESOURCE_NOT_FOUND")
    assert_envelope(qa.client.get(f"/api/v1/audit-events/{timeline[0]['event_id']}"), 404, "RESOURCE_NOT_FOUND")
    assert_envelope(post_review(qa), 404, "RESOURCE_NOT_FOUND")


@pytest.mark.parametrize("resource", ["case", "document", "repair"])
def test_soft_deleted_references_rejected(qa, resource):
    # Repair is frozen after submission; simulate an inherited preexisting
    # tombstone only by constructing a fresh deleted draft in fixture setup.
    with Session(qa.engine, expire_on_commit=False) as session:
        if resource == "repair":
            repair = RepairProposal(case_id=qa.chain.case.id, finding_id=qa.chain.finding.id,
                action_type="REVISE_REQUIREMENT", before_text="before", proposed_text="after",
                justification="Synthetic deleted draft", deleted_at=qa.chain.case.created_at)
            session.add(repair)
            session.flush()
            qa.payload["repair_proposal_id"] = str(repair.id)
        else:
            cls, id_ = (Case, qa.chain.case.id) if resource == "case" else (Document, qa.chain.docs[0].id)
            session.get(cls, id_).deleted_at = qa.chain.case.created_at
        session.commit()
    assert_envelope(post_review(qa), 404, "RESOURCE_NOT_FOUND")
    assert counts(qa) == [0, 0, 0]


@pytest.mark.parametrize("fail_after", [1, 2, 3])
def test_atomic_rollback_no_business_audit_or_replay_rows(qa, monkeypatch, fail_after):
    original = reviews.append_audit
    calls = 0
    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        if calls == fail_after:
            raise RuntimeError("private injected failure")
        return result
    if fail_after < 3:
        monkeypatch.setattr(reviews, "append_audit", fail)
    else:
        with qa.engine.begin() as conn:
            conn.exec_driver_sql("CREATE TRIGGER fail_replay BEFORE INSERT ON idempotency_records BEGIN SELECT RAISE(ABORT, 'injected replay failure'); END")
    result = post_review(qa)
    assert_envelope(result, 500, "INTERNAL_ERROR")
    assert "private" not in result.text and "injected" not in result.text
    assert counts(qa) == [0, 0, 0]
    with Session(qa.engine) as session:
        case = session.get(Case, qa.chain.case.id)
        assert case.version == 1 and case.assurance_status == "READY_FOR_REVIEW"
    # The exact transport retry succeeds once the failure is removed.
    monkeypatch.setattr(reviews, "append_audit", original)
    with qa.engine.begin() as conn:
        conn.exec_driver_sql("DROP TRIGGER IF EXISTS fail_replay")
    assert_envelope(post_review(qa), 201)
    assert counts(qa) == [1, 2, 1]


@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_writers_have_one_atomic_winner(qa, same_key):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(post_review, qa, key="same" if same_key else f"key-{i}") for i in range(2)]
        results = [r.result() for r in futures]
    assert sorted(r.status_code for r in results) == ([201, 201] if same_key else [201, 409])
    if same_key:
        assert results[0].json()["data"] == results[1].json()["data"]
    else:
        assert next(r for r in results if r.status_code == 409).json()["error"]["code"] == "VERSION_CONFLICT"
    assert counts(qa) == [1, 2, 1]


def test_refresh_restart_persists_review_audit_and_replay(qa):
    data = assert_envelope(post_review(qa), 201)["data"]
    with TestClient(qa.make_app()) as restarted:
        assert_envelope(restarted.get(f"/api/v1/reviews/{data['review_id']}"), 200)["data"] == data
        assert restarted.get(qa.path).json()["data"]["pagination"]["total"] == 1
        assert restarted.get(qa.path.replace("/reviews", "/audit")).json()["data"]["pagination"]["total"] == 2
        replay = restarted.post(qa.path, json=qa.payload, headers={"Idempotency-Key": "qa-transport-key"})
        assert_envelope(replay, 201)["data"] == data
    assert counts(qa) == [1, 2, 1]


def test_audit_redaction_and_pagination(qa):
    assert_envelope(post_review(qa), 201)
    with Session(qa.engine) as session:
        session.add(AuditEvent(case_id=qa.chain.case.id, actor_id=qa.actor_id,
            request_id="req_legacy", event_type="UNKNOWN_FUTURE_EVENT", resource_type="case",
            resource_id=qa.chain.case.id, resource_version=2,
            details_json={"token": "secret", "raw_document": "private", "nested": {"password": "secret"}},
            occurred_at=qa.chain.case.created_at))
        session.commit()
    url = qa.path.replace("/reviews", "/audit")
    result = assert_envelope(qa.client.get(url + "?limit=1&offset=0"), 200)["data"]
    assert result["pagination"] == {"limit": 1, "offset": 0, "total": 3}
    assert result["items"][0]["details"] == {}
    assert "secret" not in str(result) and "private" not in str(result)
    assert qa.client.get(url + "?offset=100").json()["data"]["items"] == []
    for query in ("?limit=0", "?offset=-1", "?limit=201", "?unknown=value"):
        assert_envelope(qa.client.get(url + query), 400, "VALIDATION_ERROR")


def test_clean_case_gap_rejects_approve_case_without_fabrication(qa):
    with Session(qa.engine, expire_on_commit=False) as session:
        clean = seed_chain(session, suffix="clean", clean=True)
    qa.grants[qa.actor_id] = frozenset({qa.chain.case.id, clean.case.id})
    path = f"/api/v1/cases/{clean.case.id}/reviews"
    for payload in ({"decision": "APPROVE_CASE", "decision_reason": "No contradiction was found.", "expected_case_version": 1},
                    {**qa.payload, "decision": "APPROVE_CASE"}):
        assert_envelope(qa.client.post(path, json=payload, headers={"Idempotency-Key": "clean"}), 400, "VALIDATION_ERROR")
    # An existing repair from another case cannot fill the contract gap.
    assert_envelope(qa.client.post(path, json=qa.payload, headers={"Idempotency-Key": "clean"}), 404, "RESOURCE_NOT_FOUND")
    with Session(qa.engine) as session:
        assert session.get(AnalysisJob, clean.job.id).result_json == {"finding_ids": []}
        for cls in (Finding, RepairProposal, Review, AuditEvent):
            assert session.scalar(select(func.count()).select_from(cls).where(cls.case_id == clean.case.id)) == 0
    assert qa.client.get(path).json()["data"]["items"] == []


def test_no_review_or_audit_mutation_routes(qa):
    review = assert_envelope(post_review(qa), 201)["data"]
    events = qa.client.get(qa.path.replace("/reviews", "/audit")).json()["data"]["items"]
    for path in (f"/api/v1/reviews/{review['review_id']}", f"/api/v1/audit-events/{events[0]['event_id']}"):
        for method in ("patch", "put", "delete"):
            response = getattr(qa.client, method)(path)
            assert response.status_code == 405
            assert response.json()["success"] is False
    assert counts(qa) == [1, 2, 1]


@pytest.mark.parametrize("retried", [False, True])
def test_failed_job_blocks_assurance_until_completed_retry(qa, retried):
    # Provider/job service is not present on this branch. This seeds its
    # persisted failure/retry contract at the review integration boundary.
    with Session(qa.engine) as session:
        finding = session.get(Finding, qa.chain.finding.id)
        finding.status, finding.resolution_note = "RESOLVED", "Verified source disposition evidence."
        failed = AnalysisJob(case_id=qa.chain.case.id, analysis_types=["CONTRADICTION_DETECTION"],
            processing_status="FAILED", result_json=None,
            error_json={"code": "AI_PROVIDER_TIMEOUT", "retryable": True})
        session.add(failed)
        session.flush()
        if retried:
            session.add(AnalysisJob(case_id=qa.chain.case.id, retry_of_job_id=failed.id,
                analysis_types=["CONTRADICTION_DETECTION"], processing_status="COMPLETED",
                result_json={"finding_ids": []}, warnings_json=[]))
        failed_id = failed.id
        session.commit()
    outcome = assert_envelope(post_review(qa), 201)["data"]["assurance_status_after"]
    assert outcome == ("REVIEW_COMPLETED" if retried else "ACTION_REQUIRED")
    with Session(qa.engine) as session:
        original = session.get(AnalysisJob, failed_id)
        assert original.processing_status == "FAILED" and original.result_json is None


def test_draft_repair_cannot_be_reviewed_and_headers_cannot_forge_actor(qa):
    with Session(qa.engine, expire_on_commit=False) as session:
        draft = RepairProposal(case_id=qa.chain.case.id, finding_id=qa.chain.finding.id,
            action_type="REVISE_REQUIREMENT", before_text="Before", proposed_text="Draft",
            justification="Synthetic unsubmitted draft")
        session.add(draft)
        session.commit()
    assert_envelope(post_review(qa, payload={**qa.payload, "repair_proposal_id": str(draft.id)}), 409, "INVALID_STATE_TRANSITION")
    response = qa.client.post(qa.path, json=qa.payload, headers={"Idempotency-Key": "headers",
        "X-Actor-ID": str(uuid4()), "X-Reviewer-ID": str(uuid4()), "X-Role": "ADMIN"})
    assert assert_envelope(response, 201)["data"]["reviewer"]["actor_id"] == str(qa.actor_id)


def test_persistence_after_starting_a_fresh_python_process(qa):
    review = assert_envelope(post_review(qa), 201)["data"]
    # A fresh interpreter creates its own app, engine and connections; no
    # Python singleton or in-memory fixture can supply the returned records.
    code = """
import json, sys
from uuid import UUID
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import create_app
from app.services.assurance.access import get_case_grants
url, actor, case, review = sys.argv[1:]
actor, case = UUID(actor), UUID(case)
app = create_app(Settings(database_url=url, demo_mode=True, demo_actor_id=actor,
    demo_scopes=frozenset({'review:read', 'audit:read'})))
app.dependency_overrides[get_case_grants] = lambda: {actor: frozenset({case})}
with TestClient(app) as client:
    detail = client.get('/api/v1/reviews/' + review)
    audit = client.get('/api/v1/cases/' + str(case) + '/audit')
    assert detail.status_code == 200 and audit.status_code == 200
    print(json.dumps({'review': detail.json()['data'], 'audit_total': audit.json()['data']['pagination']['total']}))
"""
    result = subprocess.run([sys.executable, "-c", code, qa.settings.database_url,
        str(qa.actor_id), str(qa.chain.case.id), review["review_id"]], capture_output=True,
        text=True, timeout=30, check=True)
    persisted = json.loads(result.stdout)
    assert persisted == {"review": review, "audit_total": 2}
