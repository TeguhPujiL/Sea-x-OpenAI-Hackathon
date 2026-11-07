from pathlib import Path

from scripts.qa_report import write_html_report


def render(tmp_path, report):
    output = tmp_path / "nested" / "report.html"
    assert write_html_report(report, output) is None
    return output.read_text(encoding="utf-8")


def test_report_escapes_document_and_error_content_without_executable_links(tmp_path):
    hostile = '<script>alert("test")</script><img src=x onerror=alert(1)>'
    text = render(tmp_path, {"run_id": hostile, "base_url": "javascript:alert(1)", "status": hostile,
        "scenarios": [{"scenario": hostile, "status": hostile, "failure": {"message": hostile},
            "files": [{"source": hostile, "file": hostile}],
            "checks": [{"name": hostile, "detail": {"message": hostile}}],
            "findings": [{"title": hostile, "evidence": [{"excerpt": hostile}]}]}]})
    assert "<script>" not in text
    assert "<img" not in text
    assert "&lt;script&gt;" in text
    assert "href=" not in text and "src=" not in text.replace("&lt;img src=", "")
    assert "Content-Security-Policy" in text
    assert 'class="badge neutral">&lt;script&gt;' in text


def test_empty_failure_and_inventory_only_runs_do_not_claim_live_execution(tmp_path):
    text = render(tmp_path, {"status": "FAIL", "failure": {"type": "ValueError", "message": "Dataset absent"}})
    assert "Dataset absent" in text and "Scenario count" in text
    assert "production certification" in text
    text = render(tmp_path, {"status": "DRY_RUN", "scenarios": [{"scenario": "MIXED", "status": "DRY_RUN", "files": [{"source": "Negative", "file": "sample.pdf"}]}]})
    assert "No AI execution recorded" in text
    assert "does not test the API or provider" in text
    assert "No finding detail recorded; this alone does not establish a clean case" in text
    assert "sample.pdf" in text and "Not executed / not recorded" in text


def test_report_counts_only_executed_checks_and_retains_workflow_risks_and_evidence(tmp_path):
    text = render(tmp_path, {"run_id": "run-test", "status": "PASS_WITH_KNOWN_GAPS", "started_at": "2026-11-07T00:00:00Z",
        "scenarios": [{"scenario": "POSITIVE", "status": "BLOCKED_CONTRACT_G01", "checks": [{"name": "clean", "status": "PASS"}]},
            {"scenario": "MIXED", "status": "FAIL", "case_id": "case-test", "job_id": "job-test",
             "workflow": {"upload": "PASS", "repair": "NOT_EXECUTED"},
             "risk_coverage": [{"name": "memory-conflict", "status": "PASS", "finding_ids": ["f-test"]}],
             "checks": [{"name": "sources", "status": "PASS"}, {"name": "warranty", "status": "FAIL"}],
             "analysis": {"status": "COMPLETED", "result": {"finding_ids": ["f-test"]}, "ai_execution": {"usage": {"input_tokens": 123}, "evidence_checks": {"checked": 4}}},
             "findings": [{"finding_id": "f-test", "title": "Conflicting memory", "evidence_status": "VERIFIED", "evidence": [{"excerpt": "16 GB minimum", "page_number": 1}]}]}]})
    assert '&quot;PASS&quot;: 2' in text and '&quot;FAIL&quot;: 1' in text
    assert "memory-conflict" in text and "f-test" in text and "16 GB minimum" in text
    assert "NOT_EXECUTED" in text and "case-test" in text and "job-test" in text
    assert "123" in text and "G01" in text and "G14" in text


def test_sensitive_structured_fields_are_redacted_and_unknown_fields_not_dumped(tmp_path):
    text = render(tmp_path, {"secret": "top-level-private", "scenarios": [{"scenario": "MIXED",
        "analysis": {"ai_execution": {"model": "observed-model", "api_key": "private-api-value", "usage": {"input_tokens": 10}}},
        "checks": [{"name": "test", "detail": {"authorization": "private-bearer-value", "nested": {"password": "private-password-value"}}}]}]})
    assert "private-api-value" not in text and "private-bearer-value" not in text
    assert "private-password-value" not in text and "top-level-private" not in text
    assert "observed-model" in text and "input_tokens" in text
    assert "[REDACTED]" in text


def test_report_displays_audit_failures_warnings_limits_and_observed_http_statuses(tmp_path):
    text = render(tmp_path, {"status": "FAIL", "scenarios": [{"scenario": "MIXED", "status": "FAIL",
        "warnings": ["Risk coverage requires manual review <inspect>"],
        "audit_failure": {"type": "AssertionError", "message": "Missing material audit for upload"},
        "audit_limit": "No rollback atomicity or chain verification was performed.",
        "simulation_limit": "Separate fixture delta is not actual savings.",
        "requests": [{"method": "POST", "path": "/cases/<case>/reviews", "status": 409},
                     {"method": "POST", "path": "/cases", "status": 201, "expected_status": 201}]}]})
    assert "Scenario warnings" in text and "manual review &lt;inspect&gt;" in text
    assert "Audit verification failure" in text and "Missing material audit for upload" in text
    assert "No rollback atomicity or chain verification" in text
    assert "Separate fixture delta is not actual savings" in text
    assert "Observed HTTP status" in text and "Expected HTTP status" in text
    assert "409" in text and "/cases/&lt;case&gt;/reviews" in text
    assert "intentional validation or stale-version probes" in text
    assert "Expected status is shown only when recorded" in text


def test_no_api_data_failure_stays_explicit_without_fabricated_measurements(tmp_path):
    text = render(tmp_path, {"status": "FAIL", "scenarios": [{"scenario": "NEGATIVE", "status": "FAIL",
        "failure": {"type": "ConnectError", "message": "Local app could not be reached"},
        "requests": [], "workflow": {"upload": "FAIL", "assess": "NOT_RUN"}}]})
    assert "Local app could not be reached" in text
    assert "No API responses recorded" in text and "No request trace was returned" in text
    assert "No AI execution recorded" in text
    assert "Not executed / not recorded" in text
    assert "NOT_RUN" in text
    assert "input_tokens" not in text and "evidence_checks" not in text
