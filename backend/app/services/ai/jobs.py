from time import perf_counter
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select, text

from app.api.response import ApiError
from app.core.security import Actor
from app.core.transactions import audit, case_for
from app.models import AnalysisJob, AiExecution, Document, DocumentPage, Finding, EvidenceRef
from app.models.base import now
from app.schemas.p0 import AnalysisOutput
from app.services.ai.provider import ProviderFailure, PROMPT_VERSION
from app.services.documents.pdf import normalize

TERMINAL = {"COMPLETED", "FAILED", "NEEDS_REVIEW"}
ALLOWED = {"QUEUED": {"PROCESSING", "FAILED"}, "PROCESSING": TERMINAL}


def transition(job, target):
    current = getattr(job.processing_status, "value", job.processing_status)
    if target not in ALLOWED.get(current, set()):
        raise ApiError(409, "INVALID_STATE_TRANSITION", "Invalid job transition")
    job.processing_status = target
    if target == "PROCESSING":
        job.started_at = now()
        job.progress_percent = 10
    if target in TERMINAL:
        job.completed_at = now()
        job.progress_percent = 100


def context_for(db, job):
    actor = Actor(job.actor_id, "", "", frozenset())
    case_for(db, actor, job.case_id)
    pages = {}
    for document_id in job.input_document_ids_json:
        document = db.get(Document, UUID(document_id))
        if document is None or document.deleted_at or document.case_id != job.case_id:
            raise ProviderFailure("EVIDENCE_VALIDATION_FAILED", False)
        for page in db.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id)):
            pages[(document_id, page.page_number)] = page.normalized_text
    if not pages:
        raise ProviderFailure("EVIDENCE_VALIDATION_FAILED", False)
    return actor, pages


