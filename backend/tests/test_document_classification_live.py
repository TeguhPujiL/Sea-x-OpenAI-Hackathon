"""Explicit opt-in: nine small synthetic PDFs, real classification provider."""
import os
import pytest
from sqlalchemy import select
from app.models import AiExecution
from app.services.ai.classification import ClassificationProvider
from test_document_classification import dc_runtime,HEADINGS,BODY,classify
from test_evaluation_integrity import new_case,upload

pytestmark=pytest.mark.skipif(os.getenv('PROCUREMIND_RUN_CLASSIFICATION_LIVE')!='1',reason='Live classification requires explicit opt-in')


@pytest.mark.parametrize('kind',list(HEADINGS))
def test_live_nine_document_roles(dc_runtime,kind):
    r=dc_runtime
    if not r.settings.openai_api_key:pytest.skip('No provider key configured')
    case=new_case(r);doc=upload(r,case,HEADINGS[kind]+'\n'+BODY[kind],'OTHER')
    r.app.state.classification_provider=ClassificationProvider(r.settings)
    response=classify(r,doc);assert response.status_code==201,response.text
    result=response.json()['data']
    assert result['suggested_type']==kind,result
    assert result['status']==('NEEDS_REVIEW' if kind=='OTHER' else 'AUTO_READY'),result
    assert all(e['verification_status']=='VERIFIED' for e in result['evidence'])
    with r.app.state.session_factory() as db:
        execution=db.scalar(select(AiExecution))
        assert execution.model and execution.schema_valid and execution.evidence_validation_passed
    if result['status']=='AUTO_READY':
        patched=r.client.patch(f'/api/v1/documents/{doc}',json={'document_type':result['suggested_type'],'expected_version':result['expected_version']})
        assert patched.status_code==200 and patched.json()['data']['document_type']==kind
