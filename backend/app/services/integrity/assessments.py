"""P1 orchestration using shared ACL, immutable jobs/executions and AuditService."""
from time import perf_counter
from uuid import UUID, uuid4
from pydantic import ValidationError
from sqlalchemy import select, text, inspect
from app.api.response import ApiError
from app.api.presenters import job_data
from app.core.security import Actor, check_version
from app.core.transactions import case_for, resource_for, audit, idempotent_replay, idempotent_response, wire
from app.models import AnalysisJob, AiExecution, Document, DocumentPage, Finding, EvidenceRef
from app.models.base import now
from app.models.p1 import AssessmentCheck, AssessmentResult
from app.schemas.evaluation import AssessmentOutput, AssessmentView
from app.services.ai.jobs import transition
from app.services.ai.provider import ProviderFailure
from app.services.ai.p1 import PROMPT_VERSION
from app.services.evidence.supplier_readiness import EvidenceValidator, readiness
from app.services.integrity.evaluation_checker import evaluate

TERMINAL = {"COMPLETED", "NEEDS_REVIEW", "FAILED"}


def require_migration(db):
    if "p1_checks" not in inspect(db.bind).get_table_names():
        raise ApiError(409, "INVALID_STATE_TRANSITION", "Apply the explicit P1 migration before using the proposed extension")


def documents_for(db, actor, case_id, kind, payload):
    criteria = payload.get("criteria_document_ids", payload.get("requirement_document_ids", []))
    supplier = payload["supplier_document_ids"]
    report = [payload["evaluation_document_id"]] if kind == "EVALUATION" else []
    ids = criteria + supplier + report
    if len(ids) != len(set(map(str, ids))):
        raise ApiError(400, "VALIDATION_ERROR", "Duplicate document references are not allowed")
    rows, digests = [], set()
    for value in ids:
        row = resource_for(db, actor, Document, UUID(str(value)))
        if row.case_id != case_id:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Document not found")
        expected = {"TOR", "TECHNICAL_SPECIFICATION"} if value in criteria else {"EVALUATION_REPORT"} if value in report else {"SUPPLIER_QUOTATION", "WARRANTY_EVIDENCE", "OTHER"}
        if row.document_type.value not in expected or row.processing_status.value != "COMPLETED":
            raise ApiError(400, "VALIDATION_ERROR", "Document role or processing status does not match the assessment input")
        if row.sha256 in digests:
            raise ApiError(400, "VALIDATION_ERROR", "Duplicate PDF content is not allowed in an assessment")
        digests.add(row.sha256)
        if not db.scalar(select(DocumentPage.id).where(DocumentPage.document_id == row.id).limit(1)):
            raise ApiError(422, "PDF_EXTRACTION_FAILED", "Document has no extracted pages")
        rows.append({"document_id": str(row.id), "sha256": row.sha256, "version": row.version, "document_type": row.document_type.value})
    return rows


def create_check(db, request, actor, case_id, kind, payload, key, previous=None):
    require_migration(db)
    case = case_for(db, actor, case_id)
    if actor.role not in {"ANALYST", "REVIEWER", "ADMIN"}:
        raise ApiError(403, "FORBIDDEN", "A backend analyst or reviewer role is required")
    if case.case_status.value in {"ARCHIVED", "REVIEW_COMPLETED"}:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "The case is not open for new assessments")
    snapshot = documents_for(db, actor, case_id, kind, payload)
    replay = idempotent_replay(db, actor, "POST", request.url.path, key, payload)
    if replay:
        return replay, None
    if previous:
        check_version(previous.version, payload["expected_version"])
        old_job = db.get(AnalysisJob, previous.job_id)
        if old_job.processing_status.value not in TERMINAL:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Previous assessment is still processing")
        if payload["supplier_ref"] != previous.supplier_ref or payload["requirement_document_ids"] != previous.request_json["requirement_document_ids"]:
            raise ApiError(400, "VALIDATION_ERROR", "Revalidation must retain supplier and governing requirements")
    job = AnalysisJob(id=uuid4(), case_id=case_id, analysis_types=["REQUIREMENT_EXTRACTION"],
        input_document_ids_json=[r["document_id"] for r in snapshot], actor_id=actor.actor_id, request_id=request.state.request_id)
    db.add(job)
    db.flush()
    check = AssessmentCheck(id=uuid4(), case_id=case_id, job_id=job.id, kind=kind,
        supplier_ref=payload.get("supplier_ref"), version=previous.version+1 if previous else 1,
        previous_check_id=previous.id if previous else None, reference_date=now().date(),
        request_json=payload, documents_json=snapshot)
    db.add(check)
    db.flush()
    audit(db, actor, request.state.request_id, case_id, "P1_REVALIDATION_REQUESTED" if previous else "P1_CHECK_REQUESTED", "p1_check", check.id, check.version,
        {"job_id": str(job.id), "kind": kind, "previous_check_id": str(previous.id) if previous else None})
    return idempotent_response(db, actor, request, key, payload, job_data(db, job), 202), check.id


