from contextlib import contextmanager
from hashlib import sha256
import json
from uuid import UUID
from datetime import datetime
from enum import Enum

from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from app.api.response import ApiError, success
from app.models import Case, CaseAccess, IdempotencyRecord, AuditEvent
from app.models.base import now


def wire(value):
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [wire(v) for v in value]
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    return value


@contextmanager
def write_transaction(request):
    # Serialize SQLite writers before checking idempotency and expected_version.
    # The provider call is outside this transaction.
    with request.app.state.session_factory() as db:
        try:
            db.execute(text("BEGIN IMMEDIATE"))
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def case_for(db, actor, case_id, include_deleted=False):
    row = db.get(Case, case_id)
    if row is None or (row.deleted_at and not include_deleted) or db.get(CaseAccess, (case_id, actor.actor_id)) is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Case not found")
    return row


def resource_for(db, actor, model, resource_id):
    row = db.get(model, resource_id)
    if row is None or getattr(row, "deleted_at", None):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Resource not found")
    try:
        case_for(db, actor, row.case_id)
    except ApiError:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Resource not found") from None
    return row


def append_core_audit(db, actor, request_id, case_id, event_type, resource_type, resource_id, version, details=None):
    # Integration writer only; Fazhima owns review/audit services and routes.
    db.add(AuditEvent(case_id=case_id, actor_id=actor.actor_id, request_id=request_id,
        event_type=event_type, resource_type=resource_type, resource_id=resource_id,
        resource_version=version, details_json=wire(details or {}), occurred_at=now()))



def audit(db, actor, request_id, case_id, event_type, resource_type, resource_id, version, details=None):
    """Delegate owned phase-A writes to the app's transaction-bound audit port."""
    resolve = db.info.get("audit_service_provider")
    service = resolve() if resolve else db.info.get("audit_service")
    if service is None:
        # Explicit default for trusted CLI/standalone sessions outside the app.
        return append_core_audit(db, actor, request_id, case_id, event_type, resource_type, resource_id, version, details)
    from app.core.integration import AuditCommand
    service.record(db, AuditCommand(actor, request_id, case_id, event_type, resource_type,
        resource_id, version, json.dumps(wire(details or {}), sort_keys=True)))


def fingerprint(payload):
    return sha256(json.dumps(wire(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def idempotent_replay(db, actor, method, route, key, payload):
    digest = fingerprint(payload)
    row = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.actor_id == actor.actor_id,
        IdempotencyRecord.method == method, IdempotencyRecord.route == route, IdempotencyRecord.key == key))
    if row:
        if row.request_hash != digest:
            raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "The idempotency key was used with different input")
        return JSONResponse(row.response_body, status_code=row.response_status, headers=row.response_headers or {})
    return None


def idempotent_response(db, actor, request, key, payload, data, status):
    response = success(wire(data), request.state.request_id, status)
    db.add(IdempotencyRecord(actor_id=actor.actor_id, method=request.method, route=request.url.path,
        key=key, request_hash=fingerprint(payload), response_status=status,
        response_body=json.loads(response.body)))
    return response
