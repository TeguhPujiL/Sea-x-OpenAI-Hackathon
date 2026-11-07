"""Back up the local SQLite database before installing this proposed feature."""
import argparse
from app.core.config import get_settings
from app.core.database import build_engine
from app.services.assurance.finding_scenarios.conclusions_migration import migrate

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url")
    args = parser.parse_args()
    engine = build_engine(args.database_url or get_settings().database_url)
    try:
        migrate(engine)
        print("Installed PROPOSED-v1.2 local procurement-conclusion migration.")
    finally:
        engine.dispose()
