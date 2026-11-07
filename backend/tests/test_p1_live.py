"""Explicit opt-in live integration, synthetic uploaded PDFs only.

Set PROCUREMIND_RUN_P1_LIVE=1 to incur two configured-provider calls.
"""
import os
import pytest
from app.services.ai.p1 import P1Provider
from test_evaluation_integrity import p1_runtime, fixture_inputs, create_evaluation
from test_supplier_readiness import readiness_inputs, create_readiness

pytestmark = pytest.mark.skipif(os.getenv("PROCUREMIND_RUN_P1_LIVE") != "1", reason="Live provider calls require explicit opt-in")


def test_live_positive_readiness_from_uploaded_pdf(p1_runtime):
    r=p1_runtime
    if not r.settings.openai_api_key:
        pytest.skip("No backend provider key configured")
    case,payload,_=readiness_inputs(r,months=36)
    r.app.state.p1_provider=P1Provider(r.settings)
    job,result=create_readiness(r,case,payload)
    assert job['status']=='COMPLETED',job['error']
    assert result['requirements'] and all(i['readiness_status']=='VERIFIED' for i in result['requirements'])
    assert job['ai_execution']['model']
    assert job['ai_execution']['schema_valid'] and job['ai_execution']['evidence_validation_passed']


def test_live_negative_evaluation_from_uploaded_pdf(p1_runtime):
    r=p1_runtime
    if not r.settings.openai_api_key:
        pytest.skip("No backend provider key configured")
    case,payload,_=fixture_inputs(r,months=36,decision='NON_COMPLIANT')
    r.app.state.p1_provider=P1Provider(r.settings)
    job,result=create_evaluation(r,case,payload)
    assert job['status']=='COMPLETED',job['error']
    assert result['summary']['inconsistent']==1
    assert len(job['result']['finding_ids'])==1
    assert job['ai_execution']['model']
    assert job['ai_execution']['schema_valid'] and job['ai_execution']['evidence_validation_passed']
