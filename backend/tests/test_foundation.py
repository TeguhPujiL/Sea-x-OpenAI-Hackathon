from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.core.database import build_engine
from app.main import create_app
from app.schemas.shared import StrictModel, utc_z


def test_startup_health_openapi_and_errors():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert set(response.json()) == {"success", "data", "error", "meta"}
        assert client.get("/openapi.json").status_code == 200
        missing = client.get("/api/v1/missing")
        assert missing.status_code == 404
        assert missing.json()["success"] is False


def test_shared_input_is_closed_and_requires_aware_time():
    with pytest.raises(ValidationError):
        StrictModel(unknown="value")
    with pytest.raises(ValueError):
        utc_z(datetime(2026, 1, 1))


def test_sqlite_foreign_keys_enabled():
    engine = build_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
    finally:
        engine.dispose()
