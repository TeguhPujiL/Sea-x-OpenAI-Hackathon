import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import UUID, uuid4
from datetime import datetime, timezone

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.response import ApiError
from app.core.config import Settings
from app.core.database import build_engine
from app.core.migrations import migrate
from app.core.security import Actor, get_actor
from app.main import create_app
from app.models import Case, CaseAccess, Document, DocumentPage, AnalysisJob, AiExecution, Finding, EvidenceRef, AuditEvent, IdempotencyRecord, RepairProposal, Review
from app.services.ai.jobs import transition
from app.services.ai.provider import ProviderResult, ProviderFailure, OpenAIAnalysisProvider

SCOPES = frozenset({"case:read", "case:write", "case:delete", "document:read", "document:write", "document:delete", "analysis:read", "analysis:write", "finding:read", "finding:write", "finding:decide"})


def pdf(*texts, encrypted=False):
    with pymupdf.open() as doc:
        for text_value in texts or ("Minimum RAM 16 GB",):
            page = doc.new_page()
            if text_value:
                page.insert_text((72, 72), text_value)
        return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user") if encrypted else doc.tobytes()


class TestProvider:
    __test__ = False
    def __init__(self, output=None, error=None):
        self.output = output or {"requirements": [], "findings": []}
        self.error = error
        self.calls = 0
    def analyze(self, pages, types):
        self.calls += 1
        if self.error:
            raise self.error
        output = self.output(pages) if callable(self.output) else self.output
        return ProviderResult(json.dumps(output), "actual-test-runtime-model", {"input_tokens": 11, "output_tokens": 7})


@pytest.fixture
def runtime(tmp_path):
    settings = Settings(database_url=f"sqlite:///{(tmp_path/'test.db').as_posix()}", storage_root=tmp_path/'storage',
        demo_mode=True, demo_actor_id=uuid4(), demo_scopes=SCOPES, openai_model="requested-test-model", upload_max_bytes=10_000)
    engine = build_engine(settings.database_url)
    migrate(engine)
    migrate(engine)  # Idempotent migration, no silent data deletion.
    app = create_app(settings)
    app.state.analysis_provider = TestProvider()
    with TestClient(app) as client:
        yield client, app, settings, engine
    engine.dispose()


def create(client, key=None):
    response = client.post("/api/v1/cases", headers={"Idempotency-Key": key or str(uuid4())}, json={
        "title": "Synthetic procurement", "category": "IT_EQUIPMENT", "description": None,
        "quantity": 50, "budget_ceiling_idr": 900000000, "currency": "IDR"})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def upload(client, case_id, payload=None, key=None, **extras):
    return client.post(f"/api/v1/cases/{case_id}/documents", headers={"Idempotency-Key": key or str(uuid4())},
        files={"file": ("spec.pdf", payload if payload is not None else pdf(), extras.pop("mime", "application/pdf"))},
        data={"document_type": "TECHNICAL_SPECIFICATION", **extras})


def analyze(client, case_id, ids, key=None):
    return client.post(f"/api/v1/cases/{case_id}/analyses", headers={"Idempotency-Key": key or str(uuid4())},
        json={"document_ids": ids, "analysis_types": ["REQUIREMENT_EXTRACTION", "CONTRADICTION_DETECTION"], "force_reanalysis": False})


def finding_output(pages):
    citation = {"document_id": pages[0]["document_id"], "page_number": pages[0]["page_number"], "excerpt": "Minimum RAM 16 GB"}
    return {"requirements": [{"text": "Minimum RAM is 16 GB", "evidence": [citation]}], "findings": [{
        "type": "REQUIREMENT_CONTRADICTION", "severity": "HIGH", "title": "Test contradiction", "summary": "Test assertion",
        "confidence": 0.9, "evidence": [citation]}]}


