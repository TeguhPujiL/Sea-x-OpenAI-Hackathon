"""P1 golden/API tests: synthetic PDFs and explicit fake provider, never live responses."""
import json
from types import SimpleNamespace
from uuid import uuid4, UUID
import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.config import Settings
from app.core.database import build_engine
from app.core.migrations import migrate
from app.core.p1_migrations import migrate as migrate_p1
from app.main import create_app
from app.models import Document, CaseAccess, AuditEvent
from app.services.ai.provider import ProviderResult, ProviderFailure


class FixtureProvider:
    """Test-only extraction payload, grounded in actual uploaded fixture page text."""
    def __init__(self):
        self.output = None
        self.failure = None
        self.calls = 0
        self.before_return = None

    def extract(self, context):
        self.calls += 1
        if self.before_return:
            self.before_return()
        if self.failure:
            raise self.failure
        return ProviderResult(json.dumps(self.output), "synthetic-runtime-model", {"input_tokens": 10, "output_tokens": 20})


@pytest.fixture
def p1_runtime(tmp_path):
    settings = Settings(database_url="sqlite:///"+(tmp_path/"p1.db").as_posix(), storage_root=tmp_path/"pdfs",
        p1_enabled=True, demo_mode=True, demo_actor_id=uuid4(), demo_role="ANALYST",
        demo_scopes=frozenset({"case:write", "case:read", "document:write", "document:read", "document:delete", "analysis:write", "analysis:read", "finding:read", "finding:write", "finding:decide"}))
    engine = build_engine(settings.database_url)
    migrate(engine)
    migrate_p1(engine)
    migrate_p1(engine)
    app = create_app(settings)
    provider = FixtureProvider()
    app.state.p1_provider = provider
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, app=app, engine=engine, settings=settings, provider=provider)
    engine.dispose()


def new_case(r):
    response = r.client.post("/api/v1/cases", headers={"Idempotency-Key":str(uuid4())}, json={"title":"Synthetic P1 fixture", "category":"OTHER", "quantity":1, "budget_ceiling_idr":0})
    assert response.status_code == 201, response.text
    return response.json()["data"]["case_id"]


def upload(r, case_id, content, kind):
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 40), content)
        payload = pdf.tobytes()
    response = r.client.post(f"/api/v1/cases/{case_id}/documents", headers={"Idempotency-Key":str(uuid4())},
        data={"document_type":kind}, files={"file":("synthetic.pdf",payload,"application/pdf")})
    assert response.status_code == 201, response.text
    return response.json()["data"]["document_id"]


def citation(document_id, excerpt):
    return {"document_id":document_id,"page_number":1,"excerpt":excerpt}


def fixture_inputs(r, *, months=36, decision="NON_COMPLIANT", supplier="SYN-A", missing=False):
    case = new_case(r)
    required = "WARRANTY-001: Minimum warranty 36 months. Mandatory for all suppliers."
    actual = f"Supplier {supplier}. Warranty coverage: {months} months."
    recorded = f"Supplier SYN-A WARRANTY-001: {decision}."
    criterion = upload(r,case,required,"TOR")
    document = upload(r,case,actual,"WARRANTY_EVIDENCE") if not missing else None
    report = upload(r,case,recorded,"EVALUATION_REPORT")
    output = {"criteria":[{"criterion_id":"WARRANTY-001","description":"Minimum warranty 36 months", "mandatory":True,
        "applicable_supplier":None,"metric":"WARRANTY_MONTHS","operator":"MIN","required_value":36,"evidence":[citation(criterion,required)]}],
        "observations": [] if missing else [{"criterion_id":"WARRANTY-001","supplier_ref":supplier,"actual_value":months,
            "validity_from":None,"validity_until":None,"ambiguous":False,"contextual_explanation":"", "evidence":[citation(document,actual)]}],
        "decisions":[{"criterion_id":"WARRANTY-001","supplier_ref":"SYN-A","recorded_decision":decision,"confidence":0.9,"evidence":[citation(report,recorded)]}]}
    payload={"evaluation_document_id":report,"criteria_document_ids":[criterion],"supplier_document_ids":[document] if document else [],
        "check_types":["CRITERIA_CONSISTENCY","EVIDENCE_VERIFICATION","DECISION_CONSISTENCY"]}
    r.provider.output=output
    return case,payload,output


def create_evaluation(r, case, payload, key=None):
    response=r.client.post(f"/api/v1/cases/{case}/evaluation-checks",json=payload,headers={"Idempotency-Key":key or str(uuid4())})
    assert response.status_code==202,response.text
    job=r.client.get('/api/v1/jobs/'+response.json()["data"]["job_id"]).json()["data"]
    listing=r.client.get(f"/api/v1/cases/{case}/evaluation-checks").json()["data"]["items"]
    assessment=next(c for c in listing if c["job_id"]==job["job_id"])
    return job,assessment


