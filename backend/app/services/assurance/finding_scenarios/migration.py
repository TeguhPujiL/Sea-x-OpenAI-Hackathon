"""Explicit feature-local SQLite migration; never invoked at app startup."""
from hashlib import sha256

from sqlalchemy import inspect
from sqlalchemy.schema import CreateTable

from app.models.base import now
from .models import FindingScenario


GUARDS = (
    "CREATE TRIGGER IF NOT EXISTS finding_scenarios_no_update BEFORE UPDATE ON finding_scenarios BEGIN SELECT RAISE(ABORT, 'finding scenario immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS finding_scenarios_no_delete BEFORE DELETE ON finding_scenarios BEGIN SELECT RAISE(ABORT, 'finding scenario immutable'); END",
    """CREATE TRIGGER IF NOT EXISTS finding_scenarios_sources BEFORE INSERT ON finding_scenarios
    WHEN NOT EXISTS (SELECT 1 FROM cases c JOIN findings f ON f.case_id=c.id
      JOIN analysis_jobs j ON j.id=f.analysis_job_id AND j.case_id=c.id
      JOIN ai_executions a ON a.id=NEW.ai_execution_id AND a.case_id=c.id
      WHERE c.id=NEW.case_id AND f.id=NEW.finding_id AND j.id=NEW.analysis_job_id
        AND c.deleted_at IS NULL AND c.case_status NOT IN ('ARCHIVED','REVIEW_COMPLETED')
        AND f.status IN ('OPEN','UNDER_REVIEW') AND c.version=NEW.source_case_version AND f.version=NEW.source_finding_version)
      OR NOT EXISTS (SELECT 1 FROM challenges ch WHERE ch.case_id=NEW.case_id AND ch.finding_id=NEW.finding_id
        AND ch.deleted_at IS NULL AND ch.status IN ('DRAFT','READY'))
    BEGIN SELECT RAISE(ABORT, 'invalid finding scenario sources'); END""",
    """CREATE TRIGGER IF NOT EXISTS finding_scenarios_citation_sources BEFORE INSERT ON finding_scenarios
    WHEN COALESCE(json_type(NEW.payload_json,'$.baseline.evidence'),'null')!='array'
      OR json_array_length(NEW.payload_json,'$.baseline.evidence') < 1
      OR EXISTS (SELECT 1 FROM (
        SELECT value AS ref FROM json_each(NEW.payload_json,'$.baseline.evidence')
        UNION ALL SELECT citation.value AS ref FROM json_each(NEW.payload_json,'$.alternatives') alternative,
          json_each(alternative.value,'$.evidence') citation
      ) r LEFT JOIN documents d ON d.id=lower(replace(json_extract(r.ref,'$.document_id'),'-',''))
        LEFT JOIN document_pages p ON p.document_id=d.id AND p.page_number=json_extract(r.ref,'$.page_number')
      WHERE d.id IS NULL OR d.deleted_at IS NOT NULL OR d.case_id!=NEW.case_id OR d.processing_status!='COMPLETED'
        OR p.id IS NULL OR json_type(r.ref,'$.page_number')!='integer'
        OR json_extract(r.ref,'$.page_number') < 1 OR json_extract(r.ref,'$.page_number') > d.page_count
        OR NOT EXISTS (SELECT 1 FROM analysis_jobs j, json_each(j.input_document_ids_json) source_item
          WHERE j.id=NEW.analysis_job_id AND lower(replace(source_item.value,'-',''))=d.id))
    BEGIN SELECT RAISE(ABORT, 'invalid finding scenario citation sources'); END""",
)

REQUIRED_TRIGGERS = {"finding_scenarios_no_update", "finding_scenarios_no_delete", "finding_scenarios_sources", "finding_scenarios_citation_sources"}


def migration_checksum(connection):
    return sha256((str(CreateTable(FindingScenario.__table__).compile(connection)) + "\n" + "\n".join(GUARDS)).encode()).hexdigest()


def migrate(engine):
    if engine.dialect.name != "sqlite":
        raise RuntimeError("Finding scenario migration supports SQLite only")
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar() != 1:
            raise RuntimeError("SQLite foreign keys must be enabled")
        required = {"cases", "case_access", "findings", "challenges", "documents", "document_pages", "evidence_refs",
            "analysis_jobs", "ai_executions", "generation_leases", "idempotency_records", "audit_events"}
        if not required.issubset(inspect(connection).get_table_names()):
            raise RuntimeError("Install the reviewed core/assurance migrations before this experiment")
        digest = migration_checksum(connection)
        connection.exec_driver_sql("CREATE TABLE IF NOT EXISTS finding_scenario_schema_versions (version INTEGER PRIMARY KEY CHECK(version=1), checksum TEXT NOT NULL, applied_at TEXT NOT NULL)")
        previous = connection.exec_driver_sql("SELECT checksum FROM finding_scenario_schema_versions WHERE version=1").scalar()
        if previous is not None and previous != digest:
            raise RuntimeError("Experimental finding scenario migration checksum mismatch")
        exists = inspect(connection).has_table("finding_scenarios")
        if (previous is None and exists) or (previous is not None and not exists):
            raise RuntimeError("Refusing to adopt an unversioned table or silently recreate a missing versioned scenario table")
        FindingScenario.__table__.create(connection, checkfirst=True)
        for guard in GUARDS:
            connection.exec_driver_sql(guard)
        if previous is None:
            connection.exec_driver_sql("INSERT INTO finding_scenario_schema_versions(version,checksum,applied_at) VALUES (1,?,?)", (digest, now().isoformat().replace("+00:00", "Z")))
        if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("Foreign-key validation failed")
