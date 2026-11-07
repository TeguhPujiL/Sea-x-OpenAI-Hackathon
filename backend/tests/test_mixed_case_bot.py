"""Runner regressions with explicitly mocked transport and synthetic tiny PDFs."""
from argparse import Namespace
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
import pytest

from scripts.mixed_case_bot import corpora, risk_coverage, run_suite, RiskCaseBot


TEXT = "Synthetic test only: approved 16 GB memory conflicts with mandatory 32 GB memory."
STAMP = "2026-11-07T00:00:00Z"


def make_corpora(tmp_path):
    folders = [tmp_path / "Positive", tmp_path / "Negative"]
    for folder in folders:
        folder.mkdir()
        names = ["02_Technical_Specification.pdf", "07_Bid_Evaluation_Report.pdf"]
        for name in names:
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((40, 40), TEXT)
                (folder / name).write_bytes(pdf.tobytes())
        (folder / "manifest_pdf.txt").write_text("\n".join(names) + "\n")
    return folders


def args_for(tmp_path, positive, negative, **overrides):
    return Namespace(base_url="http://127.0.0.1:8002", positive=positive, negative=negative,
        output_dir=tmp_path / "reports", dry_run=True, scenarios=["positive", "negative", "mixed"],
        timeout=3, analysis_only=False, strict_risks=False, **overrides)


def test_both_manifests_account_for_files_and_same_basenames_keep_source_identity(tmp_path):
    positive, negative = make_corpora(tmp_path)
    roots, files, manifests = corpora(positive, negative)
    assert set(roots) == set(manifests) == {"Positive", "Negative"}
    assert len(files) == 4
    assert len({item["upload_filename"] for item in files}) == 4
    assert {item["upload_filename"] for item in files if item["file"].startswith("02_")} == {
        "Positive__02_Technical_Specification.pdf", "Negative__02_Technical_Specification.pdf"}
    assert all(item["sha256"] and item["page_count"] == 1 for item in files)
    (negative / "unlisted.txt").write_text("unexpected input")
    with pytest.raises(ValueError, match="Unexpected non-PDF"):
        corpora(positive, negative)


def test_dry_run_makes_no_http_calls_and_creates_preserved_json_html_and_latest_pointer(tmp_path, monkeypatch):
    positive, negative = make_corpora(tmp_path)
    def no_http(*args, **kwargs):
        pytest.fail("Dry-run must never send an HTTP request")
    monkeypatch.setattr(httpx.Client, "send", no_http)
    args = args_for(tmp_path, positive, negative)
    assert run_suite(args) == 0
    pointer = json.loads((args.output_dir / "latest.json").read_text())
    report = json.loads(Path(pointer["report_json"]).read_text())
    assert report["mode"] == "DRY_RUN" and report["status"] == "DRY_RUN_READY"
    assert [len(value["files"]) for value in report["scenarios"]] == [2, 2, 4]
    assert all(value["status"] == "NOT_RUN_DRY_RUN" for value in report["scenarios"])
    assert all("analysis" not in value for value in report["scenarios"])
    assert Path(pointer["report_html"]).is_file()
    assert "does not test the API or provider" in Path(pointer["report_html"]).read_text(encoding="utf-8")
    first = pointer["report_json"]
    assert run_suite(args) == 0
    next_pointer = json.loads((args.output_dir / "latest.json").read_text())
    assert next_pointer["report_json"] != first and Path(first).exists()


def test_preflight_failure_still_writes_reports_and_never_sends_files_to_remote_host(tmp_path, monkeypatch):
    positive, negative = make_corpora(tmp_path)
    def no_http(*args, **kwargs):
        pytest.fail("Rejected destination must not receive any HTTP call")
    monkeypatch.setattr(httpx.Client, "send", no_http)
    args = args_for(tmp_path, positive, negative)
    args.base_url = "https://example.com"
    assert run_suite(args) == 1
    pointer = json.loads((args.output_dir / "latest.json").read_text())
    report = json.loads(Path(pointer["report_json"]).read_text())
    assert report["status"] == "FAIL" and report["scenarios"] == []
    assert "restricted to the local server" in report["failure"]["message"]
    assert Path(pointer["report_html"]).is_file()


