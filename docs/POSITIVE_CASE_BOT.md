# Local positive-case test bot

Run from the repository root with the local full-cycle app running:

```powershell
.\.venv\Scripts\python.exe scripts/positive_case_bot.py --base-url http://127.0.0.1:8002 --dataset '..\test_data\Positive' --output '.tools\qa-results\positive-case.json'
$LASTEXITCODE
```

The runner creates a new, labeled test case for each run and preserves all resources for inspection. It uses the real backend and configured live provider. Each run can incur normal provider token usage. It does not automatically retry generation requests. Mutation replay checks reuse the original idempotency key.

The entire specified folder is accounted for: all 14 PDFs, including the scenario manifest PDF, are uploaded. manifest_pdf.txt is read as the control inventory and checked against every PDF; it is not sent to a PDF-only upload endpoint. Unknown non-PDF files, manifest omissions, unreadable PDFs and out-of-folder references fail the run. Document hashes, extracted page counts and persisted counts are checked.

The bot checks canonical envelopes, UUIDs, required backend demo identity, idempotent creation/upload/analysis, terminal-state polling, runtime model/evidence validation, absence of false positives, paginated audit records and refresh persistence. All input is treated as evidence. Statements inside the PDFs about expected workflow or approval do not override API Contract v1.1.

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Passed without a workflow blocker. |
| 1 | A file, API, analysis or assertion failed; inspect report.failure and report.checks. |
| 2 | Clean-positive assertions passed, but final completion remains BLOCKED_CONTRACT_G01. This is the expected current clean-path result and is not full release approval. |

The positive manifest expects final approval, while v1.1 requires repair_proposal_id for a review and does not permit APPROVE_CASE. The runner verifies rejection of that unsupported command and verifies that no fake findings, challenges, simulations or reviews were created. It does not mix the positive pack's 710M/835M/680M offers into the separate synthetic-suppliers-v1 calculation fixture. Approval needs an approved contract addendum; hiding the gap is not a passing test.

## Executed live result, 7 November 2026 (Asia/Jakarta)

- Run: 36a04be2d2124bea98dceeea00058eef.
- Local case: c15cc3f3-dca7-433b-beee-aa2e4a81fdf7.
- Job: 5c7defa4-65bb-49c4-b58c-01abd8e9d052.
- 14 PDFs uploaded and extracted; manifest_pdf.txt read as control. All 49 executed checks passed, with zero failed assertions.
- Actual analysis status COMPLETED; actual model gpt-6.1-sol; 19 requirements; finding_ids=[].
- Evidence checks: 22 checked, 22 passed, 0 failed; no warnings.
- Provider-reported usage: 4716 input tokens, 2358 output tokens. These are recorded measurements, not estimates.
- Final status: BLOCKED_CONTRACT_G01. Challenge/simulation/repair are not applicable to the no-finding branch.
- The original failed upload/analysis histories remain preserved. The bot uses a new case rather than rewriting earlier records.

The complete machine-readable live report is .tools/qa-results/positive-case.json. Local reports and runtime data are ignored by Git. Resume the case using its UUID in the app to inspect it.

## Upload HTTP 500 encountered during local setup

The runtime PDF directory had a protected Windows ACL owned by the restricted runner. After the API server was moved outside the network sandbox, its runtime identity could not create files there: PermissionError on stored_path.open('xb'). This was a local storage permission problem, not invalid PDF content.

Permission inheritance was restored only on .runtime/full-cycle-pdfs, using the workspace parent permissions. Existing PDFs/database records were retained. A live upload returned 201 Created after repair, followed by successful upload of all 14 PDFs in this run. The product's private-directory creation policy and production permissions were not loosened globally.

## Automated runner verification

Five runner tests cover complete manifest inventory, extra/omitted files, remote-destination rejection, and clean-case completion blocking without fabricated downstream commands. Together with the provider schema regressions, 11 tests passed. Provider/P0/decision/demo checks separately passed 94 tests. Earlier unrelated legacy assurance migration-fixture errors remain documented in ASSURE_AUDIT_NULL_FIX.md; no full-backend-green claim is made here.
