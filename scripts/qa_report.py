"""Render saved QA measurements as a self-contained, inert HTML report."""
from collections import Counter
from html import escape
import json
from pathlib import Path


_PRIVATE_KEYS = {"password", "api_key", "openai_api_key", "authorization", "cookie",
                 "set-cookie", "session_token", "access_token", "secret", "credentials"}


def _public(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if str(key).lower() in _PRIVATE_KEYS else _public(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    return value


def _text(value):
    if value is None:
        return "Not recorded"
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(_public(value), indent=2, ensure_ascii=False)
    return escape(str(value), quote=True)


def _status(value):
    label = str(value or "NOT_RECORDED")
    tone = "bad" if label in {"FAIL", "FAILED", "ERROR"} else "good" if label == "PASS" else "neutral"
    return f'<span class="badge {tone}">{_text(label)}</span>'


def _table(columns, rows):
    rows = list(rows)
    if not rows:
        return '<p class="muted">None recorded.</p>'
    return '<div class="scroll"><table><thead><tr>' + "".join(
        f"<th>{_text(column)}</th>" for column in columns
    ) + "</tr></thead><tbody>" + "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    ) + "</tbody></table></div>"


def _details(title, value):
    return f"<details><summary>{_text(title)}</summary><pre>{_text(value)}</pre></details>"


def _scenario(value, index):
    analysis = value.get("analysis") or {}
    execution = analysis.get("ai_execution")
    risk = value.get("risk_coverage") or []
    if isinstance(risk, dict):
        risk = [{"name": name, **item} if isinstance(item, dict) else {"name": name, "detail": item}
                for name, item in risk.items()]
    result = analysis.get("result") or {}
    findings = value.get("findings") or []
    pieces = [f'<section aria-labelledby="scenario-{index}"><h2 id="scenario-{index}">{_text(value.get("scenario", "Scenario"))} {_status(value.get("status"))}</h2>',
        '<dl class="metadata">' + "".join(f"<dt>{label}</dt><dd>{_text(item)}</dd>" for label, item in [
            ("Case ID", value.get("case_id")), ("Job ID", value.get("job_id")),
            ("Started (UTC)", value.get("started_at")), ("Finished (UTC)", value.get("finished_at")),
            ("Analysis status", analysis.get("status", "Not executed / not recorded")),
            ("Finding IDs", result.get("finding_ids")),
        ]) + "</dl>"]
    if value.get("failure"):
        pieces.append(f'<div class="failure"><strong>Failure</strong><pre>{_text(value["failure"])}</pre></div>')
    if value.get("audit_failure"):
        pieces.append(f'<div class="failure"><strong>Audit verification failure</strong><pre>{_text(value["audit_failure"])}</pre></div>')
    if value.get("warnings"):
        pieces.append('<div class="notice"><strong>Scenario warnings</strong><ul>' + "".join(
            f"<li>{_text(warning)}</li>" for warning in value["warnings"]) + "</ul></div>")
    if value.get("completion_gap"):
        pieces.append(f'<p class="notice">{_text(value["completion_gap"])}</p>')
    for field, label in (("simulation_limit", "Simulation interpretation limit"), ("audit_limit", "Audit verification limit")):
        if value.get(field):
            pieces.append(f'<p class="notice"><strong>{label}:</strong> {_text(value[field])}</p>')
    pieces.extend(["<h3>Workflow</h3>", _table(["Step", "Recorded outcome"],
        ((_text(step), _text(outcome)) for step, outcome in (value.get("workflow") or {}).items())),
        "<h3>Expected risk coverage</h3>", _table(["Risk", "Status", "Finding IDs", "Detail"],
        ((_text(item.get("name")), _status(item.get("status")), _text(item.get("finding_ids")), _text(item.get("detail"))) for item in risk)),
        "<h3>Execution and evidence</h3>"])
    if execution:
        pieces.append(_details("Recorded AI execution", execution))
    else:
        pieces.append('<p class="muted">No AI execution recorded. An inventory-only run does not test the API or provider.</p>')
    if analysis.get("warnings"):
        pieces.append(_details("Analysis warnings", analysis["warnings"]))
    if analysis.get("error"):
        pieces.append(f'<div class="failure"><strong>Analysis error</strong><pre>{_text(analysis["error"])}</pre></div>')
    if findings:
        pieces.append(_table(["Finding", "Evidence status", "Source evidence"],
            ((_text({key: item.get(key) for key in ("finding_id", "type", "title", "summary")}),
              _text(item.get("evidence_status")), _text(item.get("evidence"))) for item in findings)))
    else:
        pieces.append('<p class="muted">No finding detail recorded; this alone does not establish a clean case.</p>')
    pieces.extend(["<h3>Executed checks</h3>", _table(["Check", "Status", "Detail"],
        ((_text(item.get("name")), _status(item.get("status")), _text(item.get("detail"))) for item in value.get("checks", []))),
        '<h3>Recorded API responses</h3><p class="muted">Non-2xx responses can be intentional validation or stale-version probes. Consult the executed checks; an HTTP status alone does not establish a failed assertion. Expected status is shown only when recorded by the runner.</p>',
        _details("No API responses recorded", "No request trace was returned by this scenario.") if not value.get("requests") else
        '<details><summary>HTTP response trace</summary>' + _table(["Method", "Path", "Observed HTTP status", "Expected HTTP status"],
        ((_text(item.get("method")), _text(item.get("path")), _text(item.get("status")), _text(item.get("expected_status")))
         for item in value["requests"])) + '</details>',
        "<h3>Input inventory</h3>", _table(["Source", "File", "SHA-256", "Stored document ID"],
        ((_text(item.get("source")), _text(item.get("file")), _text(item.get("sha256")), _text(item.get("document_id")))
         for item in value.get("files", []))), "</section>"])
    return "\n".join(pieces)


def write_html_report(report: dict, output: Path) -> None:
    """Write only recorded outcomes; escape data and avoid executable links/scripts."""
    scenarios = report.get("scenarios") or ([report] if report.get("scenario") else [])
    counts = Counter(str(check.get("status", "NOT_RECORDED"))
                     for value in scenarios for check in value.get("checks", []))
    summary = _table(["Scenario", "Status", "Files", "Checks passed", "Checks failed"], (
        (_text(value.get("scenario")), _status(value.get("status")), _text(len(value.get("files", []))),
         _text(sum(check.get("status") == "PASS" for check in value.get("checks", []))),
         _text(sum(check.get("status") == "FAIL" for check in value.get("checks", [])))) for value in scenarios))
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
        '<title>ProcureMind QA test report</title><style>',
        'body{font:15px/1.5 system-ui,sans-serif;color:#173536;background:#eef3f3;margin:0}main{max-width:1200px;margin:auto;padding:28px}h1{font-size:28px}h2{font-size:22px}h3{margin-top:28px}section,.card{background:white;border:1px solid #ccd9d9;border-radius:12px;padding:24px;margin:20px 0}.metadata{display:grid;grid-template-columns:160px 1fr;gap:7px 16px}.metadata dt{font-weight:600}.metadata dd{margin:0;overflow-wrap:anywhere}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #d8e2e2;white-space:pre-wrap;overflow-wrap:anywhere}th{background:#f3f7f7}.badge{display:inline-block;padding:3px 8px;border-radius:6px;font-size:12px;background:#e7eded;overflow-wrap:anywhere}.good{background:#d9eee2;color:#14552f}.bad,.failure{background:#fff0ed;color:#902f24}.neutral{background:#fff1ce;color:#684b06}.failure,.notice{padding:14px;border-radius:6px}.notice{background:#fff7df}.muted{color:#587071}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}details{margin:8px 0}summary{cursor:pointer;font-weight:600}@media(max-width:600px){main{padding:12px}section,.card{padding:16px}.metadata{grid-template-columns:1fr;gap:4px}.metadata dd{margin-bottom:10px}}',
        '</style></head><body><main><h1>ProcureMind QA test report</h1>',
        f'<p>Suite status: {_status(report.get("status"))}</p>',
        '<div class="card"><dl class="metadata">' + "".join(
            f"<dt>{label}</dt><dd>{_text(value)}</dd>" for label, value in [
                ("Run ID", report.get("run_id")), ("Started (UTC)", report.get("started_at")),
                ("Finished (UTC)", report.get("finished_at")), ("Local API", report.get("base_url")),
                ("Scenario count", len(scenarios)), ("Executed check counts", dict(counts))]) + '</dl></div>',
        '<p>This report reflects only recorded checks. It is not production certification or procurement approval. Uploaded document statements do not override API Contract v1.1.</p>']
    if report.get("failure"):
        parts.append(f'<div class="failure"><strong>Suite failure</strong><pre>{_text(report["failure"])}</pre></div>')
    parts.extend(["<h2>Scenario summary</h2>", summary])
    parts.extend(_scenario(value, index) for index, value in enumerate(scenarios))
    parts.extend(['<section><h2>Known contract limits</h2>',
        '<p><strong>G01 — clean-case completion:</strong> v1.1 requires a repair proposal for review and has no APPROVE_CASE decision. A positive control may pass clean assertions while final completion remains blocked. No finding or repair should be fabricated.</p>',
        '<p><strong>G14 — audit provenance:</strong> the integrated service may return null hashes. Displaying those records does not verify a hash chain. Hash chaining, when available, is tamper-evident; this report does not claim tamper-proof storage.</p>',
        '<p>Missing risk coverage or skipped workflow stages must be reviewed separately from passed assertions. Runtime provider usage and evidence checks are shown only when returned by the app.</p>',
        '</section></main></body></html>'])
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts) + "\n", encoding="utf-8")
