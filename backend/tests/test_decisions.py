import json
from types import SimpleNamespace
from uuid import UUID, uuid4
from dataclasses import FrozenInstanceError

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_p0 import runtime, create, upload, analyze, pdf, TestProvider
from app.api.response import ApiError
from app.core.integration import CoreAuditAdapter, StoredSimulationLookup
from app.core.security import Actor, get_actor
from app.models import Case, Document, Finding, AiExecution, Simulation, Challenge, RepairProposal, Review, SubmittedRepairSnapshot, GenerationLease, IdempotencyRecord, AuditEvent
from app.models.base import now
from app.services.ai.provider import ProviderResult, ProviderFailure
from app.services.ai.decisions import OpenAIDecisionProvider, DecisionFailure, CHALLENGE_PROMPT_VERSION, REPAIR_PROMPT_VERSION

DECISION_SCOPES = {"challenge:read", "challenge:write", "challenge:delete", "repair:read", "repair:write", "repair:delete"}


class DecisionStub:
    def __init__(self, mode=None):
        self.mode = mode
        self.calls = []
    def generate(self, kind, context):
        self.calls.append(kind)
        if self.mode == "timeout": raise DecisionFailure("AI_PROVIDER_TIMEOUT")
        if self.mode == "rate": raise DecisionFailure("RATE_LIMITED", True, "7")
        refs = list(context["evidence"])
        before = next((r["excerpt"] for r in refs if "32" in r["excerpt"]), refs[0]["excerpt"])
        if kind == "challenge":
            output = {"question":"What documented operational need supports the change from 16 GB to 32 GB?",
                "risk_rationale":"A more restrictive requirement may reduce competition without documented operational need.", "evidence": refs}
        else:
            proposed = "Minimum RAM 16 GB, unless documented workload analysis supports a higher threshold."
            if context["action_type"] == "MAINTAIN_WITH_JUSTIFICATION": proposed = before
            if context["action_type"] == "REQUEST_MORE_EVIDENCE": proposed = "Request technical justification before revising the requirement."
            output = {"before_text":before, "proposed_text":proposed,
                "justification":"Align the requirement with documented operational needs and require supporting justification.", "evidence":refs}
        if self.mode == "schema": output["invented"] = True
        if self.mode == "citation": output["evidence"] = [{"document_id":str(uuid4()), "page_number":1, "excerpt":"Invented"}]
        if self.mode == "allegation": output["risk_rationale" if kind == "challenge" else "justification"] = "This proves corruption and fraud."
        if self.mode == "numbers": output["question" if kind == "challenge" else "proposed_text"] = "What justifies RAM 999 GB?"
        if self.mode == "before": output["before_text"] = "Minimum RAM 999 GB"
        if self.mode == "metrics": output["justification"] = "The price delta is IDR 999999999."
        if self.mode == "malformed": return ProviderResult("not-json", "actual-decision-model", None)
        return ProviderResult(json.dumps(output), "actual-decision-model", {"input_tokens":37, "output_tokens":19})


@pytest.fixture
def decisions(runtime):
    client, app, settings, engine = runtime
    settings.demo_scopes = settings.demo_scopes | DECISION_SCOPES
    def comparison(pages):
        refs = [{"document_id":p["document_id"], "page_number":p["page_number"], "excerpt":p["text"]} for p in pages]
        return {"requirements":[], "findings":[{"type":"REQUIREMENT_CONTRADICTION", "severity":"HIGH", "title":"RAM inconsistency", "summary":"The supplied requirements differ.", "confidence":.9, "evidence":refs}]}
    app.state.analysis_provider = TestProvider(comparison)
    case = create(client)
    docs = [upload(client,case["case_id"],pdf(value)).json()["data"] for value in ("Minimum RAM 32 GB","Minimum RAM 16 GB")]
    job_id = analyze(client,case["case_id"],[d["document_id"] for d in docs]).json()["data"]["job_id"]
    job = client.get('/api/v1/jobs/'+job_id).json()["data"]
    finding_id = job["result"]["finding_ids"][0]
    with Session(engine) as db:
        simulation = Simulation(case_id=UUID(case["case_id"]), finding_id=UUID(finding_id),
            engine_version="supplier-eligibility-v1", supplier_data_version="synthetic-suppliers-v1",
            input_snapshot_json={"quantity":50,"baseline":{"minimum_ram_gb":32},"alternative":{"minimum_ram_gb":16},"suppliers":[]},
            result_json={"baseline":{"eligible_supplier_count":1,"lowest_total_offer_idr":825000000},"alternative":{"eligible_supplier_count":3,"lowest_total_offer_idr":660000000},"delta":{"eligible_supplier_count":2,"lowest_total_offer_idr":-165000000}},
            interpretation="Test-only immutable fixture; no engine is implemented by this test.")
        db.add(simulation); db.commit()
        simulation_id = str(simulation.id)
    app.state.decision_provider = DecisionStub()
    return client, app, settings, engine, case["case_id"], finding_id, simulation_id, docs


