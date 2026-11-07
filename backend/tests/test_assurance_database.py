from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import build_engine
from app.models import Base, Case
from app.services.assurance import migrate as migrations
from conftest import post_review, seed_chain


def test_migrations_match_metadata_are_repeatable_and_enable_foreign_keys(qa):
    assert migrations.migrate(qa.engine) == []
    with qa.engine.connect() as conn:
        inspector = inspect(conn)
        assert conn.scalar(text("PRAGMA foreign_keys")) == 1
        assert conn.scalar(text("PRAGMA foreign_key_check")) is None
        assert conn.scalar(text("PRAGMA integrity_check")) == "ok"
        for name, table in Base.metadata.tables.items():
            assert {c["name"] for c in inspector.get_columns(name)} == set(table.columns.keys())
            assert len(inspector.get_foreign_keys(name)) == len(table.foreign_keys)
        revisions = conn.execute(text("SELECT revision FROM assurance_schema_revisions ORDER BY revision")).scalars().all()
        assert revisions == ["0001_foundation", "0002_assurance_guards"]


@pytest.mark.parametrize("sql", [
    "UPDATE cases SET version=0", "UPDATE cases SET version=1.5",
    "UPDATE cases SET case_status='APPROVE_CASE'", "UPDATE cases SET assurance_status='INVALID'",
    "UPDATE cases SET budget_ceiling_idr=-1", "UPDATE documents SET page_count=0",
    "UPDATE documents SET page_count=0.5", "UPDATE document_pages SET page_number=0",
    "UPDATE documents SET page_count=1.5", "UPDATE cases SET quantity=1.5",
    "UPDATE document_pages SET page_number=2", "UPDATE evidence_refs SET page_number=2",
    "UPDATE evidence_refs SET page_number=1.5", "UPDATE findings SET status='INVALID'",
    "UPDATE findings SET evidence_status='INVALID'", "UPDATE findings SET confidence=2",
    "UPDATE repair_proposals SET proposed_text='changed'", "DELETE FROM repair_proposals",
])
def test_database_check_constraints_and_submission_freeze(qa, sql):
    with qa.engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql(sql)


def test_foreign_keys_unique_page_numbers_and_cross_case_refs(qa):
    with Session(qa.engine, expire_on_commit=False) as session:
        other = seed_chain(session, suffix="foreign")
    with qa.engine.begin() as conn:
        for sql, params in [
            ("UPDATE evidence_refs SET document_id=?", (uuid4().hex,)),
            ("UPDATE evidence_refs SET document_id=?", (other.docs[0].id.hex,)),
            ("UPDATE findings SET analysis_job_id=? WHERE id=?", (other.job.id.hex, qa.chain.finding.id.hex)),
            ("INSERT INTO document_pages (id,document_id,page_number,normalized_text) VALUES (?,?,1,'test')", (uuid4().hex, qa.chain.docs[0].id.hex)),
        ]:
            with pytest.raises(IntegrityError):
                conn.exec_driver_sql(sql, params)


def test_idempotency_unique_scope_and_integrity_guards(qa):
    assert post_review(qa).status_code == 201
    with qa.engine.begin() as conn:
        for sql in [
            "INSERT INTO idempotency_records (id,created_at,actor_id,method,route,key,request_hash,response_status,response_body) SELECT '00000000000040008000000000000000',created_at,actor_id,method,route,key,request_hash,response_status,response_body FROM idempotency_records",
            "UPDATE idempotency_records SET request_hash='invalid'",
            "UPDATE idempotency_records SET key=''",
            "UPDATE idempotency_records SET route='/wrong'",
            "UPDATE idempotency_records SET response_status=500",
        ]:
            with pytest.raises(IntegrityError):
                conn.exec_driver_sql(sql)


