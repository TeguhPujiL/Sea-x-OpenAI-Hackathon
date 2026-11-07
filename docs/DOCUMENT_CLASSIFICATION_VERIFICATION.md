# DC1 batch PDF classification verification

Branch: teguh. User request: upload all selected PDFs in one action and automatically match the existing nine document types. The user explicitly confirmed PDF only. The preceding P1 backend work remains present and separately disabled; this later request authorizes DC1 frontend integration.

## Result and prompt

The browser uploads every PDF using the original single-file multipart API, retaining one idempotency key per file. It then classifies uploaded files with at most two concurrent classification/PATCH operations. Successful, independently supported proposals fill the existing type field through its expected_version PATCH; ambiguity and failures do not discard or upload PDFs again. The manual type editor remains available. Per-file primary-purpose rationale, page-addressed excerpts, AI execution ID and a nine-type batch summary are visible.

Prompt source: backend/app/services/ai/classification.py, INSTRUCTIONS. Version: document-classification-v1. It defines TOR, TECHNICAL_SPECIFICATION, OWNER_COST_ESTIMATE, TECHNICAL_JUSTIFICATION, SUPPLIER_QUOTATION, WARRANTY_EVIDENCE, EVALUATION_REPORT, CONTRACT and OTHER; distinguishes buyer estimates from offers and governing criteria from evaluation decisions; ignores embedded instructions and never uses the filename. PDF bytes are immutable. Classification is not substantive supplier compliance, signature authentication or approval.

An AUTO_READY proposal requires valid schema, exact authorized citations, confidence>=0.90, no model ambiguity, exactly one independently recognized primary heading within the first 200 normalized characters of page1, and a verified heading citation for the same role. Draft/template contracts and OTHER require human review. Confidence is not calibrated accuracy or evidence verification. Unknown or compound documents may require manual classification; no guarantee of perfect classification is made.

API: see DOCUMENT_CLASSIFICATION_ADDENDUM.md (DC1 is PROPOSED for shared deployment). POST /api/v1/documents/{document_id}/classifications returns201 with a proposal, requires document:write, ACL, Idempotency-Key and expected_version. It changes no document metadata itself and adds no tables. Existing AiExecution, GenerationLease, IdempotencyRecord and transaction-bound AuditService are reused. Unauthorized or stale requests fail closed; actual provider attempts retain model/usage/latency and evidence checks, including controlled provider/schema failures.

## Executed tests

- Full backend regression run: 370 passed, 11 skipped (9 classification live tests and 2 P1 live tests intentionally opt-in). This run preceded addition of eight Indonesian-heading fixture cases.
- Final targeted classification backend tests: 28 passed, including the nine categories, eight Indonesian headings, malformed citations, low confidence, injected/wrong-role labels, mixed documents, draft contracts, source/version changes, revoked case membership, provider timeout/rate/errors and idempotent replay without duplicate inference.
- Full frontend Node suite: 82 passed, including a nine-file batch, concurrency bound, no duplicate uploads on classification failure, same-key transport retry, cross-case rejection and preservation of a newer human-selected type.
- TypeScript typecheck and production build passed; latest local asset index-D74fOwdc.js was produced with classification enabled.
- Live model golden tests: 9 passed, using real uploaded synthetic PDFs and actual runtime model gpt-6.1-sol. Eight recognized types were AUTO_READY and OTHER was NEEDS_REVIEW. This is 9/9 on these synthetic fixtures, not a general accuracy estimate.
- Actual authenticated localhost web check passed: a synthetic PDF named misleading-contract-name.pdf with a TERMS OF REFERENCE heading was classified TOR/AUTO_READY, then assigned through versioned PATCH (HTTP200). The synthetic document and case were soft-deleted afterward; existing user PDFs were unchanged.
- Default P0 schema hides DC1. Running local OpenAPI exposes DC1 and zero P1 assessment paths. Current source flags remain opt-in; no shared deployment, commit or push was performed.

