"""Explicit opt-in experimental finding-scenario SQLite migration.

Back up the local database first. Core/assurance migrations must already exist.
No app startup code invokes this migration.
"""
import argparse

from app.core.config import get_settings
from app.core.database import build_engine
from app.services.assurance.finding_scenarios.migration import migrate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Dedicated local SQLite URL; defaults to backend configuration")
    args = parser.parse_args()
    engine = build_engine(args.database_url or get_settings().database_url)
    try:
        migrate(engine)
        print("Installed explicit PROPOSED-v1.2 experimental finding-scenario migration.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
