"""Explicit feature-local SQLite migration; no startup DDL."""
from hashlib import sha256
from sqlalchemy import inspect
from sqlalchemy.schema import CreateTable
from app.models.base import now
from .conclusions import ProcurementConclusion

GUARDS = (
    "CREATE TRIGGER IF NOT EXISTS procurement_conclusions_no_update BEFORE UPDATE ON procurement_conclusions BEGIN SELECT RAISE(ABORT,'procurement conclusion immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS procurement_conclusions_no_delete BEFORE DELETE ON procurement_conclusions BEGIN SELECT RAISE(ABORT,'procurement conclusion immutable'); END",
    """CREATE TRIGGER IF NOT EXISTS procurement_conclusions_sources BEFORE INSERT ON procurement_conclusions
    WHEN NOT EXISTS (SELECT 1 FROM cases c JOIN analysis_jobs j ON j.case_id=c.id
      WHERE c.id=NEW.case_id AND j.id=NEW.analysis_job_id AND c.deleted_at IS NULL
      AND c.version=NEW.source_case_version AND c.case_status NOT IN ('ARCHIVED','REVIEW_COMPLETED')
      AND j.processing_status IN ('COMPLETED','NEEDS_REVIEW'))
    BEGIN SELECT RAISE(ABORT,'invalid procurement conclusion sources'); END""",
)
TRIGGER_NAMES = {"procurement_conclusions_no_update", "procurement_conclusions_no_delete", "procurement_conclusions_sources"}

def checksum(connection):
    return sha256((str(CreateTable(ProcurementConclusion.__table__).compile(connection)) + "\n" + "\n".join(GUARDS)).encode()).hexdigest()

def migrate(engine):
    if engine.dialect.name != "sqlite":
        raise RuntimeError("Local procurement-conclusion migration supports SQLite only")
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar() != 1:
            raise RuntimeError("SQLite foreign keys must be enabled")
        if not {"cases", "analysis_jobs", "audit_events", "idempotency_records"}.issubset(inspect(connection).get_table_names()):
            raise RuntimeError("Install the reviewed core/assurance migrations first")
        connection.exec_driver_sql("CREATE TABLE IF NOT EXISTS procurement_conclusion_schema_versions (version INTEGER PRIMARY KEY CHECK(version=1), checksum TEXT NOT NULL, applied_at TEXT NOT NULL)")
        previous = connection.exec_driver_sql("SELECT checksum FROM procurement_conclusion_schema_versions WHERE version=1").scalar()
        digest = checksum(connection)
        exists = inspect(connection).has_table("procurement_conclusions")
        if previous is not None and previous != digest or (previous is None and exists) or (previous is not None and not exists):
            raise RuntimeError("Procurement-conclusion migration checksum/table mismatch")
        ProcurementConclusion.__table__.create(connection, checkfirst=True)
        for guard in GUARDS:
            connection.exec_driver_sql(guard)
        if previous is None:
            connection.exec_driver_sql("INSERT INTO procurement_conclusion_schema_versions VALUES(1,?,?)", (digest, now().isoformat().replace("+00:00", "Z")))
        if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("Foreign-key validation failed")