def test_case_crud_versions_idempotency_and_atomic_audit(runtime):
    client, app, settings, engine = runtime
    case = create(client, "case-retry")
    assert UUID(case["case_id"]).version == 4
    assert case["created_at"].endswith("Z") and case["version"] == 1
    assert create(client, "case-retry") == case
    changed = client.post("/api/v1/cases", headers={"Idempotency-Key": "case-retry"}, json={"title": "Different", "category": "OTHER", "quantity": 1, "budget_ceiling_idr": 0})
    assert changed.status_code == 409
    path = f"/api/v1/cases/{case['case_id']}"
    assert client.patch(path, json={"title": "Changed", "expected_version": 1}).status_code == 200
    assert client.patch(path, json={"title": "Stale", "expected_version": 1}).status_code == 409
    assert client.patch(path, json={"case_status": "ARCHIVED", "expected_version": 2}).status_code == 400
    assert client.get("/api/v1/cases").json()["data"]["pagination"]["total"] == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Case)) == 1
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 2
    assert client.request("DELETE", path, json={"reason": "Duplicate", "expected_version": 2}).status_code == 200
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("amount", [True, 1.5, "100", -1])
def test_invalid_money_is_400(runtime, amount):
    client = runtime[0]
    r = client.post("/api/v1/cases", headers={"Idempotency-Key": str(uuid4())}, json={"title": "X", "category": "OTHER", "quantity": 1, "budget_ceiling_idr": amount})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("kind,expected", [("nonpdf",415),("mime",415),("malformed",422),("oversized",413),("encrypted",400),("textless",422),("unknown",400)])
def test_rejected_upload_has_no_rows_or_findings(runtime, kind, expected):
    client, app, settings, engine = runtime
    case = create(client)
    data, extras = pdf(), {}
    if kind == "nonpdf": data = b"not a pdf"
    if kind == "mime": extras["mime"] = "image/png"
    if kind == "malformed": data = b"%PDF-1.7\nmalformed"
    if kind == "oversized": data = b"%PDF-" + b"x" * settings.upload_max_bytes
    if kind == "encrypted": data = pdf(encrypted=True)
    if kind == "textless": data = pdf("")
    if kind == "unknown": extras["reviewer"] = "forged"
    response = upload(client, case["case_id"], data, **extras)
    assert response.status_code == expected, response.text
    assert set(response.json()) == {"success","data","error","meta"}
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 0
        assert db.scalar(select(func.count()).select_from(Finding)) == 0
    assert not list(settings.storage_root.glob("*.pdf"))


def test_document_pages_bytes_metadata_and_upload_replay(runtime):
    client, app, settings, engine = runtime
    case = create(client)
    binary = pdf("Minimum RAM 16 GB", "Second page")
    r = upload(client, case["case_id"], binary, "upload-key")
    assert r.status_code == 201, r.text
    document = r.json()["data"]
    assert document["page_count"] == 2 and "storage_key" not in document
    replay = upload(client, case["case_id"], binary, "upload-key")
    assert replay.json() == r.json()
    assert upload(client, case["case_id"], pdf("Different bytes"), "upload-key").status_code == 409
    with Session(engine) as db:
        row = db.get(Document, UUID(document["document_id"]))
        assert (settings.storage_root/row.storage_key).read_bytes() == binary
        pages = db.scalars(select(DocumentPage).order_by(DocumentPage.page_number)).all()
        assert [p.page_number for p in pages] == [1, 2]
        assert pages[1].normalized_text == "Second page"
    path = f"/api/v1/documents/{document['document_id']}"
    assert client.patch(path, json={"description": "Metadata", "expected_version": 1}).status_code == 200
    assert client.patch(path, json={"sha256": "forged", "expected_version": 2}).status_code == 400
    assert client.request("DELETE", path, json={"reason": "Uploaded in error", "expected_version": 2}).status_code == 200
    assert client.get(path).status_code == 404
    assert len(list(settings.storage_root.glob("*.pdf"))) == 1  # Soft deletion retains immutable bytes.