def execute_job(app, job_id):
    settings = app.state.settings
    result = None
    output = None
    failure = None
    warnings = []
    checks = {"checked": 0, "passed": 0, "failed": 0}
    schema_valid = False
    start = perf_counter()
    # Claim before any provider call; duplicate dispatch does not execute twice.
    with app.state.session_factory() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        job = db.get(AnalysisJob, job_id)
        if job is None or job.processing_status != "QUEUED":
            return
        transition(job, "PROCESSING")
        db.commit()
    try:
        with app.state.session_factory() as db:
            job = db.get(AnalysisJob, job_id)
            actor, pages = context_for(db, job)
            types = list(job.analysis_types)
        if sum(len(v) for v in pages.values()) > settings.ai_max_input_characters:
            raise ProviderFailure("AI_PROVIDER_ERROR", False)  # Explicit bounded input; never silently truncate.
        result = app.state.analysis_provider.analyze(
            [{"document_id": d, "page_number": p, "text": t} for (d, p), t in sorted(pages.items())], types)
        output = AnalysisOutput.model_validate_json(result.output_text)
        if (output.findings and "CONTRADICTION_DETECTION" not in types) or (output.requirements and "REQUIREMENT_EXTRACTION" not in types):
            raise ProviderFailure("AI_SCHEMA_VALIDATION_FAILED")
        schema_valid = True
        for assertion in [*output.requirements, *output.findings]:
            for citation in assertion.evidence:
                checks["checked"] += 1
                key = (str(citation.document_id), citation.page_number)
                if key not in pages:
                    checks["failed"] += 1
                    raise ProviderFailure("EVIDENCE_VALIDATION_FAILED", False)
                matched = bool(normalize(citation.excerpt)) and normalize(citation.excerpt) in pages[key]
                checks["passed" if matched else "failed"] += 1
                if not matched:
                    warnings.append({"code": "EVIDENCE_EXCERPT_NOT_FOUND", "document_id": key[0],
                        "page_number": key[1], "message": "A cited excerpt could not be verified against extracted page text."})
    except ValidationError:
        failure = ProviderFailure("AI_SCHEMA_VALIDATION_FAILED")
    except ProviderFailure as error:
        failure = error
    except ApiError:
        failure = ProviderFailure("RESOURCE_NOT_FOUND", False)
    except Exception:
        # Never persist provider messages, raw outputs or document text as errors.
        failure = ProviderFailure("INTERNAL_ERROR")
    latency = max(0, round((perf_counter() - start) * 1000))
    with app.state.session_factory() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        job = db.get(AnalysisJob, job_id)
        if job.processing_status != "PROCESSING":
            return
        actor = Actor(job.actor_id, "", "", frozenset())
        if failure is None:
            try:
                actor, current_pages = context_for(db, job)
                if current_pages != pages:
                    raise ProviderFailure("EVIDENCE_VALIDATION_FAILED", False)
            except (ApiError, ProviderFailure):
                failure = ProviderFailure("EVIDENCE_VALIDATION_FAILED", False)
        execution = AiExecution(case_id=job.case_id, job_id=job.id, provider=settings.openai_provider,
            model=result.model if result else None, requested_model=settings.openai_model,
            operation="EXTRACT_AND_COMPARE", prompt_version=PROMPT_VERSION,
            input_document_ids_json=job.input_document_ids_json, schema_valid=schema_valid,
            evidence_validation_passed=schema_valid and failure is None and checks["failed"] == 0,
            evidence_checks_json=checks, warnings_json=warnings, latency_ms=latency,
            usage_json=result.usage if result else None)
        db.add(execution)
        db.flush()
        finding_ids = []
        if failure is None:
            for candidate in output.findings:
                verified = all(normalize(c.excerpt) and normalize(c.excerpt) in pages[(str(c.document_id), c.page_number)] for c in candidate.evidence)
                finding = Finding(case_id=job.case_id, analysis_job_id=job.id, ai_execution_id=execution.id,
                    type=candidate.type, severity=candidate.severity, title=candidate.title,
                    summary=candidate.summary, confidence=candidate.confidence,
                    evidence_status="VERIFIED" if verified else "UNVERIFIED")
                db.add(finding)
                db.flush()
                finding_ids.append(str(finding.id))
                for citation in candidate.evidence:
                    matched = normalize(citation.excerpt) and normalize(citation.excerpt) in pages[(str(citation.document_id), citation.page_number)]
                    db.add(EvidenceRef(finding_id=finding.id, document_id=citation.document_id,
                        page_number=citation.page_number, excerpt=citation.excerpt,
                        verification_status="VERIFIED" if matched else "UNVERIFIED"))
                audit(db, actor, job.request_id, job.case_id, "FINDING_CREATED", "finding", finding.id, finding.version)
            job.result_json = {"requirement_count": len(output.requirements), "finding_ids": finding_ids}
            job.requirements_json = [r.model_dump(mode="json") for r in output.requirements]
            job.warnings_json = warnings
            transition(job, "NEEDS_REVIEW" if warnings else "COMPLETED")
        else:
            job.result_json = None
            job.error_json = {"code": failure.code, "message": "Analysis could not produce a usable validated result.", "retryable": failure.retryable}
            job.warnings_json = warnings
            transition(job, "FAILED")
        audit(db, actor, job.request_id, job.case_id, "ANALYSIS_FINISHED", "analysis_job", job.id, 1,
            {"status": job.processing_status, "execution_id": str(execution.id)})
        db.commit()


def recover_interrupted_jobs(app):
    """Single-process MVP startup recovery. Never rewrite a terminal execution."""
    from sqlalchemy import inspect
    with app.state.session_factory() as db:
        if "analysis_jobs" not in inspect(db.bind).get_table_names():
            return
        columns = {c["name"] for c in inspect(db.bind).get_columns("analysis_jobs")}
        if not {"actor_id", "input_document_ids_json"} <= columns:
            return  # Explicit migration is required; do not guess legacy provenance.
        db.execute(text("BEGIN IMMEDIATE"))
        rows = db.scalars(select(AnalysisJob).where(AnalysisJob.processing_status.in_(["QUEUED", "PROCESSING"]), AnalysisJob.actor_id.is_not(None))).all()
        for job in rows:
            transition(job, "FAILED")
            job.result_json = None
            job.error_json = {"code": "INTERNAL_ERROR", "message": "The server restarted before analysis completed.", "retryable": True}
            actor = Actor(job.actor_id, "", "", frozenset())
            audit(db, actor, job.request_id, job.case_id, "ANALYSIS_INTERRUPTED", "analysis_job", job.id, 1)
        db.commit()