def check_for(db, actor, check_id, kind):
    require_migration(db)
    check = resource_for(db, actor, AssessmentCheck, check_id)
    if check.kind != kind:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Assessment not found")
    return check


def view(db, check):
    job = db.get(AnalysisJob, check.job_id)
    result = db.get(AssessmentResult, check.id)
    execution = db.scalar(select(AiExecution).where(AiExecution.job_id == job.id))
    data = {"check_id": check.id, "case_id": check.case_id, "job_id": check.job_id,
        "kind": check.kind, "version": check.version, "previous_check_id": check.previous_check_id,
        "supplier_ref": check.supplier_ref, "status": job.processing_status,
        "ai_execution_id": execution.id if execution else None, "reference_date": check.reference_date,
        "summary": {}, "items": [], "requirements": [], "finding_ids": [], "changes": [], "created_at": check.created_at}
    if result:
        data.update(result.result_json)
    return AssessmentView.model_validate(data).model_dump(mode="json")


def load_context(db, check, actor):
    case_for(db, actor, check.case_id)
    current = documents_for(db, actor, check.case_id, check.kind, check.request_json)
    if current != check.documents_json:
        raise ProviderFailure("EVIDENCE_VALIDATION_FAILED", False)
    pages = {}
    for row in current:
        for page in db.scalars(select(DocumentPage).where(DocumentPage.document_id == UUID(row["document_id"]))):
            pages[(row["document_id"], page.page_number)] = page.normalized_text
    return pages