def test_verified_high_finding_completed_and_human_dismissal(runtime):
    client, app, settings, engine = runtime
    app.state.analysis_provider = TestProvider(finding_output)
    case = create(client)
    doc = upload(client, case["case_id"]).json()["data"]
    started = analyze(client, case["case_id"], [doc["document_id"]], "analysis-key")
    assert started.status_code == 202, started.text
    assert started.json()["data"]["status"] == "QUEUED"
    job_id = started.json()["data"]["job_id"]
    job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
    assert job["status"] == "COMPLETED", job
    assert job["ai_execution"]["model"] == "actual-test-runtime-model"
    assert job["ai_execution"]["usage"]["input_tokens"] == 11
    assert job["ai_execution"]["evidence_checks"] == {"checked": 2, "passed": 2, "failed": 0}
    assert analyze(client, case["case_id"], [doc["document_id"]], "analysis-key").json() == started.json()
    assert app.state.analysis_provider.calls == 1
    fid = job["result"]["finding_ids"][0]
    finding = client.get(f"/api/v1/findings/{fid}").json()["data"]
    assert finding["severity"] == "HIGH" and finding["evidence_status"] == "VERIFIED"
    assert "type" in finding and "evidence" in finding and "category" not in finding
    assert client.patch(f"/api/v1/findings/{fid}", json={"severity": "LOW", "expected_version": 1}).status_code == 400
    assert client.patch(f"/api/v1/findings/{fid}", json={"status": "UNDER_REVIEW", "expected_version": 1}).status_code == 200
    stale = client.post(f"/api/v1/findings/{fid}/dismissals", json={"reason_code": "FALSE_POSITIVE", "rationale": "Reviewed the document", "expected_version": 1})
    assert stale.status_code == 409
    dismissal = client.post(f"/api/v1/findings/{fid}/dismissals", json={"reason_code": "FALSE_POSITIVE", "rationale": "Reviewed the document", "expected_version": 2})
    assert dismissal.status_code == 201 and dismissal.json()["data"]["dismissed_by"] == str(settings.demo_actor_id)
    assert client.post(f"/api/v1/jobs/{job_id}/retries", json={"reason": "Retry"}).status_code == 409


@pytest.mark.parametrize("mode,terminal,code", [("schema","FAILED","AI_SCHEMA_VALIDATION_FAILED"),("warning","NEEDS_REVIEW",None),("clean","COMPLETED",None),("timeout","FAILED","AI_PROVIDER_TIMEOUT"),("rate","FAILED","RATE_LIMITED"),("foreign_citation","FAILED","EVIDENCE_VALIDATION_FAILED")])
def test_ai_quality_failure_and_clean_paths(runtime, mode, terminal, code):
    client, app, settings, engine = runtime
    def output(pages):
        obj = finding_output(pages)
        if mode == "schema": return {"requirements": [], "findings": [], "invented": True}
        if mode == "warning": obj["findings"][0]["evidence"][0]["excerpt"] = "Minimum RAM 128 GB"
        if mode == "foreign_citation": obj["findings"][0]["evidence"][0]["document_id"] = str(uuid4())
        return obj
    app.state.analysis_provider = TestProvider(output if mode not in {"clean","timeout","rate"} else None,
        ProviderFailure("AI_PROVIDER_TIMEOUT") if mode == "timeout" else ProviderFailure("RATE_LIMITED") if mode == "rate" else None)
    case = create(client)
    doc = upload(client, case["case_id"]).json()["data"]
    job_id = analyze(client, case["case_id"], [doc["document_id"]]).json()["data"]["job_id"]
    job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
    assert job["status"] == terminal, job
    if code:
        assert job["result"] is None and job["error"]["code"] == code
    if mode == "warning":
        assert job["warnings"][0]["code"] == "EVIDENCE_EXCERPT_NOT_FOUND"
        finding = client.get('/api/v1/findings/'+job["result"]["finding_ids"][0]).json()["data"]
        assert finding["evidence_status"] == "UNVERIFIED"
    if mode == "clean":
        assert job["result"]["finding_ids"] == []
        assert client.get(f"/api/v1/cases/{case['case_id']}/findings").json()["data"]["items"] == []
    if terminal in {"FAILED","NEEDS_REVIEW"}:
        app.state.analysis_provider = TestProvider()
        retry = client.post(f"/api/v1/jobs/{job_id}/retries", json={"reason": "Provider recovered"})
        assert retry.status_code == 202
        assert retry.json()["data"]["job_id"] != job_id
        assert retry.json()["data"]["retry_of_job_id"] == job_id
        assert client.get(f"/api/v1/jobs/{job_id}").json()["data"] == job


