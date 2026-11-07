"""DC1 grounded proposals; metadata changes still use the existing document PATCH."""
import json
import re
from datetime import timedelta
from time import perf_counter
from uuid import uuid4
from pydantic import ValidationError
from sqlalchemy import select
from app.api.response import ApiError, failure
from app.core.security import check_version
from app.core.transactions import resource_for, write_transaction, fingerprint, idempotent_replay, idempotent_response, audit
from app.models import Document, DocumentPage, AiExecution, GenerationLease, IdempotencyRecord
from app.models.base import now
from app.schemas.classification import ClassificationOutput, ClassificationView
from app.services.decision_evidence import check_citations
from app.services.documents.pdf import normalize
from app.services.ai.provider import ProviderFailure
from app.services.ai.classification import PROMPT_VERSION

PRIMARY_ROLES = {
    "TOR": r"terms\s+of\s+reference|kerangka\s+acuan\s+kerja|\bKAK\b|\bTOR\b",
    "TECHNICAL_SPECIFICATION": r"technical\s+specifications?|spesifikasi\s+teknis",
    "OWNER_COST_ESTIMATE": r"owner.?s?\s+cost\s+estimate|harga\s+perkiraan\s+sendiri|\bHPS\b",
    "TECHNICAL_JUSTIFICATION": r"technical\s+justification|justifikasi\s+teknis",
    "SUPPLIER_QUOTATION": r"supplier\s+quotation|vendor\s+quotation|surat\s+penawaran|penawaran\s+harga",
    "WARRANTY_EVIDENCE": r"warranty\s+(?:certificate|statement|letter|evidence)|certificate\s+of\s+warranty|surat\s+(?:jaminan\s+)?garansi|sertifikat\s+garansi",
    "EVALUATION_REPORT": r"evaluation\s+report|berita\s+acara\s+(?:hasil\s+)?evaluasi|laporan\s+(?:hasil\s+)?evaluasi",
    "CONTRACT": r"\bcontract\b|\bkontrak\b|surat\s+perjanjian",
}


def independent_ready(output, pages, checks):
    heading = pages.get(1, "")[:200]
    roles = {kind for kind, pattern in PRIMARY_ROLES.items() if re.search(pattern, heading, re.I)}
    selected = output.suggested_type.value
    cited_heading = any(c.page_number == 1 and normalize(c.excerpt) in heading and
        re.search(PRIMARY_ROLES.get(selected, r"(?!)"), c.excerpt, re.I) for c in output.evidence)
    draft_contract = selected == "CONTRACT" and bool(re.search(r"\bdraft\b|\btemplate\b|\brancangan\b|\bcontoh\b", heading, re.I))
    return checks["failed"] == 0 and not output.ambiguous and output.confidence >= 0.9 and selected != "OTHER" and roles == {selected} and cited_heading and not draft_contract


def source(db, actor, document_id):
    document = resource_for(db, actor, Document, document_id)
    pages = {p.page_number:p.normalized_text for p in db.scalars(select(DocumentPage).where(DocumentPage.document_id == document_id))}
    if not pages or not any(pages.values()):
        raise ApiError(422, "PDF_EXTRACTION_FAILED", "No usable extracted pages are available")
    return document, pages