def test_risk_candidates_require_negative_evidence_not_positive_names_or_manifest_summaries():
    files = [{"document_id": str(uuid4()), "source": source, "file": name} for source, name in (
        ("Positive", "02_Technical_Specification.pdf"),
        ("Negative", "00_Negative_Scenario_Manifest.pdf"),
        ("Negative", "08_Internal_Integrity_Review_and_Action_Record.pdf"),
        ("Negative", "02_Technical_Specification.pdf"),
        ("Negative", "06C_Vendor_C_Warranty_Letter.pdf"),
        ("Negative", "07_Bid_Evaluation_Report.pdf"))]
    def finding(*indices):
        return {"finding_id": str(uuid4()), "title": "Memory 16 GB versus 32 GB and warranty contradiction",
            "summary": "Control issue, not a misconduct verdict", "evidence": [{"document_id": files[i]["document_id"], "excerpt": "memory warranty"} for i in indices]}
    for bad in (finding(0), finding(1, 2)):
        assert all(value["status"] == "WARN" for value in risk_coverage([bad], files))
    memory, warranty_one, warranty_both = finding(3), finding(4), finding(4, 5)
    coverage = risk_coverage([memory, warranty_one, warranty_both], files)
    assert coverage[0]["finding_ids"] == [memory["finding_id"]]
    assert coverage[2]["finding_ids"] == [warranty_both["finding_id"]]
    assert all("Heuristic" in value["detail"] for value in coverage if value["status"] == "PASS")