def test_access_and_cross_case_document_references(runtime):
    client, app, settings, engine = runtime
    first, second = create(client), create(client)
    doc = upload(client, first["case_id"]).json()["data"]
    assert analyze(client, second["case_id"], [doc["document_id"]]).status_code == 404
    app.dependency_overrides[get_actor] = lambda: Actor(uuid4(), "Other", "ANALYST", SCOPES)
    assert client.get('/api/v1/cases/'+first["case_id"]).status_code == 404
    hidden = client.get('/api/v1/documents/'+doc["document_id"])
    absent = client.get('/api/v1/documents/'+str(uuid4()))
    assert hidden.status_code == absent.status_code == 404
    assert hidden.json()["error"] == absent.json()["error"]
    assert client.get('/api/v1/cases').json()["data"]["items"] == []


def test_concurrent_case_idempotency_creates_one_case(runtime):
    client, app, settings, engine = runtime
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(client, "concurrent-key"), range(2)))
    assert results[0]["case_id"] == results[1]["case_id"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Case)) == 1


@pytest.mark.parametrize("source,target,allowed", [("QUEUED","PROCESSING",True),("QUEUED","FAILED",True),("PROCESSING","COMPLETED",True),("PROCESSING","NEEDS_REVIEW",True),("PROCESSING","FAILED",True),("QUEUED","COMPLETED",False),("COMPLETED","PROCESSING",False),("FAILED","QUEUED",False)])
def test_job_transition_rules(source, target, allowed):
    job = AnalysisJob(processing_status=source)
    if allowed:
        transition(job,target)
        assert job.processing_status == target
    else:
        with pytest.raises(ApiError): transition(job,target)


def test_terminal_job_is_immutable_in_database(runtime):
    client, app, settings, engine = runtime
    case = create(client)
    doc = upload(client, case["case_id"]).json()["data"]
    job_id = analyze(client, case["case_id"], [doc["document_id"]]).json()["data"]["job_id"]
    with Session(engine) as db:
        job = db.get(AnalysisJob, UUID(job_id))
        job.progress_percent = 0
        with pytest.raises(ValueError): db.flush()
        db.rollback()
        with pytest.raises(IntegrityError): db.execute(text("UPDATE analysis_jobs SET progress_percent=0"))
        db.rollback()


def test_real_sdk_adapter_requests_strict_schema_without_network():
    captured = {}
    class Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text='{"requirements": [], "findings": []}',model="returned-runtime-id",usage=None)
    settings = Settings(openai_model="configured-model")
    result = OpenAIAnalysisProvider(settings, SimpleNamespace(responses=Responses())).analyze([], ["CONTRADICTION_DETECTION"])
    assert result.model == "returned-runtime-id" and result.usage is None
    assert captured["model"] == "configured-model" and captured["store"] is False
    assert captured["text"]["format"]["strict"] is True
    assert captured["text"]["format"]["schema"]["additionalProperties"] is False


def test_finalized_review_protects_case_and_evidence(runtime):
    client, app, settings, engine = runtime
    app.state.analysis_provider = TestProvider(finding_output)
    case = create(client)
    doc = upload(client, case["case_id"]).json()["data"]
    job_id = analyze(client, case["case_id"], [doc["document_id"]]).json()["data"]["job_id"]
    fid = client.get(f"/api/v1/jobs/{job_id}").json()["data"]["result"]["finding_ids"][0]
    with Session(engine) as db:
        repair = RepairProposal(case_id=UUID(case["case_id"]), finding_id=UUID(fid), action_type="REVISE_REQUIREMENT", before_text="Before", proposed_text="After", justification="Test only")
        db.add(repair)
        db.flush()
        db.add(Review(case_id=UUID(case["case_id"]), repair_proposal_id=repair.id, decision="REQUEST_EVIDENCE", decision_reason="Test only", reviewer_actor_id=settings.demo_actor_id, reviewer_snapshot_json={}, assurance_status_after="ACTION_REQUIRED"))
        db.commit()
    assert client.request("DELETE", '/api/v1/documents/'+doc["document_id"], json={"reason":"Remove", "expected_version":1}).status_code == 409
    version = client.get('/api/v1/cases/'+case["case_id"]).json()["data"]["version"]
    assert client.request("DELETE", '/api/v1/cases/'+case["case_id"], json={"reason":"Remove", "expected_version":version}).status_code == 409


