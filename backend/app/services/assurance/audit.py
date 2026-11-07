"""Atomic audit append primitive. Caller owns commit/rollback.

No hash chain is claimed. Null hashes are explicit in the v1.1 wire response.
Actor snapshots live in reserved internal details to avoid a shared table change.
"""
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.response import ApiError
from app.core.security import Actor
from app.models import AuditEvent
from app.models.base import now
from app.services.assurance.access import case_for_actor
from app.services.assurance.schemas import ActorView, AuditActorView, AuditView, Page, ResourceView


def actor_snapshot(actor: Actor) -> dict:
    return ActorView(actor_id=actor.actor_id, display_name=actor.display_name,
                     role=actor.role).model_dump(mode="json")


def append_audit(session: Session, *, actor: Actor, case_id: UUID, request_id: str,
                 event_type: str, resource_type: str, resource_id: UUID,
                 resource_version: int, details: dict) -> AuditEvent:
    if not session.in_transaction():
        raise RuntimeError("Audit append requires a caller-owned transaction")
    if "_actor" in details:
        raise ValueError("_actor is reserved for the trusted backend snapshot")
    row = AuditEvent(id=uuid4(), case_id=case_id, actor_id=actor.actor_id,
        request_id=request_id, event_type=event_type, resource_type=resource_type,
        resource_id=resource_id, resource_version=resource_version,
        details_json={**details, "_actor": actor_snapshot(actor)}, occurred_at=now())
    session.add(row)
    session.flush()
    return row


# Safe fields are allowlisted by event type. Unknown events expose no material
# details until their owner registers a reviewed projection; raw text is never
# returned simply because a field happens to have an innocuous key name.
SAFE_DETAILS = {
    "PROCUREMENT_CONCLUSION_RECORDED": {"decision", "selected_vendor_id", "analysis_job_id", "source_case_version"},
    "REVIEW_COMPLETED": {"decision", "assurance_status_after", "repair_proposal_id",
                         "case_version_before", "case_version_after"},
    "CASE_ASSURANCE_CHANGED": {"assurance_status_before", "assurance_status_after",
                               "review_id", "case_version_before", "case_version_after"},
}


def audit_view(row: AuditEvent) -> AuditView:
    stored = row.details_json
    snapshot = stored.get("_actor")
    if snapshot is None:
        # Do not invent a historical name/role for legacy events.
        snapshot = {"actor_id": str(row.actor_id), "display_name": None, "role": None}
    snapshot = {**snapshot, "actor_id": row.actor_id}
    fields = SAFE_DETAILS.get(row.event_type, set())
    # Material fields emitted by this service are scalars; nested payloads from
    # other producers cannot sneak document text through the allowlist.
    details = {k: v for k, v in stored.items() if k in fields and
               (v is None or isinstance(v, (str, bool, int, float)))}
    return AuditView(event_id=row.id, case_id=row.case_id, event_type=row.event_type,
        actor=AuditActorView(**snapshot), resource=ResourceView(type=row.resource_type,
        id=row.resource_id, version=row.resource_version), occurred_at=row.occurred_at,
        request_id=row.request_id, details=details,
        previous_hash=row.previous_hash, event_hash=row.event_hash)


def list_audit(session: Session, case_id: UUID, actor: Actor, grants: dict,
               limit: int, offset: int) -> Page[AuditView]:
    with session.begin():
        case_for_actor(session, case_id, actor, grants)
        total = session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.case_id == case_id))
        rows = session.scalars(select(AuditEvent).where(AuditEvent.case_id == case_id)
            .order_by(AuditEvent.occurred_at, AuditEvent.id).limit(limit).offset(offset))
        return Page[AuditView](items=[audit_view(r) for r in rows],
                               pagination={"limit": limit, "offset": offset, "total": total})


def get_audit(session: Session, event_id: UUID, actor: Actor, grants: dict) -> AuditView:
    with session.begin():
        row = session.get(AuditEvent, event_id)
        if row is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Audit event not found")
        case_for_actor(session, row.case_id, actor, grants)
        return audit_view(row)
