"""Explicit, checksum-verified SQLite migrations; never called on app startup.

Usage: python -m app.services.assurance.migrate [--database-url sqlite:///...]
Existing unversioned tables require an explicit, reviewed adoption migration.
"""
import argparse
import hashlib
from pathlib import Path
import sqlite3

from sqlalchemy import inspect

from app.core.config import get_settings
from app.core.database import build_engine

MIGRATIONS = Path(__file__).with_name("migrations")


def statements(script: str):
    current = ""
    for line in script.splitlines(keepends=True):
        current += line
        if sqlite3.complete_statement(current):
            yield current
            current = ""
    if current.strip():
        raise ValueError("Incomplete migration statement")


def migrate(engine) -> list[str]:
    if engine.dialect.name != "sqlite":
        raise ValueError("Only SQLite migration dialect is implemented")
    files = sorted(MIGRATIONS.glob("[0-9]*.sql"))
    if not files:
        raise RuntimeError("Migration resources are missing")
    applied = []
    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            tables = set(inspect(conn).get_table_names())
            if tables and "assurance_schema_revisions" not in tables:
                raise RuntimeError("Unversioned database: back up and obtain a reviewed adoption migration")
            conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS assurance_schema_revisions "
                "(revision TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TEXT NOT NULL)")
            known = dict(conn.exec_driver_sql("SELECT revision, sha256 FROM assurance_schema_revisions").all())
            if set(known) - {f.stem for f in files}:
                raise RuntimeError("Database contains unknown migration revisions")
            for file in files:
                # Text-mode reading normalizes CRLF/LF. Git checkout settings
                # must not make an unchanged revision fail on another host.
                source = file.read_text(encoding="utf-8")
                digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
                if file.stem in known:
                    if known[file.stem] != digest:
                        raise RuntimeError(f"Migration checksum mismatch: {file.stem}")
                    continue
                for sql in statements(source):
                    conn.exec_driver_sql(sql)
                conn.exec_driver_sql("INSERT INTO assurance_schema_revisions VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                                     (file.stem, digest))
                applied.append(file.stem)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    return applied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=get_settings().database_url)
    args = parser.parse_args()
    engine = build_engine(args.database_url)
    try:
        print({"applied": migrate(engine)})
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
