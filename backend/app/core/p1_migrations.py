"""Explicit additive P1.1 SQLite migration. Never runs at application startup."""
from sqlalchemy import inspect
from app.models.p1 import P1Base


def migrate(engine):
    if engine.dialect.name != "sqlite":
        raise RuntimeError("P1 migration supports SQLite only")
    with engine.begin() as connection:
        # SQLite legacy transaction mode otherwise auto-commits DDL before the
        # first DML statement, leaving partial schema behind after a failure.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        if connection.exec_driver_sql("PRAGMA user_version").scalar() != 2:
            raise RuntimeError("Apply the existing P0 migration 0002 first")
        if "case_access" not in inspect(connection).get_table_names():
            raise RuntimeError("P0 case access schema is required")
        P1Base.metadata.create_all(connection)
        connection.exec_driver_sql("INSERT OR IGNORE INTO p1_schema_revisions(revision) VALUES ('p1.1-0001')")
        for table in ("p1_checks", "p1_check_results", "p1_schema_revisions"):
            for operation in ("UPDATE", "DELETE"):
                connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable P1 record'); END")
        connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS p1_check_case BEFORE INSERT ON p1_checks WHEN NOT EXISTS (SELECT 1 FROM analysis_jobs j WHERE j.id=NEW.job_id AND j.case_id=NEW.case_id) OR (NEW.previous_check_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM p1_checks p WHERE p.id=NEW.previous_check_id AND p.case_id=NEW.case_id AND p.kind=NEW.kind AND p.supplier_ref IS NEW.supplier_ref AND NEW.version=p.version+1)) BEGIN SELECT RAISE(ABORT, 'P1 provenance mismatch'); END")
        connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS p1_result_case BEFORE INSERT ON p1_check_results WHEN NOT EXISTS (SELECT 1 FROM p1_checks c JOIN ai_executions e ON e.id=NEW.ai_execution_id WHERE c.id=NEW.check_id AND e.job_id=c.job_id AND e.case_id=c.case_id) BEGIN SELECT RAISE(ABORT, 'P1 execution mismatch'); END")
        if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
            raise RuntimeError("P1 foreign key validation failed")


if __name__ == "__main__":
    from app.core.config import get_settings
    from app.core.database import build_engine
    engine = build_engine(get_settings().database_url)
    try:
        migrate(engine)
    finally:
        engine.dispose()
