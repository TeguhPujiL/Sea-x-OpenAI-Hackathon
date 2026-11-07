"""Readiness golden scenarios and immutable supplementary-document revalidation."""
import pytest
from uuid import uuid4, UUID
from sqlalchemy import select
from app.models import Document, AiExecution, AuditEvent
from test_evaluation_integrity import p1_runtime, fixture_inputs, upload, citation


def readiness_inputs(r, **kwargs):
    case,evaluation,output=fixture_inputs(r,**kwargs)
    output['decisions']=[]
    request={'supplier_ref':'SYN-A','requirement_document_ids':evaluation['criteria_document_ids'],
        'supplier_document_ids':evaluation['supplier_document_ids'],'include_remediation_guidance':True}
    return case,request,output


def create_readiness(r,case,payload):
    response=r.client.post(f'/api/v1/cases/{case}/supplier-readiness-checks',json=payload,headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==202,response.text
    job=r.client.get('/api/v1/jobs/'+response.json()['data']['job_id']).json()['data']
    items=r.client.get(f'/api/v1/cases/{case}/supplier-readiness-checks').json()['data']['items']
    assessment=next(a for a in items if a['job_id']==job['job_id'])
    return job,assessment


@pytest.mark.parametrize('months,status',[(36,'VERIFIED'),(12,'NON_COMPLIANT'),(48,'VERIFIED')])
def test_warranty_substance_not_presence(p1_runtime,months,status):
    r=p1_runtime;case,payload,_=readiness_inputs(r,months=months)
    job,result=create_readiness(r,case,payload)
    assert job['status']=='COMPLETED'
    item=result['requirements'][0]
    assert item['readiness_status']==status
    assert item['actual_value']==months
    assert all(e['verification_status']=='VERIFIED' for e in item['evidence'])
    assert job['result']['finding_ids']==[]


def test_missing_evidence_is_not_a_clean_verified_result(p1_runtime):
    r=p1_runtime;case,payload,_=readiness_inputs(r,missing=True)
    job,result=create_readiness(r,case,payload)
    assert result['requirements'][0]['readiness_status']=='MISSING'
    assert result['summary']['missing']==1
    assert result['requirements'][0]['requires_human_review']
    assert job['result']['finding_ids']==[]


def test_selected_conflicting_document_cannot_be_omitted_by_model(p1_runtime):
    r=p1_runtime;case,payload,_=readiness_inputs(r,months=36)
    contradictory=upload(r,case,'Supplier SYN-A. Warranty coverage: 12 months.','WARRANTY_EVIDENCE')
    payload['supplier_document_ids'].append(contradictory)
    job,result=create_readiness(r,case,payload)
    assert job['status']=='NEEDS_REVIEW'
    assert result['requirements'][0]['readiness_status']=='NEEDS_REVIEW'
    assert 'conflicting' in result['requirements'][0]['explanation']


@pytest.mark.parametrize('mode',['ambiguous','wrong_supplier','conflicting_values','expired','invalid_date','invalid_citation','unknown_applicability'])
def test_readiness_uncertainty_needs_human_review(p1_runtime,mode):
    r=p1_runtime;case,payload,output=readiness_inputs(r)
    observation=output['observations'][0]
    if mode=='ambiguous':observation['ambiguous']=True
    if mode=='wrong_supplier':observation['supplier_ref']='SYN-B'
    if mode=='conflicting_values':observation['actual_value']=12
    if mode=='expired':observation['validity_until']='2000-01-01'
    if mode=='invalid_date':observation['validity_until']='2026-99-01'
    if mode=='invalid_citation':observation['evidence'][0]['excerpt']='Not in this PDF'
    if mode=='unknown_applicability':output['criteria'][0]['applicable_supplier']='SYN-B'
    job,result=create_readiness(r,case,payload)
    if mode=='invalid_date':
        assert job['status']=='FAILED' and job['error']['code']=='AI_SCHEMA_VALIDATION_FAILED'
    else:
        assert job['status']=='NEEDS_REVIEW'
        assert result['requirements'][0]['readiness_status']=='NEEDS_REVIEW'
    assert job['result'] is None or job['result']['finding_ids']==[]


def test_revalidation_new_snapshot_diff_provenance_and_version_conflict(p1_runtime):
    r=p1_runtime;case,payload,output=readiness_inputs(r,months=12)
    old_job,old=create_readiness(r,case,payload)
    text='Supplier SYN-A. Supplementary warranty coverage: 36 months.'
    new_doc=upload(r,case,text,'WARRANTY_EVIDENCE')
    output['observations'][0].update(actual_value=36,evidence=[citation(new_doc,text)])
    new_payload={**payload,'supplier_document_ids':[new_doc],'expected_version':old['version']}
    url=f"/api/v1/supplier-readiness-checks/{old['check_id']}/revalidations"
    response=r.client.post(url,json={**new_payload,'expected_version':99},headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==409
    response=r.client.post(url,json=new_payload,headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==202,response.text
    results=r.client.get(f'/api/v1/cases/{case}/supplier-readiness-checks').json()['data']['items']
    new=next(a for a in results if a['version']==2)
    assert new['previous_check_id']==old['check_id']
    assert new['requirements'][0]['readiness_status']=='VERIFIED'
    assert new['changes']==[{'requirement_id':'WARRANTY-001','before_status':'NON_COMPLIANT','after_status':'VERIFIED'}]
    preserved=r.client.get('/api/v1/supplier-readiness-checks/'+old['check_id']).json()['data']
    assert preserved==old
    with r.app.state.session_factory() as db:
        assert db.get(Document,UUID(payload['supplier_document_ids'][0])).sha256!=db.get(Document,UUID(new_doc)).sha256
        assert len(db.scalars(select(AiExecution)).all())==2
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.event_type=='P1_REVALIDATION_REQUESTED'))


def test_threshold_units_and_iso_expiry_are_independent():
    from app.services.evidence.supplier_readiness import numeric_value
    assert numeric_value('Warranty: three years','WARRANTY_MONTHS')==36
    assert numeric_value('A three-year warranty','WARRANTY_MONTHS')==36
    assert numeric_value('Minimum 36-month warranty','WARRANTY_MONTHS')==36
    assert numeric_value('Warranty: 3 years','WARRANTY_MONTHS')==36
    assert numeric_value('Installed Memory: 16GB DDR5','RAM_GB')==16
    assert numeric_value('12 months or 36 months','WARRANTY_MONTHS') is None
    assert numeric_value('Delivery within 15 days','DELIVERY_DAYS')==15
    assert numeric_value('50 units','QUANTITY')==50
    assert numeric_value('-48 months','WARRANTY_MONTHS') is None
    assert numeric_value('3.6 months','WARRANTY_MONTHS') is None


@pytest.mark.parametrize('content,claimed,expected',[
    ('Supplier SYN-B. Warranty: 36 months.',None,'NEEDS_REVIEW'),
    ('Supplier SYN-A. Warranty: 3 years.',None,'VERIFIED'),
    ('Supplier SYN-A. No warranty: 36 months.',None,'NEEDS_REVIEW'),
    ('Supplier SYN-A. Warranty: 36 months. Expires: 2000-01-01.',None,'NEEDS_REVIEW'),
    ('Supplier SYN-A. Warranty: 36 months. Expires: 2000-01-01.','2000-01-01','NEEDS_REVIEW'),
    ('Supplier SYN-A. Warranty: 36 months. Expires: 2099-01-01.','2099-01-01','VERIFIED'),
    ('Supplier SYN-A. Warranty: 36 months. Expires: unknown.',None,'NEEDS_REVIEW'),
])
def test_actual_document_identity_units_negation_and_dates(p1_runtime,content,claimed,expected):
    r=p1_runtime;case,payload,output=readiness_inputs(r)
    doc=upload(r,case,content,'WARRANTY_EVIDENCE')
    payload['supplier_document_ids']=[doc]
    output['observations'][0].update(evidence=[citation(doc,content)],validity_until=claimed)
    job,result=create_readiness(r,case,payload)
    assert result['requirements'][0]['readiness_status']==expected


def test_missing_report_duplicate_pdf_content_and_unreadable_pdf(p1_runtime):
    r=p1_runtime;case,evaluation,_=fixture_inputs(r)
    response=r.client.post(f'/api/v1/cases/{case}/evaluation-checks',json={**evaluation,'evaluation_document_id':str(uuid4())},headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==404
    # The PDF container may include generated IDs, so explicitly reuse exact bytes via storage.
    with r.app.state.session_factory() as db:
        original=db.get(Document,UUID(evaluation['supplier_document_ids'][0]))
        pdf=(r.settings.storage_root/original.storage_key).read_bytes()
    response=r.client.post(f'/api/v1/cases/{case}/documents',data={'document_type':'WARRANTY_EVIDENCE'},files={'file':('same.pdf',pdf,'application/pdf')},headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==201
    repeated=response.json()['data']['document_id']
    response=r.client.post(f'/api/v1/cases/{case}/evaluation-checks',json={**evaluation,'supplier_document_ids':evaluation['supplier_document_ids']+[repeated]},headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==400
    response=r.client.post(f'/api/v1/cases/{case}/documents',data={'document_type':'WARRANTY_EVIDENCE'},files={'file':('broken.pdf',b'%PDF-broken','application/pdf')},headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==422
    assert r.provider.calls==0


def test_no_applicable_requirement_is_not_fabricated(p1_runtime):
    r=p1_runtime;case,payload,_=readiness_inputs(r)
    r.provider.output={'criteria':[],'observations':[],'decisions':[]}
    job,result=create_readiness(r,case,payload)
    assert job['status']=='NEEDS_REVIEW'
    assert result['requirements']==[] and result['summary']['needs_review']==1


def test_unauthorized_supplier_role_fails_closed(p1_runtime):
    from app.core.security import get_actor, Actor
    r=p1_runtime;case,payload,_=readiness_inputs(r)
    r.app.dependency_overrides[get_actor]=lambda: Actor(r.settings.demo_actor_id,'Untrusted supplier','SUPPLIER',r.settings.demo_scopes)
    response=r.client.post(f'/api/v1/cases/{case}/supplier-readiness-checks',json=payload,headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==403
    assert r.provider.calls==0
    assert r.client.get(f'/api/v1/cases/{case}/supplier-readiness-checks').status_code==403
