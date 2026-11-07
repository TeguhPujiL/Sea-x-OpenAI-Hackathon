# Proposed P1.1 integration

Read P1_CONTRACT_ADDENDUM.md before enabling. Approval of that versioned proposal is pending; no P0 route, enum or Review/Audit/Simulation decision logic is replaced. The user requested both prompts from Prompting P1.pdf on branch teguh. The source default remains off. On 7 November 2026 the user authorized local pilot activation; the current local backend has P1 enabled. Shared-environment approval remains pending. No new supplier portal or P1 frontend was implemented.

## Current local access

Open http://localhost:8000 and log in, then open http://localhost:8000/docs in the same browser. The seven proposed P1 operations are available through Swagger Try it out. P1 results must be read through their assessment endpoints, not interpreted through the P0 workflow UI.

The ignored .runtime/demo-features.json stores p1=true and document_classification=true for the local launcher. This is a local pilot preference, not a shared contract approval. The explicit P1 migration has already been applied to .runtime/demo.db; do not reset that database.

## Explicit setup after approval

Back up the target SQLite database and PDF storage. Apply the existing P0 bootstrap first on a dedicated demo database; do not reset existing records. Run all steps under the same Windows identity as the server to retain protected-PDF write permissions.

```powershell
.\.venv\Scripts\python.exe scripts/demo_runtime.py setup --skip-install
$env:PROCUREMIND_DATABASE_URL = 'sqlite:///' + (Join-Path (Get-Location) '.runtime/demo.db').Replace('\', '/')
.\.venv\Scripts\python.exe -m app.core.p1_migrations
# Only after Integration Lead approval of P1.1:
$env:PROCUREMIND_P1_ENABLED = 'true'
# Stop the existing ProcureMind process before restarting it with this flag.
.\.venv\Scripts\python.exe scripts/demo_runtime.py start
```

For another deployment set its actual database URL explicitly. The migration requires P0 user_version=2 and uses a separate p1_schema_revisions ledger. It adds p1_checks and p1_check_results with same-case/execution FK guards and immutable SQL/ORM protection; it never changes the P0 schema version. It can run twice safely. Disabling the flag hides proposed endpoints without deleting their records. Existing /jobs still exposes retained job history. Supplier self-service roles are deliberately denied until an approved identity/binding design exists.

## Client workflow

1. Use existing login/case APIs and upload PDFs through existing /cases/{case_id}/documents. Correct document types through existing versioned document PATCH before starting P1. No upload byte replacement is allowed.
2. POST the proposed assessment request with a unique Idempotency-Key. The 202 response is the existing JobView, with job_id. A same-key/same-input replay returns the original envelope and does not bill a second generation.
3. Poll GET /jobs/{job_id}, stopping only on COMPLETED, NEEDS_REVIEW or FAILED. Resolve check_id by listing the case's evaluation-checks or supplier-readiness-checks and matching job_id. Job result remains requirement_count/finding_ids; detail belongs to the proposed assessment resource.
4. Read the assessment detail. Show processing status separately from consistency_result and readiness_status. Explicit verified supplier identity, unambiguous numeric evidence, source roles, source dates and excerpts are required before a deterministic substantive check. Missing input is not a misconduct judgment. Contextual explanations are tentative and require a human.
5. Revalidation submits the same supplier/governing requirement IDs plus the selected permitted new supplier-document snapshot and expected_version to /supplier-readiness-checks/{check_id}/revalidations. It creates a new check/job/execution/version, retains the predecessor, and returns changed requirement statuses in changes. Multiple branches from an immutable version are intentional and visible via previous_check_id.
6. Use existing finding detail/PATCH/dismissal/Challenge workflows for human confirmation, rationale-bearing dismissal or requests for additional evidence. Create a new evaluation check after permitted corrected documents for re-evaluation. Do not fabricate a repair proposal to use Assurance; its existing preconditions and G01 still apply.

Frontend integration is owner work. Existing P0 UI recovery selects general document-analysis jobs; before shared activation, distinguish P1 jobs by matching the proposed assessment listings (and ai_execution.operation after completion). A P1 empty finding list must not be presented as a P0 clean-case completion. Do not infer readiness from document presence or progress=100. No frontend files were changed in this task.

## AI and evidence

The real adapter uses configured provider/model, strict JSON Schema and the existing uuid4-to-uuid provider adapter while retaining local UUID4 checks. Prompt/schema version is procuremind-p1-extraction-v1. Canonical requests remain separate from the internal extraction schema. Numeric parser handles explicit English GB/month/year/day/unit notation; ambiguous, conflicting, negative, fractional or unsupported quantities are unresolved. No OCR, signature authentication or external validity authority is claimed. Only independently verified inconsistency items create shared P0 findings. Actual model identifier, usage/null, latency, prompt version and evidence counts are available in the existing job's ai_execution.

Citation checking uses authorized normalized page text; governing criteria must cite criteria documents, observations supplier documents, and recorded decisions the selected report. Every cited assertion is validated, including observations not used in a particular result. Duplicate IDs/content or duplicate criterion/supplier keys are rejected. Worker rechecks case membership and the selected document metadata snapshot before atomic persistence. Input bounds fail without truncating source text. Logs do not receive keys, model output or raw PDF text.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend
npm.cmd run typecheck
```

Live verification is explicitly opt-in, incurs provider usage, and sends generated synthetic PDFs only. Do not run it on sensitive case data:

```powershell
$env:PROCUREMIND_RUN_P1_LIVE = '1'
.\.venv\Scripts\python.exe -m pytest backend/tests/test_p1_live.py -q
```

On Windows use a fresh --basetemp path within .runtime if sandbox and normal-user pytest temp permissions differ, and -p no:cacheprovider if its existing cache belongs to a different identity. Never change access globally or remove user databases to fix test permissions.

OpenAPI snapshot: openapi.p1-proposed.json. Default /openapi.json remains P0; opt-in schema advertises version 1.1+p1.1-proposed and adds exactly seven operations. Existing P0 path definitions are regression-tested as unchanged. The snapshot and addendum are proposals, not a replacement for contract v1.1.
