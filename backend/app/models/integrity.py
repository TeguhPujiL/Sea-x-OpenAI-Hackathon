"""Teguh resource integrity guards, installed by the explicit migration runner."""
from sqlalchemy import DDL, event, inspect
from sqlalchemy.orm import Session
from app.models.tables import AnalysisJob, DocumentPage, Document, Finding, EvidenceRef


TERMINAL = {"COMPLETED", "NEEDS_REVIEW", "FAILED"}
TRANSITIONS = {"QUEUED": {"PROCESSING", "FAILED"}, "PROCESSING": TERMINAL}


@event.listens_for(Session, "before_flush")
def resource_integrity(session, _context, _instances):
    for obj in session.deleted:
        if isinstance(obj, (AnalysisJob, DocumentPage, Finding, EvidenceRef)):
            raise ValueError("Execution and evidence records cannot be deleted")
    for obj in session.dirty:
        if not session.is_modified(obj):
            continue
        state = inspect(obj)
        if isinstance(obj, (DocumentPage, EvidenceRef)):
            raise ValueError("Stored evidence text and references are immutable")
        if isinstance(obj, Document):
            for field in ("case_id", "storage_key", "sha256", "page_count", "size_bytes", "filename", "mime_type"):
                if state.attrs[field].history.has_changes():
                    raise ValueError("PDF content identity is immutable")
        if isinstance(obj, Finding):
            for field in ("case_id", "analysis_job_id", "ai_execution_id", "type", "severity", "title", "summary", "confidence", "evidence_status"):
                if state.attrs[field].history.has_changes():
                    raise ValueError("AI finding provenance is immutable")
        if isinstance(obj, AnalysisJob):
            history = state.attrs.processing_status.history
            previous = history.deleted[0] if history.deleted else obj.processing_status
            previous = getattr(previous, "value", previous)
            current = getattr(obj.processing_status, "value", obj.processing_status)
            if previous in TERMINAL:
                raise ValueError("Terminal jobs are immutable")
            if current != previous and current not in TRANSITIONS.get(previous, set()):
                raise ValueError("Invalid job transition")


JOB_TRIGGERS = [
    "CREATE TRIGGER IF NOT EXISTS job_no_delete BEFORE DELETE ON analysis_jobs BEGIN SELECT RAISE(ABORT, 'job immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS job_terminal BEFORE UPDATE ON analysis_jobs WHEN OLD.processing_status IN ('COMPLETED','FAILED','NEEDS_REVIEW') BEGIN SELECT RAISE(ABORT, 'terminal job immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS job_transition BEFORE UPDATE ON analysis_jobs WHEN NEW.processing_status != OLD.processing_status AND NOT ((OLD.processing_status='QUEUED' AND NEW.processing_status IN ('PROCESSING','FAILED')) OR (OLD.processing_status='PROCESSING' AND NEW.processing_status IN ('COMPLETED','FAILED','NEEDS_REVIEW'))) BEGIN SELECT RAISE(ABORT, 'invalid job transition'); END",
]
# Installation is explicit so existing databases receive the same guards.
def install_guards(connection):
    for sql in JOB_TRIGGERS:
        connection.exec_driver_sql(sql)
    for table, fields in {
        "documents": ("id", "case_id", "storage_key", "sha256", "page_count", "size_bytes", "filename", "mime_type", "uploaded_at"),
        "findings": ("id", "case_id", "analysis_job_id", "ai_execution_id", "type", "severity", "title", "summary", "confidence", "evidence_status", "created_at"),
    }.items():
        condition = " OR ".join(f"NEW.{field} IS NOT OLD.{field}" for field in fields)
        connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_provenance BEFORE UPDATE ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT, 'provenance immutable'); END")
    connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS job_outcome BEFORE UPDATE ON analysis_jobs WHEN ((NEW.processing_status IN ('COMPLETED','NEEDS_REVIEW') AND COALESCE(json_type(NEW.result_json),'null')='null') OR (NEW.processing_status IN ('QUEUED','PROCESSING','FAILED') AND COALESCE(json_type(NEW.result_json),'null')!='null')) BEGIN SELECT RAISE(ABORT, 'invalid job result'); END")
    for table in ("document_pages", "evidence_refs"):
        for operation in ("UPDATE", "DELETE"):
            connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'evidence immutable'); END")