@pytest.mark.parametrize("months,decision,result,findings",[(36,"COMPLIANT","CONSISTENT",0),(36,"NON_COMPLIANT","INCONSISTENT",1),(12,"NON_COMPLIANT","CONSISTENT",0),(12,"COMPLIANT","INCONSISTENT",1)])
def test_golden_evaluation_checks_real_uploaded_pages(p1_runtime,months,decision,result,findings):
    r=p1_runtime;case,payload,_=fixture_inputs(r,months=months,decision=decision)
    with r.app.state.session_factory() as db:
        pdfs = {doc.storage_key:(r.settings.storage_root/doc.storage_key).read_bytes() for doc in db.scalars(select(Document))}
    job,assessment=create_evaluation(r,case,payload)
    assert all((r.settings.storage_root/name).read_bytes()==payload_bytes for name,payload_bytes in pdfs.items())
    assert job["status"]=="COMPLETED"
    assert assessment["items"][0]["consistency_result"]==result
    assert len(job["result"]["finding_ids"])==findings
    assert job["ai_execution"]["model"]=="synthetic-runtime-model"
    assert job["ai_execution"]["evidence_validation_passed"] is True
    if findings:
        fid=job["result"]["finding_ids"][0]
        finding=r.client.get('/api/v1/findings/'+fid).json()["data"]
        assert finding["evidence_status"]=="VERIFIED"
        assert {e["document_id"] for e in finding["evidence"]}=={payload["evaluation_document_id"],payload["criteria_document_ids"][0],payload["supplier_document_ids"][0]}
        assert assessment["items"][0]["recommended_action"]=="REQUEST_REEVALUATION"
        # Reuse the existing versioned human workflow; no duplicate decision API.
        response=r.client.post(f'/api/v1/findings/{fid}/dismissals',json={"reason_code":"HUMAN_REVIEW","rationale":"Synthetic reviewer disagrees based on evidence", "expected_version":finding["version"]})
        assert response.status_code==201,response.text
    with r.app.state.session_factory() as db:
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.event_type=="P1_CHECK_FINISHED"))
        assert len(db.scalars(select(Document)).all())==3


@pytest.mark.parametrize("mode",["invalid_excerpt","foreign_role","wrong_supplier","ambiguous","expired","fabricated_decision","no_criteria","missing_statement"])
def test_unresolved_evidence_never_creates_findings(p1_runtime,mode):
    r=p1_runtime;case,payload,output=fixture_inputs(r)
    observation=output["observations"][0]
    if mode=="invalid_excerpt":observation["evidence"][0]["excerpt"]="This excerpt is not on the page"
    if mode=="foreign_role":observation["evidence"][0]=output["criteria"][0]["evidence"][0]
    if mode=="wrong_supplier":observation["supplier_ref"]="SYN-B"
    if mode=="ambiguous":observation["ambiguous"]=True
    if mode=="expired":observation["validity_until"]="2000-01-01"
    if mode=="fabricated_decision":output["decisions"][0]["recorded_decision"]="COMPLIANT"
    if mode=="no_criteria":output.update(criteria=[],observations=[],decisions=[])
    if mode=="missing_statement":output["decisions"]=[]
    job,assessment=create_evaluation(r,case,payload)
    assert job["status"]=="NEEDS_REVIEW"
    assert job["result"]["finding_ids"]==[]
    assert assessment["summary"]["needs_review"]>0


@pytest.mark.parametrize("mode,code",[("schema","AI_SCHEMA_VALIDATION_FAILED"),("timeout","AI_PROVIDER_TIMEOUT"),("rate","RATE_LIMITED"),("auth","AI_PROVIDER_ERROR")])
def test_failed_execution_is_preserved(p1_runtime,mode,code):
    r=p1_runtime;case,payload,_=fixture_inputs(r)
    if mode=="schema":r.provider.output={"unknown":True}
    else:r.provider.failure=ProviderFailure(code,mode!="auth")
    job,assessment=create_evaluation(r,case,payload)
    assert job["status"]=="FAILED" and job["error"]["code"]==code
    assert job["ai_execution"]["model"] is None if mode!="schema" else job["ai_execution"]["model"]=="synthetic-runtime-model"
    assert assessment["items"]==[]
    assert r.client.post(f"/api/v1/jobs/{job['job_id']}/retries",json={"reason":"Synthetic retry reason"}).status_code==409