def mocked_risk_bot(tmp_path, *, provider_failed=False, analysis_only=False, strict_risks=False):
    positive, negative = make_corpora(tmp_path)
    roots, files, _ = corpora(positive, negative)
    files = [item for item in files if item["source"] == "Negative"]
    case_id, job_id, finding_id, actor_id, simulation_id, repair_id, review_id = [str(uuid4()) for _ in range(7)]
    case = {"case_id": case_id, "version": 1, "assurance_status": "ACTION_REQUIRED"}
    created_case = dict(case)
    state = {"documents": {}, "audit": [], "posts": [], "patches": [], "review_keys": set(), "repair": None}
    def audit(event_type, resource_id):
        state["audit"].append({"event_id": str(uuid4()), "case_id": case_id, "event_type": event_type,
            "actor": {"actor_id": actor_id}, "resource": {"id": resource_id, "version": 1}, "occurred_at": STAMP,
            "request_id": "req_mocked_mixed_test", "event_hash": None, "previous_hash": None})
    def envelope(data=None, error=None):
        return {"success": error is None, "data": data, "error": error,
            "meta": {"api_version": "v1", "timestamp": STAMP, "request_id": "req_mocked_mixed_test"}}
    def response(data=None, status=200, error=None):
        return httpx.Response(status, json=envelope(data, error))
    def conflict():
        return response(status=409, error={"code": "VERSION_CONFLICT", "message": "Version changed", "retryable": False, "details": []})
    def page(items):
        return {"items": items, "pagination": {"offset": 0, "limit": 50, "total": len(items)}}
    def job():
        return {"job_id": job_id, "case_id": case_id, "status": "FAILED" if provider_failed else "COMPLETED",
            "result": None if provider_failed else {"finding_ids": [finding_id]},
            "ai_execution": None if provider_failed else {"model": "mock-only-observed-model", "schema_valid": True, "evidence_validation_passed": True},
            "warnings": [], "error": {"code": "AI_PROVIDER_ERROR", "message": "Mock provider failure", "retryable": False} if provider_failed else None}
    draft = {"repair_proposal_id": repair_id, "case_id": case_id, "finding_id": finding_id,
        "simulation_id": simulation_id, "status": "DRAFT", "version": 1, "proposed_text": "Request memory requirement evidence."}
    review = {"review_id": review_id, "case_id": case_id, "decision": "REQUEST_EVIDENCE", "review_status": "COMPLETED",
        "assurance_status_after": "ACTION_REQUIRED", "reviewer": {"actor_id": actor_id}}
    simulation = {"simulation_id": simulation_id, "case_id": case_id, "finding_id": finding_id,
        "result": {"baseline": {"eligible_supplier_count": 1, "lowest_total_offer_idr": 825000000},
            "alternative": {"eligible_supplier_count": 3, "lowest_total_offer_idr": 660000000},
            "delta": {"eligible_supplier_count": 2, "lowest_total_offer_idr": -165000000}}}
    def handler(request):
        path, method = request.url.path, request.method
        key = request.headers.get("Idempotency-Key")
        body = json.loads(request.content) if request.headers.get("content-type", "").startswith("application/json") else {}
        if method == "POST":
            state["posts"].append((path, body, key))
        if method == "PATCH":
            state["patches"].append((path, body))
        if path == "/auth/session":
            return response({"authenticated": True})
        if path.endswith("/health"):
            return response({"demo_mode": True})
        if path == "/api/v1/cases":
            if not state["audit"]:
                audit("CASE_CREATED", case_id)
            return response(created_case, 201)
        if path.endswith("/documents"):
            if method == "GET":
                return response(page(list(state["documents"].values())))
            if key not in state["documents"]:
                item = files[len(state["documents"])]
                value = {"document_id": str(uuid4()), "case_id": case_id, "sha256": item["sha256"], "page_count": 1, "processing_status": "COMPLETED"}
                state["documents"][key] = value
                audit("DOCUMENT_UPLOADED", value["document_id"])
            return response(state["documents"][key], 201)
        if path.endswith("/analyses"):
            if not any(event["event_type"] == "ANALYSIS_FINISHED" for event in state["audit"]):
                audit("ANALYSIS_FINISHED", job_id)
            return response({"job_id": job_id}, 202)
        if path.endswith("/jobs/" + job_id):
            return response(job())
        if path.endswith("/findings"):
            doc_id = next(iter(state["documents"].values()))["document_id"]
            finding = {"finding_id": finding_id, "case_id": case_id, "analysis_job_id": job_id, "evidence_status": "VERIFIED",
                "title": "Memory baseline conflict 16 GB versus 32 GB", "summary": TEXT,
                "evidence": [{"document_id": doc_id, "page_number": 1, "excerpt": TEXT, "verification_status": "VERIFIED"}]}
            return response(page([finding]))
        if path.endswith("/challenges"):
            audit("CHALLENGE_CREATED", finding_id)
            return response({"case_id": case_id, "finding_id": finding_id, "status": "DRAFT", "ai_execution_id": str(uuid4())}, 201)
        if path.endswith("/simulations"):
            if not any(event["event_type"] == "SIMULATION_CREATED" for event in state["audit"]):
                audit("SIMULATION_CREATED", simulation_id)
            return response(simulation, 201)
        if path.endswith("/repair-proposals"):
            if state["repair"] is None:
                state["repair"] = deepcopy(draft)
                audit("REPAIR_CREATED", repair_id)
            return response(draft, 201)
        if path.endswith("/repair-proposals/" + repair_id):
            if method == "PATCH":
                if body["expected_version"] != state["repair"]["version"]:
                    return conflict()
                state["repair"].update(status="SUBMITTED", version=2)
                case["version"] = 2
            return response(state["repair"])
        if path.endswith("/reviews"):
            assert body["decision"] == "REQUEST_EVIDENCE"
            if key in state["review_keys"]:
                return response(review, 201)
            if body["expected_case_version"] != case["version"]:
                return conflict()
            state["review_keys"].add(key)
            case["version"] += 1
            audit("REVIEW_COMPLETED", review_id)
            return response(review, 201)
        if path.endswith("/reviews/" + review_id):
            return response(review)
        if path.endswith("/audit"):
            return response(page(state["audit"]))
        if path.endswith("/cases/" + case_id):
            return response(case)
        pytest.fail(f"Unexpected mocked request: {method} {path}")
    client = httpx.Client(base_url="http://127.0.0.1:8002", transport=httpx.MockTransport(handler))
    bot = RiskCaseBot("http://127.0.0.1:8002", roots, files, tmp_path / "risk-result.json", scenario="negative",
        analysis_only=analysis_only, strict_risks=strict_risks, client=client, sleep=lambda _: None)
    return bot, state


