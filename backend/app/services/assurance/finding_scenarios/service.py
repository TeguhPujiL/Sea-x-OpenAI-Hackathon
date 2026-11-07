import json
from datetime import timedelta
from time import perf_counter
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import inspect, select

from app.api.presenters import execution_data
from app.api.response import ApiError, failure
from app.core.transactions import case_for, fingerprint, idempotent_replay, idempotent_response, resource_for, wire, write_transaction
from app.models import AiExecution, Finding, GenerationLease, IdempotencyRecord
from app.models.base import now
from app.services.ai.provider import ProviderFailure
from app.services.decision_generation import delegate_audit
from .evidence import deterministic_checks, source_context, validate_output
from .models import FindingScenario
from .migration import migration_checksum, REQUIRED_TRIGGERS
from .provider import OpenAIFindingScenarioProvider, PROMPT_VERSION
from .schemas import ScenarioOutput


def ensure_migrated(db):
    connection = db.connection()
    if not {"finding_scenarios", "finding_scenario_schema_versions"}.issubset(inspect(connection).get_table_names()):
        raise ApiError(500, "INTERNAL_ERROR", "Experimental finding scenario migration is not installed")
    checksum = connection.exec_driver_sql("SELECT checksum FROM finding_scenario_schema_versions WHERE version=1").scalar()
    triggers = set(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='finding_scenarios'").scalars())
    if checksum != migration_checksum(connection) or not REQUIRED_TRIGGERS.issubset(triggers):
        raise ApiError(500, "INTERNAL_ERROR", "Experimental finding scenario migration or integrity guards need operator review")


def scenario_data(db, row):
    execution = db.get(AiExecution, row.ai_execution_id)
    return {"scenario_id": str(row.id), "case_id": str(row.case_id), "finding_id": str(row.finding_id),
        "analysis_job_id": str(row.analysis_job_id), "status": row.status, **row.payload_json,
        "ai_execution": execution_data(execution), "created_at": wire(row.created_at)}


def create_scenario(request, actor, case_id, payload, key):
    if len(key) > 200:
        raise ApiError(400, "VALIDATION_ERROR", "Idempotency-Key exceeds 200 characters")
    normalized = payload.model_dump(mode="json")
    identity = (actor.actor_id, request.url.path, key)
    with write_transaction(request) as db:
        ensure_migrated(db)
        case_for(db, actor, case_id)
        finding = resource_for(db, actor, Finding, payload.finding_id)
        if finding.case_id != case_id:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Finding not found for this case")
        replay = idempotent_replay(db, actor, "POST", request.url.path, key, normalized)
        if replay is not None:
            return replay
        context = source_context(db, actor, case_id, payload)
        if len(json.dumps(context, ensure_ascii=False)) > request.app.state.settings.ai_max_input_characters:
            raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Finding scenario source context exceeds the configured limit")
        lease = db.get(GenerationLease, identity)
        if lease:
            if lease.request_hash != fingerprint(normalized):
                raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "The key was reserved for different scenario input")
            if lease.expires_at > now():
                raise ApiError(409, "INVALID_STATE_TRANSITION", "Scenario generation is already in progress")
            db.delete(lease)
            db.flush()
        token = uuid4()
        db.add(GenerationLease(actor_id=actor.actor_id, route=request.url.path, key=key,
            request_hash=fingerprint(normalized), token=token,
            expires_at=now() + timedelta(seconds=request.app.state.settings.openai_timeout_seconds + 30)))
    context_digest = fingerprint(context)
    response, output, error, retry_after = None, None, None, None
    schema_valid = False
    checks = {"checked": 0, "passed": 0, "failed": 0}
    start = perf_counter()
    try:
        provider = getattr(request.app.state, "finding_scenario_provider", None) or OpenAIFindingScenarioProvider(request.app.state.settings)
        response = provider.generate(json.loads(json.dumps(context)))
        if getattr(response, "response_status", None) not in {None, "completed"} or not response.model:
            raise ValueError("Incomplete scenario provider response")
        output = ScenarioOutput.model_validate_json(response.output_text)
        schema_valid = True
        checks = validate_output(output, context)
    except (ValidationError, ValueError, TypeError):
        error = ApiError(502, "AI_PROVIDER_ERROR", "Scenario generation did not produce a usable validated result", retryable=True)
    except ProviderFailure as provider_error:
        status = {"AI_PROVIDER_TIMEOUT": 504, "RATE_LIMITED": 429}.get(provider_error.code, 502)
        error = ApiError(status, provider_error.code, "Scenario generation could not complete", retryable=provider_error.retryable)
        retry_after = getattr(provider_error, "retry_after", None)
    except ApiError as validation_error:
        error = validation_error
        checks = getattr(validation_error, "evidence_checks", checks)
    except Exception:
        error = ApiError(500, "INTERNAL_ERROR", "Scenario generation failed", retryable=True)
    latency_ms = max(0, round((perf_counter() - start) * 1000))
    with write_transaction(request) as db:
        # Authorization is always current, including completion/error replay.
        case_for(db, actor, case_id)
        lease = db.get(GenerationLease, identity)
        owns_lease = lease is not None and lease.token == token
        if not owns_lease:
            error = ApiError(409, "INVALID_STATE_TRANSITION", "Scenario generation lease was superseded")
        if error is None:
            try:
                current = source_context(db, actor, case_id, payload)
                if fingerprint(current) != context_digest:
                    raise ApiError(409, "INVALID_STATE_TRANSITION", "Scenario source context changed during generation")
            except ApiError as changed:
                error = changed
        execution = AiExecution(case_id=case_id, job_id=None, provider="openai", model=response.model if response else None,
            requested_model=request.app.state.settings.openai_model, operation="FINDING_WHAT_IF_SCENARIO", prompt_version=PROMPT_VERSION,
            input_document_ids_json=sorted({page["document_id"] for page in context["source_pages"]}),
            schema_valid=schema_valid, evidence_validation_passed=error is None, evidence_checks_json=checks,
            warnings_json=[] if error is None else [{"code": error.code, "message": "Scenario output or inputs require review."}],
            latency_ms=latency_ms, usage_json=response.usage if response else None)
        db.add(execution)
        db.flush()
        details = {"experimental_contract": "PROPOSED-v1.2", "finding_id": str(payload.finding_id),
            "analysis_job_id": context["analysis_job_id"], "source_case_version": context["case_version"],
            "source_finding_version": context["finding_version"], "input_context_sha256": context_digest,
            "execution_id": str(execution.id), "request_hash": fingerprint(normalized)}
        if error is not None:
            delegate_audit(request, db, actor, case_id, "FINDING_SCENARIO_FAILED", "ai_execution", execution.id, 1,
                {**details, "code": error.code, "schema_valid": schema_valid})
            result = failure(error, request.state.request_id)
            if retry_after:
                result.headers["Retry-After"] = str(retry_after)
            if owns_lease:
                db.add(IdempotencyRecord(actor_id=actor.actor_id, method="POST", route=request.url.path, key=key,
                    request_hash=fingerprint(normalized), response_status=error.status, response_body=json.loads(result.body),
                    response_headers={"Retry-After": str(retry_after)} if retry_after else {}))
        else:
            deterministic = deterministic_checks(context, checks)
            status = "NEEDS_REVIEW" if context["source_needs_review"] or any(check["status"] in {"CONCERN", "UNKNOWN"} for check in deterministic) else "DRAFT"
            row = FindingScenario(case_id=case_id, finding_id=payload.finding_id, analysis_job_id=context["analysis_job_id"],
                ai_execution_id=execution.id, actor_id=actor.actor_id, request_id=request.state.request_id,
                source_case_version=context["case_version"], source_finding_version=context["finding_version"], context_sha256=context_digest,
                status=status, payload_json={**output.model_dump(mode="json"), "deterministic_checks": deterministic})
            db.add(row)
            db.flush()
            delegate_audit(request, db, actor, case_id, "FINDING_SCENARIO_CREATED", "finding_scenario", row.id, 1, {**details, "status": status})
            result = idempotent_response(db, actor, request, key, normalized, scenario_data(db, row), 201)
        if owns_lease:
            db.delete(lease)
    return result