## Actual live golden observations

All entries had schema_valid=true and evidence_validation_passed=true; provider=openai, model=gpt-6.1-sol, prompt=document-classification-v1. Values below are observations from isolated synthetic test databases, not live response templates.

| Type | Result | Verified citations | Latency ms | Input/output tokens |
| --- | --- | --- | --- | --- |
| TOR | AUTO_READY | 1/1 | 5473 | 676/119 |
| TECHNICAL_SPECIFICATION | AUTO_READY | 1/1 | 3236 | 679/115 |
| OWNER_COST_ESTIMATE | AUTO_READY | 2/2 | 3294 | 682/172 |
| TECHNICAL_JUSTIFICATION | AUTO_READY | 1/1 | 3235 | 671/172 |
| SUPPLIER_QUOTATION | AUTO_READY | 1/1 | 3362 | 685/151 |
| WARRANTY_EVIDENCE | AUTO_READY | 1/1 | 2431 | 678/118 |
| EVALUATION_REPORT | AUTO_READY | 2/2 | 3043 | 680/164 |
| CONTRACT | AUTO_READY | 1/1 | 3978 | 680/200 |
| OTHER | NEEDS_REVIEW | 2/2 | 2718 | 674/145 |

## Try locally

Open http://localhost:8000, reload with Ctrl+Shift+R, sign in using the existing local credentials, create/open a case and select all PDFs in the Upload step. Upload completes before classification starts. Review uncertain rows and save any manual type changes before analysis. Use Confirm selected type followed by Save document types to retain OTHER explicitly; that confirmation uses the existing versioned PATCH and audit record. Failed classification rows can retry processing without creating new PDF records.

The local opt-in is retained in ignored .runtime/demo-features.json as {"document_classification":true}; scripts/demo_runtime.py derives matching backend/browser flags for setup/start. It does not edit .env or expose the provider key. Explicit process environment variables override this local preference. Shared deployments default to false and must coordinate PROCUREMIND_DOCUMENT_CLASSIFICATION_ENABLED with VITE_DOCUMENT_CLASSIFICATION_ENABLED. Set the local preference to false and rebuild/restart to disable.

```powershell
.\.venv\Scripts\python.exe scripts/demo_runtime.py setup --skip-install
.\.venv\Scripts\python.exe scripts/demo_runtime.py start
```

For a separate Vite dev server use frontend/.env or its shell flag VITE_DOCUMENT_CLASSIFICATION_ENABLED=true, together with the matching backend flag. No OpenAI key belongs in VITE variables.

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_document_classification.py -q
$env:PROCUREMIND_RUN_CLASSIFICATION_LIVE='1'
# Explicit live opt-in: sends nine generated synthetic PDFs; incurs provider usage.
.\.venv\Scripts\python.exe -m pytest backend/tests/test_document_classification_live.py -q
```

A pre-existing Starlette TestClient/httpx deprecation warning remains. Browser visual/keyboard QA was not performed with browser automation; frontend behavior was checked with Node integration tests and the real local API flow.

## DC1 files

Backend: schemas/classification.py; services/ai/classification.py; services/documents/classification.py; api/routes/document_classification.py; core/config.py; main.py; tests/test_document_classification.py; tests/test_document_classification_live.py.

Frontend: src/classification.ts; src/uploads.ts; src/api.ts; src/App.tsx; src/WorkspaceView.tsx; src/DocumentUploads.tsx; src/documentTypes.ts; tests/classification.test.mjs; .env.example.

Runtime/docs: scripts/demo_runtime.py; root .env.example; README.md; docs/CONTRACT_GAPS.md; docs/DOCUMENT_CLASSIFICATION_ADDENDUM.md; this verification report. Earlier uncommitted P1 files were preserved separately during DC1 verification. The user subsequently authorized local P1 activation on 7 November 2026; see P1_VERIFICATION.md. DC1 remains enabled.
