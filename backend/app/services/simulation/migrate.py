"""Explicit SQLite simulation guard migration; never creates shared tables."""
from sqlalchemy import text


def install_simulation_guards(engine):
    if engine.dialect.name != "sqlite":
        raise ValueError("This guard migration supports SQLite only")
    with engine.begin() as connection:
        for operation in ("UPDATE", "DELETE"):
            connection.execute(text(
                f"CREATE TRIGGER IF NOT EXISTS protect_simulations_{operation.lower()} "
                f"BEFORE {operation} ON simulations BEGIN "
                "SELECT RAISE(ABORT, 'immutable simulation record'); END"
            ))
        connection.execute(text("""
            CREATE TRIGGER IF NOT EXISTS protect_simulations_replace
            BEFORE INSERT ON simulations
            WHEN EXISTS (SELECT 1 FROM simulations WHERE id=NEW.id OR rowid=NEW.rowid)
            BEGIN SELECT RAISE(ABORT, 'immutable simulation record'); END
        """))


if __name__ == "__main__":
    import argparse

    from app.core.database import build_engine

    parser = argparse.ArgumentParser(description="Install immutable simulation guards on existing SQLite tables")
    parser.add_argument("--database-url", required=True)
    engine = build_engine(parser.parse_args().database_url)
    try:
        install_simulation_guards(engine)
    finally:
        engine.dispose()
