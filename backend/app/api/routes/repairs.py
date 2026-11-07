from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from pydantic import UUID4
from sqlalchemy import func, select

from app.api.response import ApiError, success
from app.api.presenters import page
from app.api.decision_presenters import repair_data
from app.core.security import Actor, require_scope, require_idempotency_key, check_version
from app.core.transactions import write_transaction, resource_for, wire
from app.models import RepairProposal, Finding, AiExecution, SubmittedRepairSnapshot
from app.models.base import now
from app.schemas.shared import Envelope
from app.schemas.p0 import DeleteRequest, ListData
from app.schemas.decisions import RepairCreate, RepairPatch, RepairView, RepairDeleted
from app.services.decision_generation import generate_decision, delegate_audit
from app.services.decision_evidence import sources_for, validated_simulation_context, validate_repair_text
from app.services.documents.pdf import normalize

router = APIRouter(tags=["repairs"])


@router.post("/findings/{finding_id}/repair-proposals", status_code=201, response_model=Envelope[RepairView])
def create_repair(finding_id: UUID4, payload: RepairCreate, request: Request,
    actor: Annotated[Actor, Depends(require_scope("repair:write"))],
    key: Annotated[str, Depends(require_idempotency_key)]):
    return generate_decision(request, actor, finding_id, payload, "repair", key=key)


@router.get("/findings/{finding_id}/repair-proposals", response_model=Envelope[ListData[RepairView]])
def list_repairs(finding_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("repair:read"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0):
    if set(request.query_params) - {"limit", "offset"}:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown query field")
    with request.app.state.session_factory() as db:
        finding = resource_for(db, actor, Finding, finding_id)
        query = select(RepairProposal).where(RepairProposal.finding_id == finding_id,
            RepairProposal.case_id == finding.case_id, RepairProposal.deleted_at.is_(None))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(RepairProposal.created_at, RepairProposal.id).limit(limit).offset(offset)).all()
        return success(page([repair_data(r) for r in rows], total, limit, offset), request.state.request_id)


@router.get("/repair-proposals/{repair_proposal_id}", response_model=Envelope[RepairView])
def get_repair(repair_proposal_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("repair:read"))]):
    with request.app.state.session_factory() as db:
        return success(repair_data(resource_for(db, actor, RepairProposal, repair_proposal_id)), request.state.request_id)


@router.patch("/repair-proposals/{repair_proposal_id}", response_model=Envelope[RepairView])
def patch_repair(repair_proposal_id: UUID4, payload: RepairPatch, request: Request,
    actor: Annotated[Actor, Depends(require_scope("repair:write"))]):
    with write_transaction(request) as db:
        row = resource_for(db, actor, RepairProposal, repair_proposal_id)
        check_version(row.version, payload.expected_version)
        if row.status != "DRAFT" or request.app.state.reference_lookup.repair_in_use(db, row):
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Only unreferenced DRAFT repair proposals may be edited")
        if payload.status is not None and payload.status not in {"DRAFT", "SUBMITTED"}:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Draft edit cannot set a review decision status")
        case, finding, context = sources_for(db, actor, row.case_id, row.finding_id)
        snapshot = request.app.state.simulation_lookup.get(db, actor, row.case_id, row.finding_id, row.simulation_id)
        context["simulation"] = validated_simulation_context(snapshot, case_id=row.case_id, finding_id=row.finding_id, simulation_id=row.simulation_id)
        if not any(normalize(row.before_text) == normalize(r["excerpt"]) for r in context["evidence"]):
            raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Original text is no longer supported by VERIFIED evidence")
        execution = resource_for(db, actor, AiExecution, row.ai_execution_id)
        if execution.operation != "DRAFT_REPAIR" or not execution.schema_valid or not execution.evidence_validation_passed:
            raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Repair generation provenance is not valid")
        proposed = payload.proposed_text if payload.proposed_text is not None else row.proposed_text
        validate_repair_text(proposed, "", context)
        if row.action_type == "MAINTAIN_WITH_JUSTIFICATION" and normalize(proposed) != normalize(row.before_text):
            raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Maintain action must preserve the evidenced requirement")
        if payload.proposed_text is not None:
            row.proposed_text = payload.proposed_text
            row.human_edits = True
        if payload.status is not None:
            row.status = payload.status
        row.version += 1
        if row.status == "SUBMITTED":
            case.case_status = "UNDER_REVIEW"
            case.assurance_status = "READY_FOR_REVIEW"
            case.version += 1
        db.flush()
        data = repair_data(row)
        if row.status == "SUBMITTED":
            db.add(SubmittedRepairSnapshot(repair_proposal_id=row.id, version=row.version, snapshot_json=data))
        delegate_audit(request, db, actor, row.case_id, "REPAIR_SUBMITTED" if row.status == "SUBMITTED" else "REPAIR_UPDATED",
            "repair_proposal", row.id, row.version, {"status": row.status, "case_version": case.version})
    return success(data, request.state.request_id)


@router.delete("/repair-proposals/{repair_proposal_id}", response_model=Envelope[RepairDeleted])
def delete_repair(repair_proposal_id: UUID4, payload: DeleteRequest, request: Request,
    actor: Annotated[Actor, Depends(require_scope("repair:delete"))]):
    with write_transaction(request) as db:
        row = resource_for(db, actor, RepairProposal, repair_proposal_id)
        check_version(row.version, payload.expected_version)
        if row.status != "DRAFT" or request.app.state.reference_lookup.repair_in_use(db, row):
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Only an unreferenced DRAFT repair proposal may be deleted")
        row.deleted_at = now()
        row.version += 1
        delegate_audit(request, db, actor, row.case_id, "REPAIR_DELETED", "repair_proposal", row.id, row.version,
            {"reason": payload.reason})
        data = {"repair_proposal_id": str(row.id), "deleted_at": wire(row.deleted_at)}
    return success(data, request.state.request_id)
