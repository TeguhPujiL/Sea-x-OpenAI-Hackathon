from sqlalchemy import select
from app.models import AiExecution, EvidenceRef
from app.core.transactions import wire


def fields(row, names):
    return {name: wire(getattr(row, name)) for name in names.split()}


def case_data(row):
    return {"case_id": str(row.id), **fields(row, "case_number title category description quantity budget_ceiling_idr currency case_status assurance_status version created_at updated_at deleted_at")}


def document_data(row):
    return {"document_id": str(row.id), **fields(row, "case_id filename document_type description mime_type size_bytes sha256 page_count processing_status version uploaded_at deleted_at")}


def execution_data(row):
    if row is None:
        return None
    return {"execution_id": str(row.id), **fields(row, "provider model operation prompt_version schema_valid evidence_validation_passed latency_ms"),
        "input_document_ids": row.input_document_ids_json, "evidence_checks": row.evidence_checks_json, "usage": row.usage_json}


def job_data(db, row):
    execution = db.scalar(select(AiExecution).where(AiExecution.job_id == row.id).order_by(AiExecution.created_at.desc()))
    data = {"job_id": str(row.id), "case_id": str(row.case_id), "job_type": "DOCUMENT_ANALYSIS",
        "status": wire(row.processing_status), "progress_percent": row.progress_percent,
        "ai_execution": execution_data(execution), "result": row.result_json,
        "warnings": row.warnings_json, "error": row.error_json,
        **fields(row, "created_at started_at completed_at")}
    if row.retry_of_job_id:
        data["retry_of_job_id"] = str(row.retry_of_job_id)
    return data


def finding_data(db, row):
    evidence = db.scalars(select(EvidenceRef).where(EvidenceRef.finding_id == row.id).order_by(EvidenceRef.document_id, EvidenceRef.page_number)).all()
    return {"finding_id": str(row.id), **fields(row, "case_id analysis_job_id ai_execution_id type severity status title summary confidence evidence_status assignee_id resolution_note version created_at updated_at"),
        "evidence": [fields(ref, "document_id page_number excerpt verification_status") for ref in evidence]}


def page(items, total, limit, offset):
    return {"items": items, "pagination": {"limit": limit, "offset": offset, "total": total}}


# JSONResponse bypasses FastAPI response validation. Validate these central
# presenters explicitly while preserving the optional retry_of_job_id wire shape.
def validated(function, schema):
    def present(*args):
        data = function(*args)
        schema.model_validate(data)
        return data
    return present


from app.schemas.p0 import CaseView, DocumentView, JobView, FindingView
case_data = validated(case_data, CaseView)
document_data = validated(document_data, DocumentView)
job_data = validated(job_data, JobView)
finding_data = validated(finding_data, FindingView)