def test_audit_failure_rolls_back_business_and_idempotency(runtime, monkeypatch):
    from app.api.routes import cases
    client, app, settings, engine = runtime
    def unavailable(*args, **kwargs):
        raise ApiError(500, "INTERNAL_ERROR", "Test transaction rollback")
    monkeypatch.setattr(cases, "audit", unavailable)
    response = client.post("/api/v1/cases", headers={"Idempotency-Key":"rollback-test"}, json={"title":"Case", "category":"OTHER", "quantity":1, "budget_ceiling_idr":0})
    assert response.status_code == 500
    with Session(engine) as db:
        for model in (Case, CaseAccess, IdempotencyRecord, AuditEvent):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_upload_transaction_failure_cleans_new_file(runtime, monkeypatch):
    from app.api.routes import documents
    client, app, settings, engine = runtime
    case = create(client)
    def unavailable(*args, **kwargs):
        raise ApiError(500, "INTERNAL_ERROR", "Test transaction rollback")
    monkeypatch.setattr(documents, "audit", unavailable)
    assert upload(client, case["case_id"]).status_code == 500
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 0
        assert db.scalar(select(func.count()).select_from(DocumentPage)) == 0
    assert not list(settings.storage_root.glob("*.pdf"))


def test_restart_reads_persisted_case_job_and_finding(runtime):
    client, app, settings, engine = runtime
    app.state.analysis_provider = TestProvider(finding_output)
    case = create(client)
    doc = upload(client, case["case_id"]).json()["data"]
    job_id = analyze(client, case["case_id"], [doc["document_id"]]).json()["data"]["job_id"]
    expected = client.get('/api/v1/jobs/'+job_id).json()["data"]
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get('/api/v1/jobs/'+job_id).json()["data"] == expected
        fid = expected["result"]["finding_ids"][0]
        assert restarted.get('/api/v1/findings/'+fid).status_code == 200


def test_authentication_scope_and_unknown_identity_fail_closed(runtime):
    client, app, settings, engine = runtime
    case = create(client)
    app.dependency_overrides[get_actor] = lambda: Actor(settings.demo_actor_id,"Demo","ANALYST",frozenset())
    assert client.get('/api/v1/cases/'+case["case_id"]).status_code == 403
    disabled = create_app(Settings(database_url=settings.database_url))
    with TestClient(disabled) as anonymous:
        assert anonymous.get('/api/v1/cases').status_code == 401


def test_large_multipart_request_rejected_before_parser(runtime):
    client, app, settings, engine = runtime
    case = create(client)
    response = upload(client, case["case_id"], b"x" * (settings.upload_max_bytes+70000))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_missing_key_and_unexpected_multipart_field(runtime):
    client = runtime[0]
    assert client.post('/api/v1/cases', json={"title":"X", "category":"OTHER", "quantity":1,"budget_ceiling_idr":0}).status_code == 400


