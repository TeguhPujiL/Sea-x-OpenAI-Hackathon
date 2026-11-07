"""Explicit SQLite migrations 0001/0002: foundation -> Teguh P0 decisions.

Back up the SQLite file before running. Migration preserves existing rows and
fails if referential integrity is already broken. It never invents actor/input
provenance for legacy jobs; those require a reviewed operator backfill.
"""
from sqlalchemy import inspect
from sqlalchemy.schema import CreateTable
from app.core.config import get_settings
from app.core.database import build_engine
from app.models import Base, AiExecution
from app.models.integrity import install_guards
from app.models.decisions import install_decision_guards


def migrate(engine):
    if engine.dialect.name != "sqlite":
        raise RuntimeError("This migration is for SQLite only")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            if connection.exec_driver_sql("PRAGMA user_version").scalar() > 2:
                raise RuntimeError("Database is newer than this migration runner")
            inspector = inspect(connection)
            tables = inspector.get_table_names()
            if "ai_executions" in tables:
                columns = inspector.get_columns("ai_executions")
                if not next(c for c in columns if c["name"] == "model")["nullable"]:
                    ddl = str(CreateTable(AiExecution.__table__).compile(connection)).replace(
                        "CREATE TABLE ai_executions", "CREATE TABLE ai_executions_p0_migration", 1)
                    connection.exec_driver_sql(ddl)
                    names = [c["name"] for c in columns if c["name"] in AiExecution.__table__.columns]
                    quoted = ", ".join('"'+n+'"' for n in names)
                    connection.exec_driver_sql(f"INSERT INTO ai_executions_p0_migration ({quoted}) SELECT {quoted} FROM ai_executions")
                    connection.exec_driver_sql("DROP TABLE ai_executions")
                    connection.exec_driver_sql("ALTER TABLE ai_executions_p0_migration RENAME TO ai_executions")
                elif "requested_model" not in {c["name"] for c in columns}:
                    connection.exec_driver_sql("ALTER TABLE ai_executions ADD COLUMN requested_model VARCHAR")
            if "analysis_jobs" in tables:
                existing = {c["name"] for c in inspect(connection).get_columns("analysis_jobs")}
                additions = {"input_document_ids_json": "JSON NOT NULL DEFAULT '[]'", "requirements_json": "JSON", "actor_id": "CHAR(32)", "request_id": "VARCHAR"}
                for name, sql_type in additions.items():
                    if name not in existing:
                        connection.exec_driver_sql(f"ALTER TABLE analysis_jobs ADD COLUMN {name} {sql_type}")
            if "idempotency_records" in tables:
                fields = {c["name"] for c in inspect(connection).get_columns("idempotency_records")}
                if "response_headers" not in fields:
                    connection.exec_driver_sql("ALTER TABLE idempotency_records ADD COLUMN response_headers JSON NOT NULL DEFAULT '{}'")
            Base.metadata.create_all(connection)
            install_guards(connection)
            install_decision_guards(connection)
            for name in ("ai_executions", "simulations", "reviews", "audit_events"):
                for operation in ("UPDATE", "DELETE"):
                    connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS protect_{name}_{operation.lower()} BEFORE {operation} ON {name} BEGIN SELECT RAISE(ABORT, 'immutable record'); END")
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                raise RuntimeError("Foreign key validation failed; migration rolled back")
            connection.exec_driver_sql("PRAGMA user_version=2")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


def main():
    engine = build_engine(get_settings().database_url)
    try:
        migrate(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