def test_risk_workflow_replays_keys_rejects_stale_versions_and_never_approves(tmp_path):
    bot, state = mocked_risk_bot(tmp_path)
    assert bot.run() == 2  # Uncovered risks remain warnings, not invented findings.
    report = json.loads(bot.output.read_text())
    assert report["status"] == "PASS_WITH_WARNINGS"
    assert report["workflow"]["assure"] == "PASS_REQUEST_EVIDENCE_ACTION_REQUIRED"
    assert report["workflow"]["simulation"] == "PASS_CONTRACT_FIXTURE_ONLY"
    names = {check["name"] for check in report["checks"] if check["status"] == "PASS"}
    assert {"simulation_replay", "repair_replay", "review_replay", "stale_repair_version_rejected", "stale_case_version_rejected", "immutable_review_refresh", "submitted_repair_unchanged"} <= names
    assert len(state["review_keys"]) == 1 and len(state["documents"]) == 2
    assert not any(body.get("decision") in {"APPROVE_DRAFT", "APPROVE_CASE"} for _, body, _ in state["posts"])
    assert report["analysis"]["ai_execution"]["model"] == "mock-only-observed-model"
    assert report["audit"] and report["risk_coverage"][1]["status"] == "WARN"


def test_provider_failure_preserves_error_and_audit_without_creating_downstream_resources(tmp_path):
    bot, state = mocked_risk_bot(tmp_path, provider_failed=True)
    assert bot.run() == 1
    report = json.loads(bot.output.read_text())
    assert report["status"] == "FAIL" and report["workflow"]["assess"] == "FAIL"
    assert report["analysis"]["error"]["code"] == "AI_PROVIDER_ERROR"
    assert report["audit"] and "challenge" not in report
    assert not any(path.endswith(("/challenges", "/simulations", "/repair-proposals", "/reviews")) for path, _, _ in state["posts"])


def test_analysis_only_explicitly_skips_workflow_and_strict_coverage_fails_missing_risks(tmp_path):
    bot, state = mocked_risk_bot(tmp_path, analysis_only=True, strict_risks=True)
    assert bot.run() == 1
    assert bot.report["failure"]["message"] == "all_expected_risks_have_coverage_candidates"
    assert bot.report["workflow"]["assess"] == "PASS_RISKS_DETECTED"
    assert bot.report["workflow"]["repair"] == "NOT_RUN_ANALYSIS_ONLY"
    assert not any(path.endswith("/challenges") for path, _, _ in state["posts"])


@pytest.mark.parametrize("bad_ref", [
    {"document_id": str(uuid4()), "page_number": 1, "excerpt": TEXT},
    {"page_number": 2, "excerpt": TEXT},
    {"page_number": 1, "excerpt": "A quotation absent from source"},
])
def test_findings_cannot_pass_with_foreign_out_of_range_or_fabricated_citations(tmp_path, bad_ref):
    bot, _ = mocked_risk_bot(tmp_path, analysis_only=True)
    case_id, job_id, document_id, finding_id = [str(uuid4()) for _ in range(4)]
    bot.report["case_id"] = case_id
    bot.page_text[(document_id, 1)] = TEXT
    ref = {"document_id": document_id, "page_number": 1, "excerpt": TEXT, **bad_ref}
    finding = {"finding_id": finding_id, "case_id": case_id, "analysis_job_id": job_id, "evidence": [ref]}
    try:
        with pytest.raises(AssertionError, match="evidence_"):
            bot.validate_findings([finding], {"job_id": job_id, "result": {"finding_ids": [finding_id]}})
    finally:
        bot.client.close()
