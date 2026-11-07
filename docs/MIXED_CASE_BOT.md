# Repeatable local corpus QA

Run the three-scenario suite from the repository root, with the local application running:

```powershell
.\scripts\run_mixed_case_bot.cmd
```

Or use Python directly:

```powershell
.\.venv\Scripts\python.exe scripts/mixed_case_bot.py --base-url http://127.0.0.1:8002
```

The default datasets are `../test_data/Positive` and `../test_data/Negative`, resolved relative to the repository, independent of the shell's working directory. Each contains 14 PDFs and a `manifest_pdf.txt` control inventory. Every PDF, including the scenario manifest PDF, is uploaded. The text control inventory is read and validated rather than sent to the PDF-only endpoint. Unknown files, omissions, duplicate inventory entries and paths resolving outside the dataset fail preflight.

## Scenarios and persisted results

1. Positive control: all Positive PDFs in an independent case; checks for no false findings. The existing positive bot records the clean-completion contract gap G01 rather than generating a fake finding or repair.
2. Negative control: all Negative PDFs in an independent case; expects source-grounded findings and exercises challenge, deterministic simulation, repair submission, and an immutable `REQUEST_EVIDENCE` review leaving assurance `ACTION_REQUIRED`.
3. Mixed case: all PDFs from both folders in one new case. Uploaded names start with `Positive__` or `Negative__`; original names, hashes, source folders and returned document IDs are retained in reports. Neither pack is silently declared the authoritative procurement version.

The default live suite uploads 56 PDFs across three new cases. It makes up to seven deliberate AI generation calls (one per analysis, plus challenge and repair for each risk case). Calls use the backend's real configured provider and can incur normal usage charges. Generation failures are reported without automatic retries. Idempotency checks repeat the same captured request/key; they are not additional generation attempts.

All test cases, documents, executions and reviews remain available for inspection in the application. The bot never deletes test history, changes uploaded PDFs, resolves findings, approves procurement, or sends a client-authored reviewer identity. Challenge readiness remains a human action; generated challenges are checked as DRAFT.

## Reports

Every invocation, including dry runs and failures after argument parsing, writes a unique UTC timestamp/run-ID directory:

```text
.tools/qa-results/mixed/<UTC-timestamp>-<run-id>/report.json
.tools/qa-results/mixed/<UTC-timestamp>-<run-id>/report.html
```

Live runs also retain individual `positive.json`, `negative.json` and `mixed.json` results. `latest.json` in the parent folder points to the latest aggregate JSON and HTML. Previous run directories are preserved. HTML is self-contained, escapes document/server text, and requires no network or scripts to open.

Find the latest report in PowerShell:

```powershell
$mixedReport = Get-Content .tools/qa-results/mixed/latest.json | ConvertFrom-Json
$mixedReport.report_html
$mixedReport.report_json
$LASTEXITCODE
```

Reports record measured checks, workflow stages, source inventories, case/job/resource IDs, findings/citations, actual AI provenance/evidence counters/usage, warnings and errors. Credentials and session cookies remain in memory and are never intentionally included. Login uses the existing ignored `.env` configuration, via the same backend login settings as the positive bot. Never hardcode API keys in the scripts or commit `.env`/runtime reports.

## Useful options

```powershell
# Inventory validation and reports only: no API calls, no provider usage.
.\scripts\run_mixed_case_bot.cmd --dry-run

# Only the combined case.
.\scripts\run_mixed_case_bot.cmd --scenarios mixed

# Stop after analysis/evidence/audit checks on the risk cases.
.\scripts\run_mixed_case_bot.cmd --analysis-only

# Treat missing heuristic coverage of any expected negative risk as a failure.
.\scripts\run_mixed_case_bot.cmd --strict-risks

# Custom local endpoint, datasets, report folder and polling deadline.
.\scripts\run_mixed_case_bot.cmd --base-url http://127.0.0.1:8002 --positive "..\test_data\Positive" --negative "..\test_data\Negative" --output-dir ".tools\qa-results\mixed" --timeout 600
```