def challenge(client, case_id, finding_id, **changes):
    return client.post(f'/api/v1/cases/{case_id}/challenges',json={"finding_id":finding_id,"generation_mode":"AI_ASSISTED","requested_evidence":["TECHNICAL_JUSTIFICATION","MARKET_COMPARISON"],**changes})


def repair(client, finding_id, simulation_id, key=None, **changes):
    return client.post(f'/api/v1/findings/{finding_id}/repair-proposals',headers={"Idempotency-Key":key or str(uuid4())},json={"action_type":"REVISE_REQUIREMENT","simulation_id":simulation_id,"generation_mode":"AI_ASSISTED",**changes})


def test_challenge_201_grounded_draft_provenance_and_crud(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    response=challenge(client,case_id,fid)
    assert response.status_code==201,response.text
    data=response.json()["data"]
    assert data["status"]=="DRAFT" and not data["human_edits"] and data["version"]==1
    assert data["requested_evidence"]==["TECHNICAL_JUSTIFICATION","MARKET_COMPARISON"]
    assert "16 GB" in data["question"] and "32 GB" in data["question"]
    assert data["created_at"].endswith("Z")
    path='/api/v1/challenges/'+data["challenge_id"]
    assert client.get(path).json()["data"]==data
    assert client.get(f'/api/v1/cases/{case_id}/challenges').json()["data"]["pagination"]["total"]==1
    with Session(engine) as db:
        execution=db.get(AiExecution,UUID(data["ai_execution_id"]))
        assert execution.model=="actual-decision-model" and execution.prompt_version==CHALLENGE_PROMPT_VERSION
        assert execution.evidence_checks_json=={"checked":2,"passed":2,"failed":0}
        assert execution.schema_valid and execution.evidence_validation_passed
    changed=client.patch(path,json={"question":"What evidence supports minimum RAM 32 GB rather than 16 GB?","status":"READY","expected_version":1})
    assert changed.status_code==200 and changed.json()["data"]["human_edits"]
    assert client.patch(path,json={"status":"CLOSED","expected_version":1}).status_code==409
    assert client.request("DELETE",path,json={"reason":"Duplicate","expected_version":2}).status_code==409
    assert client.patch(path,json={"status":"CLOSED","expected_version":2}).status_code==200
    assert client.patch(path,json={"question":"Why?","expected_version":3}).status_code==409


def test_challenge_eligible_draft_delete_and_reference_hook(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    data=challenge(client,case_id,fid).json()["data"]
    path='/api/v1/challenges/'+data["challenge_id"]
    original=app.state.reference_lookup
    app.state.reference_lookup=SimpleNamespace(challenge_in_use=lambda db,row:True)
    assert client.request("DELETE",path,json={"reason":"Duplicate","expected_version":1}).status_code==409
    app.state.reference_lookup=original
    assert client.request("DELETE",path,json={"reason":"Duplicate","expected_version":1}).status_code==200
    assert client.get(path).status_code==404
    assert client.get(f'/api/v1/cases/{case_id}/challenges').json()["data"]["items"]==[]


@pytest.mark.parametrize("action",["REVISE_REQUIREMENT","MAINTAIN_WITH_JUSTIFICATION","REQUEST_MORE_EVIDENCE"])
def test_repair_all_actions_and_server_owned_numeric_interpretation(decisions,action):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    response=repair(client,fid,sid,action_type=action)
    assert response.status_code==201,response.text
    data=response.json()["data"]
    assert data["status"]=="DRAFT" and data["action_type"]==action and data["before_text"]=="Minimum RAM 32 GB"
    assert data["simulation_id"]==sid and not data["human_edits"]
    assert "lowest_total_offer_idr=-165000000" in data["justification"]
    assert "not evidence of actual savings" in data["justification"]
    assert client.get('/api/v1/repair-proposals/'+data["repair_proposal_id"]).json()["data"]==data
    assert client.get(f'/api/v1/findings/{fid}/repair-proposals').json()["data"]["pagination"]["total"]==1
    with Session(engine) as db:
        execution=db.get(AiExecution,UUID(data["ai_execution_id"]))
        assert execution.prompt_version==REPAIR_PROMPT_VERSION and execution.usage_json["input_tokens"]==37


def test_repair_edit_submit_snapshot_freeze_and_review_preconditions(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    data=repair(client,fid,sid).json()["data"]
    path='/api/v1/repair-proposals/'+data["repair_proposal_id"]
    assert client.patch(path,json={"status":"APPROVED","expected_version":1}).status_code==409
    edit=client.patch(path,json={"proposed_text":"Minimum RAM 16 GB subject to documented workload justification.","expected_version":1})
    assert edit.status_code==200 and edit.json()["data"]["human_edits"]
    assert client.patch(path,json={"status":"SUBMITTED","expected_version":1}).status_code==409
    submitted=client.patch(path,json={"status":"SUBMITTED","expected_version":2})
    assert submitted.status_code==200,submitted.text
    assert submitted.json()["data"]["status"]=="SUBMITTED" and submitted.json()["data"]["version"]==3
    assert client.patch(path,json={"proposed_text":"Modified","expected_version":3}).status_code==409
    assert client.request("DELETE",path,json={"reason":"Remove","expected_version":3}).status_code==409
    case=client.get('/api/v1/cases/'+case_id).json()["data"]
    assert case["case_status"]=="UNDER_REVIEW" and case["assurance_status"]=="READY_FOR_REVIEW"
    with Session(engine) as db:
        snapshot=db.get(SubmittedRepairSnapshot,(UUID(data["repair_proposal_id"]),3))
        assert snapshot.snapshot_json==submitted.json()["data"]
        actor=Actor(settings.demo_actor_id,"Demo","REVIEWER",frozenset())
        candidate=app.state.review_preconditions.validate(db,actor,UUID(case_id),UUID(data["repair_proposal_id"]),case["version"])
        assert candidate.submitted_version==3 and candidate.simulation.simulation_id==UUID(sid)
        assert not db.dirty
        with pytest.raises(ApiError) as exc: app.state.review_preconditions.validate(db,actor,UUID(case_id),UUID(data["repair_proposal_id"]),case["version"]-1)
        assert exc.value.code=="VERSION_CONFLICT"
        with pytest.raises(IntegrityError): db.execute(text("UPDATE repair_proposals SET proposed_text='changed'"))
        db.rollback()
        with pytest.raises(IntegrityError): db.execute(text("DELETE FROM submitted_repair_snapshots"))
        db.rollback()


def test_repair_draft_delete_and_review_reference_restriction(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    data=repair(client,fid,sid).json()["data"]
    path='/api/v1/repair-proposals/'+data["repair_proposal_id"]
    with Session(engine) as db:
        db.add(Review(case_id=UUID(case_id),repair_proposal_id=UUID(data["repair_proposal_id"]),decision="REQUEST_EVIDENCE",decision_reason="Test-only reference guard",reviewer_actor_id=settings.demo_actor_id,reviewer_snapshot_json={},assurance_status_after="ACTION_REQUIRED"));db.commit()
    assert client.request("DELETE",path,json={"reason":"Duplicate","expected_version":1}).status_code==409
    other=repair(client,fid,sid).json()["data"]
    other_path='/api/v1/repair-proposals/'+other["repair_proposal_id"]
    assert client.request("DELETE",other_path,json={"reason":"Duplicate","expected_version":1}).status_code==200
    assert client.get(other_path).status_code==404


def test_repair_idempotency_and_field_accuracy(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    original=repair(client,fid,sid,"repair-transport")
    replay=repair(client,fid,sid,"repair-transport")
    assert original.status_code==replay.status_code==201 and original.json()==replay.json()
    assert app.state.decision_provider.calls==["repair"]
    assert repair(client,fid,sid,"repair-transport",action_type="REQUEST_MORE_EVIDENCE").status_code==409
    for field in ({"action_type":"UNSUPPORTED"},{"repair_action":"REVISE_REQUIREMENT"},{"generation_mode":"MANUAL"},{"reviewer_actor_id":str(uuid4())}):
        assert repair(client,fid,sid,**field).status_code==400
    assert client.post(f'/api/v1/findings/{fid}/repair-proposals',json={"action_type":"REVISE_REQUIREMENT","simulation_id":sid,"generation_mode":"AI_ASSISTED"}).status_code==400
    assert challenge(client,case_id,fid,unexpected=True).status_code==400


@pytest.mark.parametrize("kind",["challenge","repair"])
@pytest.mark.parametrize("mode,status,code",[("timeout",504,"AI_PROVIDER_TIMEOUT"),("rate",429,"RATE_LIMITED"),("schema",502,"AI_PROVIDER_ERROR"),("malformed",502,"AI_PROVIDER_ERROR"),("citation",422,"EVIDENCE_VALIDATION_FAILED"),("allegation",422,"EVIDENCE_VALIDATION_FAILED"),("numbers",422,"EVIDENCE_VALIDATION_FAILED")])
def test_generation_failures_preserve_actual_provenance_without_draft(decisions,kind,mode,status,code):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    app.state.decision_provider=DecisionStub(mode)
    with Session(engine) as db: before=db.scalar(select(func.count()).select_from(AiExecution))
    response=challenge(client,case_id,fid) if kind=="challenge" else repair(client,fid,sid,"failed-transport")
    assert response.status_code==status,response.text
    assert response.json()["error"]["code"]==code
    if mode=="rate": assert response.headers["Retry-After"]=="7"
    if kind=="repair":
        replay=repair(client,fid,sid,"failed-transport")
        assert replay.status_code==response.status_code and replay.json()==response.json()
        if mode=="rate": assert replay.headers["Retry-After"]=="7"
    assert app.state.decision_provider.calls==[kind]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AiExecution))==before+1
        execution=db.scalar(select(AiExecution).where(AiExecution.job_id.is_(None)))
        assert not execution.evidence_validation_passed
        assert execution.model is None if mode in {"timeout","rate"} else execution.model=="actual-decision-model"
        assert db.scalar(select(func.count()).select_from(Challenge))==0
        assert db.scalar(select(func.count()).select_from(RepairProposal))==0
        assert db.scalar(select(func.count()).select_from(GenerationLease))==0


@pytest.mark.parametrize("mode",["before","metrics"])
def test_invented_before_text_or_ai_numeric_claim_is_rejected(decisions,mode):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    app.state.decision_provider=DecisionStub(mode)
    assert repair(client,fid,sid).status_code==422


def test_cross_case_finding_and_simulation_are_rejected_before_generation(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    other=create(client)
    assert challenge(client,other["case_id"],fid).status_code==404
    with Session(engine) as db:
        original=db.get(Simulation,UUID(sid))
        wrong=Simulation(case_id=UUID(other["case_id"]),finding_id=UUID(fid),engine_version=original.engine_version,supplier_data_version=original.supplier_data_version,input_snapshot_json=original.input_snapshot_json,result_json=original.result_json,interpretation="Cross-case test input")
        db.add(wrong);db.commit();wrong_id=str(wrong.id)
    assert repair(client,fid,wrong_id).status_code==404
    assert app.state.decision_provider.calls==[]


def test_official_document_bytes_remain_unchanged(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    before={p.name:p.read_bytes() for p in settings.storage_root.glob('*.pdf')}
    challenge(client,case_id,fid)
    draft=repair(client,fid,sid).json()["data"]
    assert client.patch('/api/v1/repair-proposals/'+draft["repair_proposal_id"],json={"status":"SUBMITTED","expected_version":1}).status_code==200
    assert {p.name:p.read_bytes() for p in settings.storage_root.glob('*.pdf')}==before
    with Session(engine) as db:
        assert all(d.version==1 for d in db.scalars(select(Document)))


def test_clean_case_creates_no_finding_or_proposal(runtime):
    client,app,settings,engine=runtime
    settings.demo_scopes=settings.demo_scopes|DECISION_SCOPES
    app.state.decision_provider=DecisionStub()
    case=create(client)
    doc=upload(client,case["case_id"]).json()["data"]
    analyze(client,case["case_id"],[doc["document_id"]])
    assert challenge(client,case["case_id"],str(uuid4())).status_code==404
    assert repair(client,str(uuid4()),str(uuid4())).status_code==404
    assert app.state.decision_provider.calls==[]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Finding))==0
        assert db.scalar(select(func.count()).select_from(RepairProposal))==0


def test_audit_is_delegated_and_participates_in_same_transaction(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    events=[]
    class Delegate:
        def record(self,session,command):
            assert session.in_transaction()
            events.append(command)
            CoreAuditAdapter().record(session,command)
    app.state.audit_service=Delegate()
    draft=challenge(client,case_id,fid).json()["data"]
    assert events[-1].resource_id==UUID(draft["challenge_id"]) and events[-1].event_type=="CHALLENGE_CREATED"
    class Unavailable:
        def record(self,session,command): raise ApiError(500,"INTERNAL_ERROR","Audit unavailable")
    app.state.audit_service=Unavailable()
    with Session(engine) as db: before=db.scalar(select(func.count()).select_from(AiExecution))
    assert challenge(client,case_id,fid).status_code==500
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Challenge))==1
        assert db.scalar(select(func.count()).select_from(AiExecution))==before


def test_typed_simulation_lookup_returns_immutable_independent_snapshot(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    with Session(engine) as db:
        actor=Actor(settings.demo_actor_id,"Demo","ANALYST",frozenset())
        snapshot=app.state.simulation_lookup.get(db,actor,UUID(case_id),UUID(fid),UUID(sid))
        with pytest.raises(FrozenInstanceError): snapshot.engine_version="mutated"
        context=snapshot.as_context();context["result"]["delta"]["lowest_total_offer_idr"]=999
        assert snapshot.as_context()["result"]["delta"]["lowest_total_offer_idr"]==-165000000
        assert not db.dirty


def test_real_decision_sdk_adapter_uses_strict_schema_and_actual_model():
    calls=[]
    class Responses:
        def create(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text='{}',model="returned-runtime-model",usage=None,status="completed")
    from app.core.config import Settings
    provider=OpenAIDecisionProvider(Settings(openai_model="configured-model"),SimpleNamespace(responses=Responses()))
    for kind in ("challenge","repair"):
        result=provider.generate(kind,{"evidence":[]})
        assert result.model=="returned-runtime-model" and result.usage is None
        assert calls[-1]["text"]["format"]["strict"] is True
        assert calls[-1]["text"]["format"]["schema"]["additionalProperties"] is False
        assert calls[-1]["text"]["format"]["schema"]["$defs"]["Citation"]["properties"]["document_id"]["format"] == "uuid"
        assert calls[-1]["store"] is False


def test_concurrent_repair_key_does_not_execute_provider_twice(decisions):
    from threading import Event
    from concurrent.futures import ThreadPoolExecutor
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    started,release=Event(),Event()
    class Slow(DecisionStub):
        def generate(self,kind,context):
            started.set()
            assert release.wait(15)
            return super().generate(kind,context)
    app.state.decision_provider=Slow()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(repair,client,fid,sid,"inflight-key")
        try:
            assert started.wait(10)
            pending=repair(client,fid,sid,"inflight-key")
            assert pending.status_code==409
            assert pending.json()["error"]["code"]=="INVALID_STATE_TRANSITION"
        finally:
            release.set()
        assert first.result(timeout=15).status_code==201
    assert app.state.decision_provider.calls==["repair"]
    assert repair(client,fid,sid,"inflight-key").status_code==201
    assert app.state.decision_provider.calls==["repair"]


def test_source_changes_during_generation_do_not_commit_stale_draft(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    case=client.get('/api/v1/cases/'+case_id).json()["data"]
    class Changing(DecisionStub):
        def generate(self,kind,context):
            response=client.patch('/api/v1/cases/'+case_id,json={"title":"Changed while generating","expected_version":case["version"]})
            assert response.status_code==200
            return super().generate(kind,context)
    app.state.decision_provider=Changing()
    response=repair(client,fid,sid)
    assert response.status_code==409,response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(RepairProposal))==0
        execution=db.scalar(select(AiExecution).where(AiExecution.job_id.is_(None)))
        assert execution.schema_valid and not execution.evidence_validation_passed


def test_expired_generation_lease_can_be_reclaimed(decisions):
    from datetime import timedelta
    from app.core.transactions import fingerprint
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    route=f'/api/v1/findings/{fid}/repair-proposals'
    payload={"action_type":"REVISE_REQUIREMENT","simulation_id":sid,"generation_mode":"AI_ASSISTED"}
    with Session(engine) as db:
        db.add(GenerationLease(actor_id=settings.demo_actor_id,route=route,key="expired",request_hash=fingerprint(payload),token=uuid4(),expires_at=now()-timedelta(seconds=1)));db.commit()
    assert repair(client,fid,sid,"expired").status_code==201
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(GenerationLease))==0


def test_unverified_finding_cannot_generate_challenge_or_repair(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    with Session(engine) as db:
        original=db.get(Finding,UUID(fid))
        row=Finding(case_id=original.case_id,analysis_job_id=original.analysis_job_id,ai_execution_id=original.ai_execution_id,type=original.type,severity=original.severity,title="Unverified test finding",summary="Unverified test source",confidence=.5,evidence_status="UNVERIFIED")
        db.add(row);db.commit();unverified=str(row.id)
    assert challenge(client,case_id,unverified).status_code==422
    assert repair(client,unverified,sid).status_code==422
    assert app.state.decision_provider.calls==[]


def test_numeric_interpretation_uses_stored_results_without_recalculation(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    with Session(engine) as db:
        original=db.get(Simulation,UUID(sid))
        row=Simulation(case_id=original.case_id,finding_id=original.finding_id,engine_version="external-engine-test",supplier_data_version="external-data-test",input_snapshot_json=original.input_snapshot_json,
            result_json={"baseline":{"eligible_supplier_count":17,"lowest_total_offer_idr":123},"alternative":{"eligible_supplier_count":23,"lowest_total_offer_idr":100},"delta":{"eligible_supplier_count":6,"lowest_total_offer_idr":-23}},interpretation="Externally computed test result")
        db.add(row);db.commit();other=str(row.id)
    response=repair(client,fid,other)
    assert response.status_code==201,response.text
    assert "eligible_supplier_count=17" in response.json()["data"]["justification"]
    assert "lowest_total_offer_idr=-23" in response.json()["data"]["justification"]
    assert "825000000" not in response.json()["data"]["justification"]


def test_factory_accepts_typed_integrations_and_binds_review_lookup(decisions):
    from app.main import create_app
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    lookup=StoredSimulationLookup()
    delegate=CoreAuditAdapter()
    composed=create_app(settings,simulation_lookup=lookup,audit_service=delegate)
    assert composed.state.audit_service is delegate
    assert composed.state.simulation_lookup is lookup
    assert composed.state.review_preconditions.simulations is lookup


def test_repair_api_cannot_change_frozen_provenance_fields(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    data=repair(client,fid,sid).json()["data"]
    path='/api/v1/repair-proposals/'+data["repair_proposal_id"]
    for field in ("before_text","justification","simulation_id","action_type","ai_execution_id"):
        assert client.patch(path,json={field:"forged","expected_version":1}).status_code==400
    with Session(engine) as db:
        with pytest.raises(IntegrityError): db.execute(text("UPDATE repair_proposals SET before_text='forged'"))
        db.rollback()


def test_required_idempotency_header_is_accurate_in_openapi():
    from app.main import create_app
    schema=create_app().openapi()
    for path in ('/api/v1/cases','/api/v1/cases/{case_id}/documents','/api/v1/cases/{case_id}/analyses','/api/v1/findings/{finding_id}/repair-proposals'):
        operation=schema["paths"][path]["post"]
        header=next(p for p in operation["parameters"] if p["name"]=="Idempotency-Key")
        assert header["required"] is True
    assert not any(p["name"]=="Idempotency-Key" for p in schema["paths"]['/api/v1/cases/{case_id}/challenges']["post"].get("parameters",[]))


def test_shared_phase_a_and_b_mutations_use_same_delegated_audit_port(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    commands=[]
    class Delegate:
        def record(self,session,command):
            commands.append(command)
            CoreAuditAdapter().record(session,command)
    app.state.audit_service=Delegate()
    case=client.get('/api/v1/cases/'+case_id).json()["data"]
    assert client.patch('/api/v1/cases/'+case_id,json={"title":"Through delegated audit","expected_version":case["version"]}).status_code==200
    assert commands[-1].event_type=="CASE_UPDATED"
    assert challenge(client,case_id,fid).status_code==201
    assert commands[-1].event_type=="CHALLENGE_CREATED"
    assert repair(client,fid,sid).status_code==201
    assert commands[-1].event_type=="REPAIR_CREATED"


def test_review_owned_disposition_can_change_without_mutating_submitted_snapshot(decisions):
    client,app,settings,engine,case_id,fid,sid,docs=decisions
    draft=repair(client,fid,sid).json()["data"]
    submitted=client.patch('/api/v1/repair-proposals/'+draft["repair_proposal_id"],json={"status":"SUBMITTED","expected_version":1}).json()["data"]
    with Session(engine) as db:
        proposal=db.get(RepairProposal,UUID(draft["repair_proposal_id"]))
        snapshot=db.get(SubmittedRepairSnapshot,(proposal.id,2))
        original_snapshot=dict(snapshot.snapshot_json)
        proposal.status="APPROVED"  # Test the integration write boundary, not an approval service.
        proposal.version+=1
        db.commit()
        assert db.get(SubmittedRepairSnapshot,(proposal.id,2)).snapshot_json==original_snapshot==submitted
        assert proposal.proposed_text==submitted["proposed_text"]


def test_migration_v1_preserves_existing_idempotency_bodies_and_adds_headers(tmp_path):
    from sqlalchemy.schema import CreateTable
    from app.core.database import build_engine
    from app.core.migrations import migrate
    engine=build_engine(f"sqlite:///{(tmp_path/'v1.db').as_posix()}")
    record_id,actor_id=uuid4(),uuid4()
    body={"success":True,"data":{},"error":None,"meta":{"request_id":"req_historic","timestamp":"2026-11-07T03:20:08Z","api_version":"v1"}}
    with engine.begin() as connection:
        ddl=str(CreateTable(IdempotencyRecord.__table__).compile(connection))
        ddl="\n".join(line for line in ddl.splitlines() if 'response_headers' not in line)
        connection.exec_driver_sql(ddl)
        connection.exec_driver_sql("INSERT INTO idempotency_records (id,actor_id,method,route,key,request_hash,response_status,response_body,created_at) VALUES (?,?,'POST','/migration-test','historic',?,201,?,'2026-11-07 00:00:00')",(record_id.hex,actor_id.hex,'f'*64,json.dumps(body)))
        connection.exec_driver_sql('PRAGMA user_version=1')
    migrate(engine)
    migrate(engine)
    with Session(engine) as db:
        record=db.get(IdempotencyRecord,record_id)
        assert record.response_body==body and record.response_headers=={}
        assert db.scalar(text('PRAGMA user_version'))==2
    engine.dispose()