def test_case_number_uniqueness_and_independent_key_scopes(qa):
    with Session(qa.engine) as session:
        session.add(Case(case_number=qa.chain.case.case_number, title="duplicate", category="TEST",
                         quantity=1, budget_ceiling_idr=0))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
    assert post_review(qa).status_code == 201
    with qa.engine.begin() as conn:
        # Key text may repeat for a different actor or canonical route.
        conn.exec_driver_sql("INSERT INTO idempotency_records (id,created_at,actor_id,method,route,key,request_hash,response_status,response_body) SELECT ?,created_at,?,method,route,key,request_hash,response_status,response_body FROM idempotency_records LIMIT 1", (uuid4().hex, uuid4().hex))
        conn.exec_driver_sql("INSERT INTO idempotency_records (id,created_at,actor_id,method,route,key,request_hash,response_status,response_body) SELECT ?,created_at,actor_id,method,'/api/v1/cases/other/reviews',key,request_hash,response_status,response_body FROM idempotency_records LIMIT 1", (uuid4().hex,))


@pytest.mark.parametrize("table", ["ai_executions", "simulations", "reviews", "audit_events"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_migrated_immutable_tables_block_direct_sql(qa, table, operation):
    assert post_review(qa).status_code == 201
    with qa.engine.begin() as conn:
        statement = f"UPDATE {table} SET id=id" if operation == "UPDATE" else f"DELETE FROM {table}"
        with pytest.raises(IntegrityError, match="immutable"):
            conn.exec_driver_sql(statement)


def test_reviewed_case_and_evidence_document_cannot_be_deleted(qa):
    assert post_review(qa).status_code == 201
    with qa.engine.begin() as conn:
        for table in ("cases", "documents"):
            with pytest.raises(IntegrityError):
                conn.exec_driver_sql(f"UPDATE {table} SET deleted_at=CURRENT_TIMESTAMP")


def test_no_new_reference_to_deleted_case_or_document(qa):
    with qa.engine.begin() as conn:
        conn.exec_driver_sql("UPDATE documents SET deleted_at=CURRENT_TIMESTAMP")
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql("INSERT INTO document_pages (id,document_id,page_number,normalized_text) VALUES (?,?,1,'test')", (uuid4().hex, qa.chain.docs[0].id.hex))
        conn.exec_driver_sql("UPDATE cases SET deleted_at=CURRENT_TIMESTAMP")
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql("INSERT INTO analysis_jobs (id,created_at,case_id,analysis_types,processing_status,progress_percent,warnings_json) VALUES (?,CURRENT_TIMESTAMP,?,'[]','QUEUED',0,'[]')", (uuid4().hex, qa.chain.case.id.hex))


def test_unversioned_database_is_refused_without_modification(tmp_path):
    engine = build_engine("sqlite:///" + (tmp_path / "old.db").as_posix())
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE existing (value TEXT)")
            conn.exec_driver_sql("INSERT INTO existing VALUES ('preserved')")
        with pytest.raises(RuntimeError, match="Unversioned"):
            migrations.migrate(engine)
        with engine.connect() as conn:
            assert inspect(conn).get_table_names() == ["existing"]
            assert conn.exec_driver_sql("SELECT value FROM existing").scalar() == "preserved"
    finally:
        engine.dispose()


def test_migration_checksum_mismatch_and_bad_sql_roll_back(tmp_path, monkeypatch):
    folder = tmp_path / "revisions"
    folder.mkdir()
    revision = folder / "0001_test.sql"
    revision.write_text("CREATE TABLE test_revision (value TEXT);\nINVALID SQL;\n")
    monkeypatch.setattr(migrations, "MIGRATIONS", folder)
    engine = build_engine("sqlite:///" + (tmp_path / "migration.db").as_posix())
    try:
        with pytest.raises(Exception):
            migrations.migrate(engine)
        with engine.connect() as conn:
            assert inspect(conn).get_table_names() == []
        revision.write_text("CREATE TABLE test_revision (value TEXT);\n")
        assert migrations.migrate(engine) == ["0001_test"]
        revision.write_text("CREATE TABLE test_revision (value INTEGER);\n")
        with pytest.raises(RuntimeError, match="checksum"):
            migrations.migrate(engine)
    finally:
        engine.dispose()