Only loopback destinations are allowed. The Windows CMD launcher works from PowerShell without changing its script execution policy. It changes to the repository root for execution and restores the caller's working directory. It requires the project's installed `.venv`. It does not start or restart the server, change runtime settings, or schedule recurring executions.

## Assertions and limitations

The runner checks canonical envelopes, complete uploads, hashes/pages, case isolation of returned findings, exact whitespace-normalized quotations against the local PDF pages, source-to-document mapping, analysis result IDs, measured provider provenance, idempotent replays, stale case/repair versions, frozen submitted repair content, immutable review detail, server-derived ACTION_REQUIRED, audit actor/time/resource fields and refresh persistence.

Four coverage candidates are reported: the memory baseline conflict, HPS arithmetic mismatch, warranty-record contradiction, and draft-order deviation. A candidate requires relevant Negative source citations and matching terms; summaries from scenario manifests alone do not qualify. This is a heuristic detection aid, not a semantic correctness or completeness certificate. Missing candidates are warnings by default; `--strict-risks` turns them into failures. A mixed case cannot establish a clean pack's false-positive rate; the independent Positive control provides that check. Processing NEEDS_REVIEW is evidence-quality uncertainty, not the same thing as business assurance ACTION_REQUIRED.

Simulation assertions use only the separate approved `synthetic-suppliers-v1` fixture: baseline 32 GB = 1 / 825000000 IDR, alternative 16 GB = 3 / 660000000 IDR, delta +2 / -165000000 IDR. PDF pack prices are never substituted into that fixture. These numbers do not establish actual savings, loss or misconduct.

Known gaps remain explicit: G01 prevents final completion of a clean case under v1.1; G14 permits readable null audit hashes in the integrated implementation without establishing chain integrity. This bot checks audit presence and live refresh; it does not restart the app, prove rollback atomicity, exhaustively test authorization, or certify production readiness. Test-only REQUEST_EVIDENCE is performed as the backend's configured trusted demo QA actor.

| Exit | Meaning |
| --- | --- |
| 0 | Executed checks passed without warnings, or offline preflight is ready. DRY_RUN_READY never means a live workflow passed. |
| 1 | Inventory, API, provider, evidence, assertion or required audit check failed. Inspect the saved report. |
| 2 | Executed checks passed with a documented gap or coverage/evidence warning. The full three-scenario suite currently has G01 from the positive control. |

Regression checks for the runner and report writer:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_positive_case_bot.py backend/tests/test_mixed_case_bot.py backend/tests/test_qa_report.py -q
```

## Executed local run, 7 November 2026 (Asia/Jakarta)

Run `20261107T064251Z-05f54f45` used the running local app at `http://127.0.0.1:8002`, from local source commit `e3058b1` plus the new runner files. It did not run the later vendor-recommendation/Assure-summary commits fetched during the test.

| Scenario | PDFs | Checks passed | Findings | Result |
| --- | --- | --- | --- | --- |
| Positive control | 14 | 49 | 0 | BLOCKED_CONTRACT_G01 |
| Negative control | 14 | 81 | 5 | PASS; REQUEST_EVIDENCE / ACTION_REQUIRED |
| Mixed | 28 | 104 | 4 | PASS; REQUEST_EVIDENCE / ACTION_REQUIRED |

All 234 executed checks passed. Both risk scenarios matched all four heuristic risk candidates. Analysis evidence checks passed 18/18, 36/36 and 32/32 respectively, with no failed evidence checks. The aggregate status is `PASS_WITH_KNOWN_GAPS_OR_WARNINGS` because the Positive control remains blocked by G01. Detailed local artifacts are `.tools/qa-results/mixed/20261107T064251Z-05f54f45/report.json` and `report.html`; no API keys or runtime database files belong in Git.

Verification: 332 backend tests passed, including the runner/report regressions. The CMD launcher's offline preflight was also executed successfully. No frontend or backend runtime contract was changed by these QA tools.
