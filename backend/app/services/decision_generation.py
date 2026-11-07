"""Synchronous generation with delegated audit and no teammate business logic."""
from datetime import timedelta
import json
from time import perf_counter
from uuid import uuid4
from pydantic import ValidationError

from app.api.response import ApiError, success, failure
from app.api.decision_presenters import challenge_data, repair_data
from app.core.integration import AuditCommand
from app.core.transactions import write_transaction, resource_for, case_for, fingerprint, idempotent_replay, idempotent_response
from app.models import Finding, AiExecution, Challenge, RepairProposal, GenerationLease
from app.models.base import now
from app.schemas.decisions import ChallengeOutput, RepairOutput
from app.services.ai.provider import ProviderFailure
from app.services.ai.decisions import CHALLENGE_PROMPT_VERSION, REPAIR_PROMPT_VERSION
from app.services.decision_evidence import sources_for, check_citations, validate_challenge, validate_repair_text, validated_simulation_context, simulation_interpretation
from app.services.documents.pdf import normalize


def context_for(db, app, actor, case_id, finding_id, kind, payload):
    case, finding, context = sources_for(db, actor, case_id, finding_id)
    if kind == "repair":
        snapshot = app.state.simulation_lookup.get(db, actor, case_id, finding_id, payload.simulation_id)
        context["simulation"] = validated_simulation_context(snapshot, case_id=case_id, finding_id=finding_id, simulation_id=payload.simulation_id)
        context["action_type"] = payload.action_type.value
    else:
        context["requested_evidence"] = payload.requested_evidence
    return context


def delegate_audit(request, db, actor, case_id, event, resource_type, resource_id, version, details=None):
    request.app.state.audit_service.record(db, AuditCommand(actor, request.state.request_id, case_id,
        event, resource_type, resource_id, version, json.dumps(details or {}, sort_keys=True)))