def test_idempotency_roles_cross_case_and_unknown_fields(p1_runtime):
    r=p1_runtime;case,payload,_=fixture_inputs(r)
    key=str(uuid4());create_evaluation(r,case,payload,key)
    create_evaluation(r,case,payload,key)
    assert r.provider.calls==1
    bad={**payload,"actor_id":str(uuid4())}
    assert r.client.post(f"/api/v1/cases/{case}/evaluation-checks",json=bad,headers={"Idempotency-Key":str(uuid4())}).status_code==400
    assert r.client.post(f"/api/v1/cases/{case}/evaluation-checks",json={**payload,"supplier_document_ids":payload["supplier_document_ids"]*2},headers={"Idempotency-Key":str(uuid4())}).status_code==400
    foreign=new_case(r)
    assert r.client.post(f"/api/v1/cases/{foreign}/evaluation-checks",json=payload,headers={"Idempotency-Key":str(uuid4())}).status_code==404
    assert r.client.get(f"/api/v1/cases/{case}/evaluation-checks?invented=1").status_code==400
    with r.app.state.session_factory() as db:
        membership=db.get(CaseAccess,(UUID(case),r.settings.demo_actor_id));db.delete(membership);db.commit()
    assert r.client.get(f"/api/v1/cases/{case}/evaluation-checks").status_code==404


def test_assessment_snapshot_and_results_are_sql_immutable(p1_runtime):
    r=p1_runtime;case,payload,_=fixture_inputs(r);job,assessment=create_evaluation(r,case,payload)
    with r.engine.connect() as connection:
        for statement in ("UPDATE p1_checks SET version=2","DELETE FROM p1_checks","UPDATE p1_check_results SET result_json='{}'","DELETE FROM p1_check_results"):
            with pytest.raises(IntegrityError):connection.exec_driver_sql(statement)
            connection.rollback()
    detail=r.client.get('/api/v1/evaluation-checks/'+assessment["check_id"])
    assert detail.status_code==200 and set(detail.json())=={"success","data","error","meta"}


def test_default_openapi_is_unchanged_and_p1_is_explicit(p1_runtime):
    base=create_app(Settings()).openapi()
    extended=p1_runtime.app.openapi()
    assert not any('evaluation-checks' in p or 'supplier-readiness' in p for p in base['paths'])
    assert sum(len(methods) for p,methods in extended['paths'].items())==sum(len(methods) for p,methods in base['paths'].items())+7
    for path in base['paths']:
        assert extended['paths'][path]==base['paths'][path]


@pytest.mark.parametrize('mode',['membership_revoked','document_changed'])
def test_worker_rechecks_authorization_and_snapshot_before_persisting(p1_runtime,mode):
    r=p1_runtime;case,payload,_=fixture_inputs(r)
    def change():
        with r.app.state.session_factory() as db:
            if mode=='membership_revoked':
                db.delete(db.get(CaseAccess,(UUID(case),r.settings.demo_actor_id)))
            else:
                doc=db.get(Document,UUID(payload['supplier_document_ids'][0]));doc.description='Synthetic metadata change';doc.version+=1
            db.commit()
    r.provider.before_return=change
    response=r.client.post(f'/api/v1/cases/{case}/evaluation-checks',json=payload,headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==202
    from app.models import AnalysisJob, Finding, AiExecution
    with r.app.state.session_factory() as db:
        job=db.get(AnalysisJob,UUID(response.json()['data']['job_id']))
        assert job.processing_status.value=='FAILED'
        assert job.error_json['code']=='EVIDENCE_VALIDATION_FAILED'
        assert db.scalar(select(Finding.id)) is None
        assert db.scalar(select(AiExecution.id)) is not None


def test_p1_creation_audit_failure_rolls_back_all_records(p1_runtime):
    r=p1_runtime;case,payload,_=fixture_inputs(r)
    class RejectAudit:
        def record(self,session,command):
            raise RuntimeError('synthetic audit outage')
    r.app.state.audit_service=RejectAudit()
    response=r.client.post(f'/api/v1/cases/{case}/evaluation-checks',json=payload,headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==500
    from app.models import AnalysisJob
    from app.models.p1 import AssessmentCheck
    with r.app.state.session_factory() as db:
        assert db.scalar(select(AssessmentCheck.id)) is None
        assert db.scalar(select(AnalysisJob.id)) is None
    assert r.provider.calls==0


def test_p1_migration_rolls_back_partial_ddl(tmp_path):
    from sqlalchemy import event, inspect
    engine=build_engine('sqlite:///'+(tmp_path/'migration.db').as_posix())
    migrate(engine)
    def interrupt(connection,cursor,statement,parameters,context,executemany):
        if 'CREATE TABLE p1_check_results' in statement:
            raise RuntimeError('Synthetic migration interruption')
    event.listen(engine,'before_cursor_execute',interrupt)
    with pytest.raises(RuntimeError):migrate_p1(engine)
    event.remove(engine,'before_cursor_execute',interrupt)
    assert not any(t.startswith('p1_') for t in inspect(engine).get_table_names())
    migrate_p1(engine)
    assert 'p1_check_results' in inspect(engine).get_table_names()
    engine.dispose()
