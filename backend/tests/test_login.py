from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
import pytest

from app.core.config import Settings
from app.core.database import build_engine
from app.core.demo_bootstrap import bootstrap
from app.core.login import COOKIE, LoginSettings
from app.web import create_web_app

PASSWORD = "Test-password-42"


@pytest.fixture
def login_app(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'login.db'}"
    engine = build_engine(database_url)
    bootstrap(engine)
    engine.dispose()
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<html>Local test shell</html>")
    config = Settings(database_url=database_url, storage_root=tmp_path / "storage", demo_mode=True, demo_actor_id=uuid4(),
                      demo_scopes=frozenset({"case:read", "case:write", "document:read", "document:write", "document:delete"}))
    app = create_web_app(config, static, LoginSettings(_env_file=None, username="admin", password=SecretStr(PASSWORD)))
    with TestClient(app) as client:
        yield app, client


def sign_in(client, **changes):
    return client.post("/auth/login", json={"username": "admin", "password": PASSWORD, **changes})


def test_login_gate_cookies_and_logout(login_app):
    app, client = login_app
    assert client.get("/").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/auth/session").json()["data"]["authenticated"] is False
    blocked = client.get("/api/v1/cases")
    assert blocked.status_code == 401
    assert blocked.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert blocked.headers["X-Request-ID"] == blocked.json()["meta"]["request_id"]
    assert sign_in(client, password="wrong-password").status_code == 401
    response = sign_in(client)
    assert response.status_code == 200
    assert response.json()["data"] == {"authenticated": True, "username": "admin", "login_enabled": True}
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    token = client.cookies.get(COOKIE)
    assert token not in app.state.login_sessions.tokens
    assert client.get("/api/v1/cases").status_code == 200
    assert client.get("/auth/session").json()["data"]["authenticated"] is True
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/api/v1/cases").status_code == 401
    assert client.get("/api/v1/cases", headers={"Cookie": f"{COOKIE}={token}"}).status_code == 401


def test_login_does_not_accept_browser_actor_and_sessions_expire(login_app):
    app, client = login_app
    assert sign_in(client, actor_id=str(uuid4())).status_code == 400
    assert sign_in(client).status_code == 200
    for key in app.state.login_sessions.tokens:
        app.state.login_sessions.tokens[key] = 0
    assert client.get("/auth/session").json()["data"]["authenticated"] is False
    assert client.get("/api/v1/cases").status_code == 401


def test_login_csrf_rate_limit_and_invalid_session(login_app):
    _, client = login_app
    forbidden = client.post("/auth/login", json={"username": "admin", "password": PASSWORD}, headers={"Origin": "https://untrusted.invalid"})
    assert forbidden.status_code == 403
    for _ in range(5):
        assert sign_in(client, password="not-the-password").status_code == 401
    limited = sign_in(client)
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"
    assert client.get("/api/v1/cases", headers={"Cookie": f"{COOKIE}=made-up-session"}).status_code == 401


def test_login_rotation_and_protected_mutation_origin(login_app):
    app, client = login_app
    assert sign_in(client).status_code == 200
    old_token = client.cookies.get(COOKIE)
    assert sign_in(client).status_code == 200
    assert not app.state.login_sessions.valid(old_token)
    rejected = client.post("/api/v1/cases", headers={"Origin": "http://untrusted.invalid"}, json={})
    assert rejected.status_code == 403


def test_enabled_login_requires_credentials():
    with pytest.raises(ValidationError):
        LoginSettings(_env_file=None, password=None)


def test_login_case_history_upload_then_document_typing(login_app):
    import pymupdf
    _, client = login_app
    assert sign_in(client).status_code == 200
    cases = []
    for index in range(2):
        response = client.post("/api/v1/cases", headers={"Idempotency-Key": f"history-case-{index}"},
            json={"title": f"History fixture {index}", "category": "IT_EQUIPMENT", "quantity": 50, "budget_ceiling_idr": 900000000})
        assert response.status_code == 201
        cases.append(response.json()["data"])
    history = client.get("/api/v1/cases").json()["data"]["items"]
    assert {c["case_id"] for c in history} == {c["case_id"] for c in cases}
    case_id = cases[0]["case_id"]
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), "Synthetic requirement: minimum RAM 16 GB")
        payload = document.tobytes()
    documents = []
    for index in range(2):
        uploaded = client.post(f"/api/v1/cases/{case_id}/documents", headers={"Idempotency-Key": f"batch-{index}"},
            files={"file": (f"document-{index}.pdf", payload, "application/pdf")}, data={"document_type": "OTHER"})
        assert uploaded.status_code == 201, uploaded.text
        documents.append(uploaded.json()["data"])
    for document, kind in zip(documents, ("TOR", "TECHNICAL_SPECIFICATION")):
        response = client.patch(f"/api/v1/documents/{document['document_id']}", json={"document_type": kind, "expected_version": 1})
        assert response.status_code == 200
        assert response.json()["data"]["document_type"] == kind
        assert response.json()["data"]["version"] == 2
        stale = client.patch(f"/api/v1/documents/{document['document_id']}", json={"document_type": "OTHER", "expected_version": 1})
        assert stale.status_code == 409
    assert len(client.get(f"/api/v1/cases/{case_id}/documents").json()["data"]["items"]) == 2
    client.post("/auth/logout")
    assert client.get(f"/api/v1/cases/{case_id}").status_code == 401
    assert sign_in(client).status_code == 200
    assert client.get(f"/api/v1/cases/{case_id}").json()["data"]["case_id"] == case_id


def test_remove_uploaded_document_preserves_file_and_history(login_app):
    import pymupdf
    from sqlalchemy.orm import Session
    from app.models import Document
    from uuid import UUID
    app, client = login_app
    assert sign_in(client).status_code == 200
    created = client.post('/api/v1/cases', headers={'Idempotency-Key': 'delete-case'}, json={
        'title': 'Wrong upload test', 'category': 'OTHER', 'quantity': 1, 'budget_ceiling_idr': 0})
    cid = created.json()['data']['case_id']
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72,72), 'Synthetic wrong document')
        payload = pdf.tobytes()
    uploaded = client.post(f'/api/v1/cases/{cid}/documents', headers={'Idempotency-Key': 'delete-upload'},
        files={'file': ('wrong.pdf', payload, 'application/pdf')}, data={'document_type': 'OTHER'})
    assert uploaded.status_code == 201
    did = uploaded.json()['data']['document_id']
    assert client.request('DELETE', f'/api/v1/documents/{did}', json={'reason': 'Wrong file', 'expected_version': 2}).status_code == 409
    removed = client.request('DELETE', f'/api/v1/documents/{did}', json={'reason': 'Wrong file', 'expected_version': 1})
    assert removed.status_code == 200
    assert removed.json()['data']['deleted_at'].endswith('Z')
    assert client.get(f'/api/v1/cases/{cid}/documents').json()['data']['items'] == []
    assert client.get(f'/api/v1/documents/{did}').status_code == 404
    with app.state.session_factory() as db:
        row = db.get(Document, UUID(did))
        assert row.deleted_at is not None
        assert (app.state.settings.storage_root / row.storage_key).read_bytes() == payload