def generate_decision(request, actor, finding_id, payload, kind, *, case_id=None, key=None):
    normalized = payload.model_dump(mode="json")
    token = None
    lease_identity = (actor.actor_id, request.url.path, key)
    with write_transaction(request) as db:
        finding = resource_for(db, actor, Finding, finding_id)
        if case_id is not None:
            case_for(db, actor, case_id)
            if finding.case_id != case_id:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "Finding not found for this case")
        case_id = finding.case_id
        if key is not None:
            replay = idempotent_replay(db, actor, "POST", request.url.path, key, normalized)
            if replay:
                return replay
        context = context_for(db, request.app, actor, case_id, finding_id, kind, payload)
        if len(json.dumps(context, ensure_ascii=False)) > request.app.state.settings.ai_max_input_characters:
            raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Decision source context exceeds the configured limit")
        if key is not None:
            lease = db.get(GenerationLease, lease_identity)
            digest = fingerprint(normalized)
            if lease:
                if lease.request_hash != digest:
                    raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "The key was reserved for different input")
                if lease.expires_at > now():
                    raise ApiError(409, "INVALID_STATE_TRANSITION", "Generation is already in progress")
                db.delete(lease)
                db.flush()
            token = uuid4()
            db.add(GenerationLease(actor_id=actor.actor_id, route=request.url.path, key=key,
                request_hash=digest, token=token,
                expires_at=now() + timedelta(seconds=request.app.state.settings.openai_timeout_seconds + 30)))
    context_digest = fingerprint(context)
    # The model call never holds the SQLite writer lock.
    response = None
    output = None
    error = None
    retry_after = None
    schema_valid = False
    checks = {"checked": 0, "passed": 0, "failed": 0}
    warnings = []
    start = perf_counter()
    try:
        response = request.app.state.decision_provider.generate(kind, json.loads(json.dumps(context)))
        if getattr(response, "response_status", None) not in {None, "completed"}:
            raise ValueError("Incomplete provider response")
        schema = ChallengeOutput if kind == "challenge" else RepairOutput
        output = schema.model_validate_json(response.output_text)
        schema_valid = True
        checks = check_citations(output.evidence, context)
        if checks["failed"]:
            raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Generated citations are not grounded in VERIFIED finding evidence")
        if kind == "challenge":
            validate_challenge(output, context)
        else:
            if not any(normalize(output.before_text) == normalize(ref["excerpt"]) for ref in context["evidence"]) or not any(normalize(output.before_text) == normalize(c.excerpt) for c in output.evidence):
                raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "before_text must reproduce a cited VERIFIED finding excerpt")
            validate_repair_text(output.proposed_text, output.justification, context)
            if payload.action_type == "MAINTAIN_WITH_JUSTIFICATION" and normalize(output.proposed_text) != normalize(output.before_text):
                raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "A maintain action must preserve the evidenced requirement")
    except (ValidationError, ValueError, TypeError):
        warnings = [{"code": "AI_SCHEMA_VALIDATION_FAILED", "message": "Decision output did not match its required schema."}]
        error = ApiError(502, "AI_PROVIDER_ERROR", "Generated decision output did not match its required schema", retryable=True)
    except ProviderFailure as provider_error:
        status = {"AI_PROVIDER_TIMEOUT": 504, "RATE_LIMITED": 429}.get(provider_error.code, 502)
        error = ApiError(status, provider_error.code, "Decision generation could not complete", retryable=provider_error.retryable)
        retry_after = getattr(provider_error, "retry_after", None)
    except ApiError as validation_error:
        error = validation_error
        warnings = [{"code": "EVIDENCE_VALIDATION_FAILED", "message": "Generated decision failed independent grounding or language checks."}]
    except Exception:
        error = ApiError(500, "INTERNAL_ERROR", "Decision generation failed", retryable=True)
    latency_ms = max(0, round((perf_counter() - start) * 1000))
    with write_transaction(request) as db:
        owns_lease = True
        if key is not None:
            lease = db.get(GenerationLease, lease_identity)
            owns_lease = lease is not None and lease.token == token
            if not owns_lease:
                error = ApiError(409, "INVALID_STATE_TRANSITION", "Generation lease was superseded; refresh the request state")
        if error is None:
            try:
                current = context_for(db, request.app, actor, case_id, finding_id, kind, payload)
                if fingerprint(current) != context_digest:
                    raise ApiError(409, "INVALID_STATE_TRANSITION", "Decision source changed while generating; regenerate")
            except ApiError as changed:
                error = changed
                warnings = [{"code": "EVIDENCE_VALIDATION_FAILED", "message": "Decision inputs changed or became unavailable during generation."}]
        execution = AiExecution(case_id=case_id, job_id=None, provider="openai",
            model=response.model if response else None, requested_model=request.app.state.settings.openai_model,
            operation="DRAFT_CHALLENGE" if kind == "challenge" else "DRAFT_REPAIR",
            prompt_version=CHALLENGE_PROMPT_VERSION if kind == "challenge" else REPAIR_PROMPT_VERSION,
            input_document_ids_json=sorted({ref["document_id"] for ref in context["evidence"]}),
            schema_valid=schema_valid, evidence_validation_passed=error is None,
            evidence_checks_json=checks, warnings_json=warnings, latency_ms=latency_ms,
            usage_json=response.usage if response else None)
        db.add(execution)
        db.flush()
        audit_inputs = {"finding_id": str(finding_id), "simulation_id": normalized.get("simulation_id"),
            "source_case_version": context["case_version"], "source_finding_version": context["finding_version"],
            "input_context_sha256": context_digest, "request_hash": fingerprint(normalized),
            "execution_id": str(execution.id)}
        if error is not None:
            delegate_audit(request, db, actor, case_id, f"{kind.upper()}_GENERATION_FAILED", "ai_execution", execution.id, 1,
                {**audit_inputs, "code": error.code, "schema_valid": schema_valid})
            result = failure(error, request.state.request_id)
            if retry_after:
                result.headers["Retry-After"] = str(retry_after)
            if key is not None and owns_lease:
                from app.models import IdempotencyRecord
                db.add(IdempotencyRecord(actor_id=actor.actor_id, method="POST", route=request.url.path, key=key,
                    request_hash=fingerprint(normalized), response_status=error.status, response_body=json.loads(result.body),
                    response_headers={"Retry-After": str(retry_after)} if retry_after else {}))
        else:
            if kind == "challenge":
                row = Challenge(case_id=case_id, finding_id=finding_id, status="DRAFT", question=output.question,
                    risk_rationale=output.risk_rationale, requested_evidence_json=list(payload.requested_evidence), ai_execution_id=execution.id)
            else:
                row = RepairProposal(case_id=case_id, finding_id=finding_id, status="DRAFT", action_type=payload.action_type,
                    before_text=output.before_text, proposed_text=output.proposed_text,
                    justification=output.justification + " " + simulation_interpretation(context),
                    simulation_id=payload.simulation_id, ai_execution_id=execution.id)
            db.add(row)
            db.flush()
            data = challenge_data(row) if kind == "challenge" else repair_data(row)
            delegate_audit(request, db, actor, case_id, f"{kind.upper()}_CREATED", "challenge" if kind == "challenge" else "repair_proposal", row.id, row.version,
                audit_inputs)
            result = success(data, request.state.request_id, 201) if key is None else idempotent_response(db, actor, request, key, normalized, data, 201)
        if key is not None and owns_lease:
            db.delete(lease)
    return result
