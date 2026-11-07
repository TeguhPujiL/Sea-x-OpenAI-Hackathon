import json
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
import pytest

from scripts.positive_case_bot import inventory, PositiveCaseBot


def dataset(tmp_path):
    for name in ("01_Terms_of_Reference.pdf", "02_Technical_Specification.pdf"):
        with pymupdf.open() as doc:
            doc.new_page().insert_text((72, 72), "Synthetic test PDF only")
            (tmp_path / name).write_bytes(doc.tobytes())
    (tmp_path / "manifest_pdf.txt").write_text("01_Terms_of_Reference.pdf\n02_Technical_Specification.pdf\n")
    return tmp_path


def test_inventory_accounts_for_control_file_and_every_pdf(tmp_path):
    root, files, manifest = inventory(dataset(tmp_path))
    assert len(files) == manifest["listed_pdfs"] == 2
    assert {f["document_type"] for f in files} == {"TOR", "TECHNICAL_SPECIFICATION"}
    assert all(len(f["sha256"]) == 64 and f["page_count"] == 1 for f in files)
    assert manifest["handling"] == "READ_AS_CONTROL_MANIFEST"
    (root / "unexpected.txt").write_text("Do not silently upload or ignore unknown files")
    with pytest.raises(ValueError, match="Unexpected non-PDF"):
        inventory(root)


def test_inventory_rejects_manifest_omissions(tmp_path):
    root = dataset(tmp_path)
    (root / "manifest_pdf.txt").write_text("01_Terms_of_Reference.pdf\n")
    with pytest.raises(ValueError, match="differs from manifest"):
        inventory(root)


@pytest.mark.parametrize("url", ["https://example.com", "http://user:secret@localhost:8002"])
def test_runner_never_sends_local_files_to_other_hosts(tmp_path, url):
    with pytest.raises(ValueError, match="restricted to the local server"):
        PositiveCaseBot(url, tmp_path, tmp_path / "report.json")


def test_clean_run_reports_gap_without_generating_fake_downstream_resources(tmp_path):
    root = dataset(tmp_path)
    _, files, _ = inventory(root)
    case_id, job_id, actor_id = [str(uuid4()) for _ in range(3)]
    documents, posts = {}, []
    def envelope(data=None, *, error=None):
        return {"success": error is None, "data": data, "error": error,
            "meta": {"request_id": "req_bot_test", "timestamp": "2026-11-07T00:00:00Z", "api_version": "v1"}}
    case = {"case_id": case_id, "version": 1}
    accepted = {"job_id": job_id}
    job = {"job_id": job_id, "status": "COMPLETED", "result": {"finding_ids": []},
        "ai_execution": {"model": "actual-test-model", "schema_valid": True, "evidence_validation_passed": True}}
    def handler(request):
        path = request.url.path
        if path == "/auth/session":
            return httpx.Response(200, json=envelope({"authenticated": True}))
        if request.method == "POST":
            posts.append(path)
        if path.endswith("/health"):
            data = {"demo_mode": True}
        elif path == "/api/v1/cases":
            data = case
        elif request.method == "POST" and path.endswith("/documents"):
            key = request.headers["Idempotency-Key"]
            if key not in documents:
                item = files[len(documents)]
                documents[key] = {"document_id": str(uuid4()), "case_id": case_id,
                    "sha256": item["sha256"], "page_count": 1, "processing_status": "COMPLETED"}
            data = documents[key]
        elif path.endswith("/analyses"):
            data = accepted
        elif path.endswith("/jobs/" + job_id):
            data = job
        elif request.method == "POST" and path.endswith("/reviews"):
            return httpx.Response(400, json=envelope(error={"code": "VALIDATION_ERROR"}))
        else:
            if path.endswith("/documents"):
                items = list(documents.values())
            elif path.endswith("/audit"):
                types = ["CASE_CREATED", "DOCUMENT_UPLOADED", "DOCUMENT_UPLOADED", "ANALYSIS_FINISHED"]
                items = [{"event_id": str(uuid4()), "event_type": t, "actor": {"actor_id": actor_id}, "event_hash": None} for t in types]
            else:
                items = []
            data = {"items": items, "pagination": {"offset": 0, "limit": 50, "total": len(items)}}
        return httpx.Response(201 if request.method == "POST" and not path.endswith("/analyses") else 202 if request.method == "POST" else 200, json=envelope(data))
    client = httpx.Client(base_url="http://127.0.0.1:8002", transport=httpx.MockTransport(handler))
    output = tmp_path / "result.json"
    bot = PositiveCaseBot("http://127.0.0.1:8002", root, output, client=client, sleep=lambda _: None)
    assert bot.run() == 2
    report = json.loads(output.read_text())
    assert report["status"] == "BLOCKED_CONTRACT_G01"
    assert all(check["status"] == "PASS" for check in report["checks"])
    assert not any(path.endswith(("/challenges", "/simulations", "/repair-proposals")) for path in posts)


def test_local_login_credentials_are_not_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("PROCUREMIND_LOGIN_USERNAME", "test-local-user")
    monkeypatch.setenv("PROCUREMIND_LOGIN_PASSWORD", "test-local-password-only")
    seen = []
    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/auth/session":
            return httpx.Response(200, json={"data": {"authenticated": False}})
        body = json.loads(request.content)
        assert body == {"username": "test-local-user", "password": "test-local-password-only"}
        return httpx.Response(200, json={"data": {"authenticated": True}},
            headers={"set-cookie": "procuremind_session=test-only-session; Path=/; HttpOnly"})
    client = httpx.Client(base_url="http://127.0.0.1:8002", transport=httpx.MockTransport(handler))
    bot = PositiveCaseBot("http://127.0.0.1:8002", tmp_path, tmp_path / "report.json", client=client)
    bot.authenticate()
    assert seen == ["/auth/session", "/auth/login"]
    assert "test-local-password-only" not in json.dumps(bot.report)
    assert client.cookies["procuremind_session"] == "test-only-session"
    client.close()