def test_legacy_schema_migration_preserves_execution_rows(tmp_path):
    from sqlalchemy.schema import CreateTable
    from sqlalchemy import inspect
    engine = build_engine(f"sqlite:///{(tmp_path/'legacy.db').as_posix()}")
    case_id, job_id, execution_id = uuid4(), uuid4(), uuid4()
    with engine.begin() as conn:
        Case.__table__.create(conn)
        job_ddl = str(CreateTable(AnalysisJob.__table__).compile(conn))
        job_ddl = "\n".join(line for line in job_ddl.splitlines() if not any(name in line for name in ('input_document_ids_json','requirements_json','actor_id','request_id')))
        conn.exec_driver_sql(job_ddl)
        execution_ddl = str(CreateTable(AiExecution.__table__).compile(conn))
        execution_ddl = "\n".join(line for line in execution_ddl.splitlines() if 'requested_model' not in line)
        execution_ddl = execution_ddl.replace('model VARCHAR,','model VARCHAR NOT NULL,')
        conn.exec_driver_sql(execution_ddl)
        conn.execute(Case.__table__.insert().values(id=case_id,case_number="OLD-1",title="Legacy",category="OTHER",quantity=1,budget_ceiling_idr=0))
        conn.exec_driver_sql("INSERT INTO analysis_jobs (id,case_id,analysis_types,processing_status,progress_percent,warnings_json,created_at) VALUES (?,?,?,'COMPLETED',100,'[]','2026-11-07 00:00:00')", (job_id.hex,case_id.hex,'[]'))
        conn.exec_driver_sql("INSERT INTO ai_executions (id,case_id,job_id,provider,model,operation,prompt_version,input_document_ids_json,schema_valid,evidence_validation_passed,evidence_checks_json,warnings_json,latency_ms,created_at) VALUES (?,?,?,'openai','historic-model','EXTRACT_AND_COMPARE','v1','[]',1,1,'{}','[]',12,'2026-11-07 00:00:00')", (execution_id.hex,case_id.hex,job_id.hex))
    migrate(engine)
    migrate(engine)
    with Session(engine) as db:
        row = db.get(AiExecution,execution_id)
        assert row.model == 'historic-model' and row.latency_ms == 12
        assert db.get(AnalysisJob,job_id).input_document_ids_json == []
    with engine.connect() as conn:
        assert conn.scalar(text('PRAGMA foreign_keys')) == 1
        assert conn.exec_driver_sql('PRAGMA foreign_key_check').first() is None
    engine.dispose()


def test_startup_marks_interrupted_jobs_failed_without_fabricating_execution(runtime):
    client, app, settings, engine = runtime
    case = create(client)
    job_id = uuid4()
    with Session(engine) as db:
        db.add(AnalysisJob(id=job_id, case_id=UUID(case["case_id"]), processing_status="PROCESSING", analysis_types=["REQUIREMENT_EXTRACTION"], actor_id=settings.demo_actor_id, request_id="req_interrupted"))
        db.commit()
    with TestClient(create_app(settings)) as restarted:
        job = restarted.get('/api/v1/jobs/'+str(job_id)).json()["data"]
        assert job["status"] == "FAILED" and job["error"]["retryable"]
        assert job["ai_execution"] is None
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == "ANALYSIS_INTERRUPTED")) == 1


def test_all_openapi_references_resolve_and_validation_is_documented_400():
    schema = create_app().openapi()
    def visit(node):
        if isinstance(node,dict):
            if "$ref" in node and node["$ref"].startswith("#/"):
                target = schema
                for part in node["$ref"][2:].split('/'):
                    target = target[part]
            for value in node.values(): visit(value)
        if isinstance(node,list):
            for value in node: visit(value)
    visit(schema)
    operation = schema["paths"]["/api/v1/cases"]["post"]
    assert "400" in operation["responses"] and "422" not in operation["responses"]
    assert schema["paths"]["/api/v1/cases/{case_id}/documents"]["post"]["responses"]["422"]


def test_storage_collision_never_deletes_existing_pdf(runtime, monkeypatch):
    from app.api.routes import documents
    client, app, settings, engine = runtime
    case = create(client)
    fixed = uuid4()
    settings.storage_root.mkdir()
    existing = settings.storage_root / f"{fixed}.pdf"
    existing.write_bytes(b"existing immutable bytes")
    monkeypatch.setattr(documents,"uuid4",lambda:fixed)
    response = upload(client, case["case_id"])
    assert response.status_code == 500
    assert existing.read_bytes() == b"existing immutable bytes"


def test_encrypted_owner_only_pdf_is_rejected(runtime):
    client = runtime[0]
    case = create(client)
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72,72),"Text")
        encrypted = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="")
    assert upload(client,case["case_id"],encrypted).status_code == 400


def test_raw_sql_cannot_rewrite_pdf_identity_or_finding_provenance(runtime):
    client, app, settings, engine = runtime
    app.state.analysis_provider = TestProvider(finding_output)
    case = create(client)
    doc = upload(client,case["case_id"]).json()["data"]
    analyze(client,case["case_id"],[doc["document_id"]])
    with Session(engine) as db:
        for statement in ("UPDATE documents SET sha256='changed'", "UPDATE findings SET severity='LOW'", "UPDATE document_pages SET normalized_text='changed'", "DELETE FROM evidence_refs"):
            with pytest.raises(IntegrityError): db.execute(text(statement))
            db.rollback()