def run_check(app, check_id):
    started = perf_counter()
    with app.state.session_factory() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        check = db.get(AssessmentCheck, check_id)
        if check is None:
            return
        job = db.get(AnalysisJob, check.job_id)
        if job.processing_status.value != "QUEUED":
            return
        transition(job, "PROCESSING")
        db.commit()
        actor = Actor(job.actor_id, "", "", frozenset())
        # Actual identity snapshots for audit remain backend-owned; no model/client identity.
        configured = app.state.settings
        if configured.demo_actor_id == job.actor_id:
            actor = Actor(job.actor_id, configured.demo_display_name, configured.demo_role, configured.demo_scopes)
        request_id = job.request_id
    output = runtime = validator = result = None
    failure = None
    schema_valid = False
    try:
        with app.state.session_factory() as db:
            pages = load_context(db, check, actor)
        if sum(map(len, pages.values())) > app.state.settings.ai_max_input_characters:
            raise ProviderFailure("AI_PROVIDER_ERROR", False)
        runtime = app.state.p1_provider.extract({"kind": check.kind, "request": check.request_json,
            "reference_date": check.reference_date.isoformat(), "pages": [
                {"document_id": d, "page_number": p, "text": t} for (d, p), t in sorted(pages.items())]})
        output = AssessmentOutput.model_validate_json(runtime.output_text)
        schema_valid = True
        validator = EvidenceValidator(pages)
        payload = check.request_json
        criteria = set(payload.get("criteria_document_ids", payload.get("requirement_document_ids", [])))
        suppliers = set(payload["supplier_document_ids"])
        result = {"summary": {}, "items": [], "requirements": [], "finding_ids": [], "changes": []}
        if check.kind == "EVALUATION":
            result["items"] = evaluate(output, validator, criteria, suppliers, payload["evaluation_document_id"], check.reference_date, payload["check_types"])
            outcomes = [i["consistency_result"] for i in result["items"]]
            missing_statements = max(0, len(output.criteria) - len({i["criterion_id"] for i in result["items"]}))
            result["summary"] = {"criteria_checked": len(outcomes), "consistent": outcomes.count("CONSISTENT"),
                "inconsistent": outcomes.count("INCONSISTENT"), "needs_review": outcomes.count("NEEDS_REVIEW") + missing_statements}
        else:
            if output.decisions:
                raise ProviderFailure("AI_SCHEMA_VALIDATION_FAILED", False)
            result["requirements"] = readiness(output, validator, criteria, suppliers, payload["supplier_ref"], check.reference_date, payload["include_remediation_guidance"])
            outcomes = [i["readiness_status"] for i in result["requirements"]]
            result["summary"] = {"requirements_total": len(outcomes), **{k.lower(): outcomes.count(k) for k in ("VERIFIED", "MISSING", "NON_COMPLIANT", "NEEDS_REVIEW", "NOT_APPLICABLE")}}
        if not output.criteria:
            result["summary"]["needs_review"] = max(1, result["summary"].get("needs_review", 0))
    except ValidationError:
        failure = ProviderFailure("AI_SCHEMA_VALIDATION_FAILED", False)
        schema_valid = False
    except ProviderFailure as error:
        failure = error
        if error.code == "AI_SCHEMA_VALIDATION_FAILED":
            schema_valid = False
    except ApiError:
        failure = ProviderFailure("EVIDENCE_VALIDATION_FAILED", False)
    except Exception:
        failure = ProviderFailure("INTERNAL_ERROR")
    with app.state.session_factory() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        job = db.get(AnalysisJob, check.job_id)
        if job.processing_status.value != "PROCESSING":
            return
        if failure is None:
            try:
                if load_context(db, check, actor) != pages:
                    raise ProviderFailure("EVIDENCE_VALIDATION_FAILED", False)
            except (ApiError, ProviderFailure):
                failure = ProviderFailure("EVIDENCE_VALIDATION_FAILED", False)
        checks = validator.checks if validator else {"checked": 0, "passed": 0, "failed": 0}
        warnings = validator.warnings if validator else []
        execution = AiExecution(case_id=check.case_id, job_id=job.id, provider=app.state.settings.openai_provider,
            model=runtime.model if runtime else None, requested_model=app.state.settings.openai_model,
            operation="EVALUATION_INTEGRITY_CHECK" if check.kind == "EVALUATION" else "SUPPLIER_READINESS_CHECK", prompt_version=PROMPT_VERSION,
            input_document_ids_json=job.input_document_ids_json, schema_valid=schema_valid,
            evidence_validation_passed=failure is None and checks["failed"] == 0 and checks["checked"] > 0,
            evidence_checks_json=checks, warnings_json=warnings, latency_ms=max(0, round((perf_counter()-started)*1000)),
            usage_json=runtime.usage if runtime else None)
        db.add(execution)
        db.flush()
        if failure:
            job.error_json = {"code": failure.code, "message": "P1 assessment could not produce a usable validated result.", "retryable": failure.retryable}
            transition(job, "FAILED")
        else:
            for item in result["items"]:
                if item["consistency_result"] != "INCONSISTENT":
                    continue
                # No unverified assertions may enter the shared findings collection.
                if any(e["verification_status"] != "VERIFIED" for e in item["evidence"]):
                    continue
                finding = Finding(case_id=check.case_id, analysis_job_id=job.id, ai_execution_id=execution.id,
                    type="EVALUATION_DECISION_INCONSISTENCY", severity="MEDIUM", title="Evaluation decision requires re-evaluation",
                    summary=f"{item['supplier_ref']} / {item['criterion_id']}: {item['explanation']}",
                    confidence=next(d.confidence for d in output.decisions if d.criterion_id == item['criterion_id'] and d.supplier_ref == item['supplier_ref']),
                    evidence_status="VERIFIED")
                db.add(finding)
                db.flush()
                refs = {(r["document_id"], r["page_number"], r["excerpt"]) for r in item["evidence"]}
                for d, p, excerpt in refs:
                    db.add(EvidenceRef(finding_id=finding.id, document_id=UUID(d), page_number=p, excerpt=excerpt, verification_status="VERIFIED"))
                result["finding_ids"].append(str(finding.id))
                audit(db, actor, request_id, check.case_id, "FINDING_CREATED", "finding", finding.id, 1)
            if check.previous_check_id:
                previous = db.get(AssessmentResult, check.previous_check_id)
                before = {i["requirement_id"]: i["readiness_status"] for i in previous.result_json["requirements"]} if previous else {}
                after = {i["requirement_id"]: i["readiness_status"] for i in result["requirements"]}
                result["changes"] = [{"requirement_id": k, "before_status": before.get(k), "after_status": after.get(k)} for k in sorted(before.keys() | after.keys()) if before.get(k) != after.get(k)]
            db.add(AssessmentResult(check_id=check.id, ai_execution_id=execution.id, result_json=result))
            job.result_json = {"requirement_count": len(output.criteria), "finding_ids": result["finding_ids"]}
            job.requirements_json = [c.model_dump(mode="json") for c in output.criteria]
            transition(job, "NEEDS_REVIEW" if warnings or result["summary"].get("needs_review") or result["summary"].get("missing") else "COMPLETED")
        job.warnings_json = warnings
        audit(db, actor, request_id, check.case_id, "P1_CHECK_FINISHED", "p1_check", check.id, check.version,
            {"status": wire(job.processing_status), "execution_id": str(execution.id)})
        db.commit()
