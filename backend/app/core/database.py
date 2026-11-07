from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def build_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite:") else {})
    if url.startswith("sqlite:"):
        @event.listens_for(engine, "connect")
        def sqlite_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    # Feature dependencies must use transaction boundaries owned by their service.
    with request.app.state.session_factory() as session:
        yield session
