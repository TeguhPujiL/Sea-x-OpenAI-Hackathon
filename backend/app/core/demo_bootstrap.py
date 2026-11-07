"""Compose existing owner migrations for a dedicated demo database only."""
from sqlalchemy import inspect
from app.core.config import get_settings
from app.core.database import build_engine
from app.core.migrations import migrate as migrate_core
from app.services.assurance.migrate import migrate as migrate_assurance, statements, MIGRATIONS
from app.services.simulation.migrate import install_simulation_guards


def bootstrap(engine):
    with engine.connect() as connection:
        tables=set(inspect(connection).get_table_names())
    if not tables or "assurance_schema_revisions" in tables:
        migrate_assurance(engine)
    else:
        raise RuntimeError("Demo bootstrap refuses to adopt an unversioned existing DB; use a new dedicated demo database")
    migrate_core(engine)
    # Core may rebuild the legacy AI table. Restore only missing original owner
    # guards from the checksum-verified assurance revision; never change its SQL.
    with engine.begin() as connection:
        for sql in statements((MIGRATIONS/'0002_assurance_guards.sql').read_text(encoding='utf-8')):
            import re
            match=re.search(r'CREATE\s+(?:UNIQUE\s+)?(TRIGGER|INDEX)\s+(\w+)',sql,re.I)
            if match:
                kind,name=match.group(1).lower(),match.group(2)
                exists=connection.exec_driver_sql('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',(kind,name)).first()
                if not exists: connection.exec_driver_sql(sql)
    install_simulation_guards(engine)


def main():
    engine=build_engine(get_settings().database_url)
    try: bootstrap(engine)
    finally: engine.dispose()


if __name__=='__main__': main()
