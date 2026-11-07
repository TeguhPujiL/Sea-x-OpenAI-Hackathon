"""Explicit empty demo database initializer; never called at app startup.

This is a bootstrap, not a migration runner. Existing tables require reviewed
migrations; running create_all will not migrate existing schemas.
"""
from app.core.config import get_settings
from app.core.database import build_engine
from app.models import Base


def main():
    engine = build_engine(get_settings().database_url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