def classify(request, actor, document_id, payload, key):
    normalized = payload.model_dump(mode="json")
    lease_id = (actor.actor_id, request.url.path, key)
    token = uuid4()
    settings = request.app.state.settings
    with write_transaction(request) as db:
        document, pages = source(db, actor, document_id)
        case_id = document.case_id
        replay = idempotent_replay(db, actor, "POST", request.url.path, key, normalized)
        if replay:
            return replay
        check_version(document.version, payload.expected_version)
        if sum(map(len, pages.values())) > settings.ai_max_input_characters:
            raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Document text exceeds the configured AI input limit")
        existing = db.get(GenerationLease, lease_id)
        if existing:
            if existing.request_hash != fingerprint(normalized):
                raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "Key reserved with different input")
            if existing.expires_at > now():
                raise ApiError(409, "INVALID_STATE_TRANSITION", "Classification is already processing")
            db.delete(existing)
            db.flush()
        db.add(GenerationLease(actor_id=actor.actor_id, route=request.url.path, key=key, request_hash=fingerprint(normalized), token=token,
            expires_at=now()+timedelta(seconds=settings.openai_timeout_seconds+30)))
        snapshot = (document.sha256, document.version, fingerprint(pages))
    runtime = output = error = None
    checks = {"checked":0,"passed":0,"failed":0}
    schema_valid = False
    started = perf_counter()
    try:
        runtime = request.app.state.classification_provider.classify([
            {"document_id":str(document_id),"page_number":number,"text":content} for number,content in sorted(pages.items())])
        output = ClassificationOutput.model_validate_json(runtime.output_text)
        schema_valid = True
        context = {"evidence":[{"document_id":str(document_id),"page_number":n,"excerpt":t} for n,t in pages.items()]}
        checks = check_citations(output.evidence, context)
    except ValidationError:
        error = ApiError(502,"AI_PROVIDER_ERROR","Classification output did not match the required schema",retryable=True)
    except ProviderFailure as exc:
        status = {"AI_PROVIDER_TIMEOUT":504,"RATE_LIMITED":429}.get(exc.code,502)
        error = ApiError(status,exc.code,"Document classification provider could not complete the request",retryable=exc.retryable)
    except Exception:
        error = ApiError(500,"INTERNAL_ERROR","Document classification failed",retryable=True)
    with write_transaction(request) as db:
        # Retain attempt metadata but never return a proposal after revoked access.
        current_pages = None
        try:
            document, current_pages = source(db, actor, document_id)
        except ApiError as changed:
            error = changed
        lease = db.get(GenerationLease, lease_id)
        owns = lease is not None and lease.token == token
        if not owns:
            error = ApiError(409,"INVALID_STATE_TRANSITION","Classification attempt was superseded")
        if current_pages is not None and (document.sha256, document.version, fingerprint(current_pages)) != snapshot:
            error = ApiError(409,"VERSION_CONFLICT","Document changed while classification was processing")
        ready = error is None and output is not None and independent_ready(output, pages, checks)
        execution = AiExecution(case_id=case_id, job_id=None, provider=settings.openai_provider,
            model=runtime.model if runtime else None, requested_model=settings.openai_model, operation="DOCUMENT_CLASSIFICATION", prompt_version=PROMPT_VERSION,
            input_document_ids_json=[str(document_id)], schema_valid=schema_valid,
            evidence_validation_passed=error is None and checks["checked"]>0 and checks["failed"]==0,
            evidence_checks_json=checks, warnings_json=[] if ready else [{"code":"CLASSIFICATION_REQUIRES_REVIEW","message":"Classification was not eligible for automatic assignment."}],
            latency_ms=max(0,round((perf_counter()-started)*1000)), usage_json=runtime.usage if runtime else None)
        db.add(execution)
        db.flush()
        audit(db, actor, request.state.request_id, case_id, "DOCUMENT_CLASSIFIED", "ai_execution", execution.id, 1,
            {"document_id":str(document_id),"ready":ready,"schema_valid":schema_valid})
        if error:
            response = failure(error, request.state.request_id)
            if owns:
                db.add(IdempotencyRecord(actor_id=actor.actor_id,method="POST",route=request.url.path,key=key,
                    request_hash=fingerprint(normalized),response_status=error.status,response_body=json.loads(response.body)))
        else:
            evidence = []
            for ref in output.evidence:
                passed = str(ref.document_id)==str(document_id) and ref.page_number in pages and normalize(ref.excerpt) in pages[ref.page_number]
                evidence.append({**ref.model_dump(mode="json"),"verification_status":"VERIFIED" if passed else "UNVERIFIED"})
            result = ClassificationView(document_id=document_id,case_id=case_id,expected_version=payload.expected_version,
                suggested_type=output.suggested_type,confidence=output.confidence,status="AUTO_READY" if ready else "NEEDS_REVIEW",
                rationale=output.rationale,evidence=evidence,ai_execution_id=execution.id).model_dump(mode="json")
            response = idempotent_response(db,actor,request,key,normalized,result,201)
        if owns:
            db.delete(lease)
        return response
