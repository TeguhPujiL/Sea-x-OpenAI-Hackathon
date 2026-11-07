from app.schemas.shared import Envelope
from app.schemas.p0 import DocumentView, DocumentDeleted, ListData
import os
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from pydantic import UUID4
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.api.response import ApiError, success
from app.api.presenters import document_data, page
from app.core.config import Settings, get_settings
from app.core.security import Actor, require_scope, require_idempotency_key, check_version
from app.core.transactions import audit, case_for, resource_for, idempotent_replay, idempotent_response, write_transaction, wire
from app.models import Document, DocumentPage, Review, EvidenceRef, Finding, AnalysisJob
from app.models.base import now
from app.schemas.shared import DocumentType
from app.schemas.p0 import DocumentPatch, DeleteRequest
from app.services.documents.pdf import extract_pdf

router = APIRouter(tags=["documents"])


@router.post("/cases/{case_id}/documents", status_code=201, response_model=Envelope[DocumentView])
async def upload_document(case_id: UUID4, request: Request,
    actor: Annotated[Actor, Depends(require_scope("document:write"))],
    key: Annotated[str, Depends(require_idempotency_key)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: UploadFile = File(...), document_type: DocumentType = Form(...), description: str | None = Form(None)):
    form = await request.form()
    if set(form) - {"file", "document_type", "description"} or any(len(form.getlist(k)) != 1 for k in form):
        raise ApiError(400, "VALIDATION_ERROR", "Unknown or duplicate multipart field")
    with request.app.state.session_factory() as db:
        case_for(db, actor, case_id)
    payload = await file.read(settings.upload_max_bytes + 1)
    await file.close()
    digest, pages = await run_in_threadpool(extract_pdf, payload, file.content_type, settings)
    filename = (file.filename or "document.pdf").replace("\\", "/").rsplit("/", 1)[-1]
    normalized = {"sha256": digest, "filename": filename, "document_type": document_type.value, "description": description}
    stored_path = None
    created_file = False
    try:
        with write_transaction(request) as db:
            case_for(db, actor, case_id)
            replay = idempotent_replay(db, actor, "POST", request.url.path, key, normalized)
            if replay:
                return replay
            document_id = uuid4()
            storage_root = settings.storage_root.resolve()
            storage_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            storage_key = f"{document_id}.pdf"
            stored_path = storage_root / storage_key
            with stored_path.open("xb") as target:
                created_file = True
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            row = Document(id=document_id, case_id=case_id, document_type=document_type,
                filename=filename, description=description, storage_key=storage_key,
                sha256=digest, size_bytes=len(payload), page_count=len(pages), uploaded_at=now(), processing_status="COMPLETED")
            db.add(row)
            db.flush()
            for number, text in enumerate(pages, start=1):
                db.add(DocumentPage(document_id=document_id, page_number=number, normalized_text=text))
            audit(db, actor, request.state.request_id, case_id, "DOCUMENT_UPLOADED", "document", row.id, row.version,
                {"sha256": digest, "page_count": len(pages)})
            response = idempotent_response(db, actor, request, key, normalized, document_data(row), 201)
    except Exception:
        if created_file and stored_path is not None:
            stored_path.unlink(missing_ok=True)
        raise
    return response


@router.get("/cases/{case_id}/documents", response_model=Envelope[ListData[DocumentView]])
def list_documents(case_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("document:read"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0):
    if set(request.query_params) - {"limit", "offset"}:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown query field")
    with request.app.state.session_factory() as db:
        case_for(db, actor, case_id)
        query = select(Document).where(Document.case_id == case_id, Document.deleted_at.is_(None))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(Document.uploaded_at, Document.id).limit(limit).offset(offset)).all()
        return success(page([document_data(r) for r in rows], total, limit, offset), request.state.request_id)


@router.get("/documents/{document_id}", response_model=Envelope[DocumentView])
def get_document(document_id: UUID4, request: Request, actor: Annotated[Actor, Depends(require_scope("document:read"))]):
    with request.app.state.session_factory() as db:
        return success(document_data(resource_for(db, actor, Document, document_id)), request.state.request_id)


@router.patch("/documents/{document_id}", response_model=Envelope[DocumentView])
def patch_document(document_id: UUID4, payload: DocumentPatch, request: Request,
    actor: Annotated[Actor, Depends(require_scope("document:write"))]):
    with write_transaction(request) as db:
        row = resource_for(db, actor, Document, document_id)
        check_version(row.version, payload.expected_version)
        for name, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
            setattr(row, name, value)
        row.version += 1
        db.flush()
        audit(db, actor, request.state.request_id, row.case_id, "DOCUMENT_UPDATED", "document", row.id, row.version)
        data = document_data(row)
    return success(data, request.state.request_id)


@router.delete("/documents/{document_id}", response_model=Envelope[DocumentDeleted])
def delete_document(document_id: UUID4, payload: DeleteRequest, request: Request,
    actor: Annotated[Actor, Depends(require_scope("document:delete"))]):
    with write_transaction(request) as db:
        row = resource_for(db, actor, Document, document_id)
        check_version(row.version, payload.expected_version)
        used = db.scalar(select(EvidenceRef.id).join(Finding, EvidenceRef.finding_id == Finding.id)
            .where(EvidenceRef.document_id == document_id, Finding.case_id == row.case_id).limit(1))
        reviewed = db.scalar(select(Review.id).where(Review.case_id == row.case_id).limit(1))
        if used and reviewed:
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Finalized review references document evidence")
        active = db.scalars(select(AnalysisJob).where(AnalysisJob.case_id == row.case_id,
            AnalysisJob.processing_status.in_(["QUEUED", "PROCESSING"]))).all()
        if any(str(document_id) in j.input_document_ids_json for j in active):
            raise ApiError(409, "INVALID_STATE_TRANSITION", "Document is in an active analysis")
        row.deleted_at = now()
        row.version += 1
        audit(db, actor, request.state.request_id, row.case_id, "DOCUMENT_DELETED", "document", row.id, row.version,
            {"reason": payload.reason})
        data = {"document_id": str(row.id), "deleted_at": wire(row.deleted_at)}
    return success(data, request.state.request_id)
