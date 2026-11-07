> Historical Prompt A handoff (59-test baseline). Challenge/Repair are now implemented; current scope, 100-test results and integration contracts are in [TEGUH_DECISION_HANDOFF.md](TEGUH_DECISION_HANDOFF.md). The current openapi.teguh-p0.json contains 28 business operations plus health; remaining-work statements below describe the earlier phase-A snapshot.

# Teguh P0 case, document, analysis and finding handoff

Branch: teguh. Source of truth: API Contract v1.1, Section 2.3, docs/CONTRACT_LOCK.md and the checked source hash. This implements the requested phase-A backend; challenge/repair remain skeletons. No Simulation or Review/Audit router/service was modified or introduced.

## Implemented route matrix

| Method | Path | Success | Scope | Idempotency-Key |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/cases` | 201 | `case:write` | Required |
| GET | `/api/v1/cases` | 200 | `case:read` | Not required by v1.1 |
| GET | `/api/v1/cases/{case_id}` | 200 | `case:read` | Not required by v1.1 |
| PATCH | `/api/v1/cases/{case_id}` | 200 | `case:write` | Not required by v1.1 |
| DELETE | `/api/v1/cases/{case_id}` | 200 | `case:delete` | Not required by v1.1 |
| POST | `/api/v1/cases/{case_id}/documents` | 201 | `document:write` | Required |
| GET | `/api/v1/cases/{case_id}/documents` | 200 | `document:read` | Not required by v1.1 |
| GET | `/api/v1/documents/{document_id}` | 200 | `document:read` | Not required by v1.1 |
| PATCH | `/api/v1/documents/{document_id}` | 200 | `document:write` | Not required by v1.1 |
| DELETE | `/api/v1/documents/{document_id}` | 200 | `document:delete` | Not required by v1.1 |
| POST | `/api/v1/cases/{case_id}/analyses` | 202 | `analysis:write` | Required |
| GET | `/api/v1/jobs/{job_id}` | 200 | `analysis:read` | Not required by v1.1 |
| GET | `/api/v1/cases/{case_id}/jobs` | 200 | `analysis:read` | Not required by v1.1 |
| POST | `/api/v1/jobs/{job_id}/retries` | 202 | `analysis:write` | Not required by v1.1 |
| GET | `/api/v1/cases/{case_id}/findings` | 200 | `finding:read` | Not required by v1.1 |
| GET | `/api/v1/findings/{finding_id}` | 200 | `finding:read` | Not required by v1.1 |
| PATCH | `/api/v1/findings/{finding_id}` | 200 | `finding:write` | Not required by v1.1 |
| POST | `/api/v1/findings/{finding_id}/dismissals` | 201 | `finding:decide` | Not required by v1.1 |

Health remains GET /api/v1/health -> 200. The current generated schema is [openapi.teguh-p0.json](openapi.teguh-p0.json): 18 business operations plus health. The original openapi.foundation.json is an archival foundation snapshot, not the current API. Validation uses canonical 400 VALIDATION_ERROR; upload may return 413 FILE_TOO_LARGE, 415 UNSUPPORTED_MEDIA_TYPE and 422 PDF_EXTRACTION_FAILED. Stale expected_version returns 409 VERSION_CONFLICT.

Finding wire names remain **type** and **evidence**, per Section 6.4. The logical category is stored in Finding.type; individual references live in evidence_refs. They are not silently renamed to category/evidence_refs in JSON. Public request and response declarations are in schemas/p0.py. Central presenters validate responses even though JSONResponse bypasses FastAPI's normal response filtering.

## Changed implementation files

- api/routes/cases.py, documents.py, analyses.py, jobs.py, findings.py: authorized contract endpoints.
- api/presenters.py and schemas/p0.py: exact wire fields, closed request/output models, canonical response metadata integration.
- core/config.py, transactions.py, upload_limit.py, access.py, migrations.py, init_db.py and main.py: operational settings, serialized atomic writes, ACLs, idempotency/replay, guarded multipart size, explicit migrations, provider wiring and startup recovery.
- models/access.py, integrity.py, tables.py and __init__.py: backend case membership, job/source integrity and the minimal shared schema additions described below.
- services/documents/pdf.py: bounded PDF validation/extraction; services/ai/provider.py and jobs.py: real OpenAI adapter and independently validated immutable execution results.
- tests/test_p0.py plus updated test_foundation.py: acceptance, security, persistence and contract regression for this owned scope.
- .env.example, README.md, AGENTS.md, contract gap/lock status, verification and file inventory: current setup and integration notes.

## Migration and schema summary

Run `python -m app.core.migrations` with the backend installed and database URL configured. Initialization is explicit; app startup never calls create_all. This is SQLite migration 0001 (PRAGMA user_version=1), not a production migration framework. Back up existing DBs first.

- New case_access table: case_id + backend actor_id composite primary key. Case creation grants only the creator membership. No client-facing grant endpoint.
- analysis_jobs adds input_document_ids_json, requirements_json, actor_id and request_id. Exact source inputs and extracted requirements persist without changing public job fields.
- ai_executions adds requested_model. Actual model is nullable when no provider response was received; requested configuration is kept separately, never misrepresented as measured runtime provenance.
- Migration upgrades the former NOT NULL AI model column via a data-preserving table rebuild, adds missing job columns, retains existing UUIDs/rows, reinstalls immutable guards and checks foreign keys before committing. A legacy job's missing actor/document provenance is not fabricated; an operator must review/backfill before reuse.
- Existing Simulation, Review and Audit table definitions and their immutable guards are retained. No numeric simulation or review decision service is supplied.
- SQLite triggers and ORM checks protect terminal jobs, allowed transitions, result/state consistency, immutable PDF identity, stored pages/evidence references and AI-authored finding provenance. AI executions, simulations, reviews and audit events remain append-only.

## Transaction and integration interfaces

core/transactions.py owns the minimal shared atomic audit writer; it writes shared AuditEvent declarations but does not implement Fazhima's audit service or routes. Owner services can replace/integrate this helper while preserving the same transaction boundary. Case/document/finding writes and analysis enqueue/finish/retry commit their audit rows in the same SQLite transaction.

Idempotency scope: actor + method + concrete route + key; hash covers normalized JSON or multipart logical fields (SHA-256, filename, document_type, description), not the random multipart boundary. BEGIN IMMEDIATE serializes writers before key/version checks. Same request replays the stored full envelope/status without another business/audit write; changed payload returns 409 IDEMPOTENCY_KEY_REUSED. Replay retains the original envelope metadata; X-Request-ID response header correlates the current transport request. Idempotency records are retained; no silent TTL/eviction is added.

Trusted local `python -m app.core.access --case-id <uuid-v4> --actor-id <uuid-v4>` grants membership only under configured ADMIN context with case:write. It records CASE_ACCESS_GRANTED atomically. It is not a browser API. API scopes and case membership are both required; ADMIN does not automatically bypass API case access. Production OIDC remains an integration dependency.

## PDF and evidence behavior

Multipart accepts only file, document_type and optional description; duplicate/unknown fields fail. Request and file byte caps apply before extraction. MIME/signature, encryption including owner-only encryption, parser repair/malformed state, pages and usable text are checked. Textless PDFs return PDF_EXTRACTION_FAILED; OCR is not provided. PyMuPDF calls are serialized with a parser lock. No raw text is retained beyond extraction; one-based normalized pages persist.

Bytes are saved with a generated UUID filename using exclusive creation, flushed before DB commit, never exposed through a public URL and never replaced. On transactional failure the new file is removed; an existing colliding filename is never deleted. Soft deletion retains bytes/pages. Finalized-review evidence and active-analysis references block document deletion. A reviewed case cannot be deleted. Protected storage still needs deployment filesystem ACLs, retention and malware controls; crash-time orphan-file cleanup and process-level parser memory/time isolation remain operational follow-up.

Each AI assertion references an authorized input document and an existing one-based page. Whitespace is normalized without changing case, punctuation or numbers. Matching excerpts are VERIFIED. Existing-page mismatches remain UNVERIFIED and finish a usable result as NEEDS_REVIEW. Cross-case/unknown/out-of-range references fail the job with EVIDENCE_VALIDATION_FAILED and produce no findings. Original quotations and provenance are not silently repaired or edited.

## Real AI adapter and failure modes

The OpenAI Responses adapter sends strict JSON Schema for requirements and findings, uses the configured model/key, store=false and no automatic SDK retries, and captures the model returned by the provider plus usage/null. See [official OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs). Schema/prompt version: procurement-analysis-v1; operation EXTRACT_AND_COMPARE. It supports the requested subset of analysis_types and rejects unrequested result categories.

| Condition | Job outcome |
| --- | --- |
| Valid schema/citations, no unresolved warning | COMPLETED; HIGH findings are allowed |
| No contradiction | COMPLETED with finding_ids=[]; no fabricated finding |
| Usable result, excerpt not found on existing authorized page | NEEDS_REVIEW + EVIDENCE_EXCERPT_NOT_FOUND warnings |
| Invalid schema/refusal/empty or truncated unusable output | FAILED / AI_SCHEMA_VALIDATION_FAILED |
| Inaccessible or invalid citation location | FAILED / EVIDENCE_VALIDATION_FAILED |
| Provider timeout | FAILED / AI_PROVIDER_TIMEOUT, retryable |
| Provider/API rate limit | FAILED / RATE_LIMITED, retryable |
| Missing config or nontransient provider rejection | FAILED / AI_PROVIDER_ERROR; missing config and 4xx rejection are not retryable until corrected |
| Unexpected worker failure | FAILED / INTERNAL_ERROR, generic sanitized message |

Measured latency, schema flag, evidence counters, warnings, actual provider model when known, requested model separately and usage/null persist in immutable AI execution records. Raw responses, secrets and unnecessary raw documents are not logged or persisted. No corruption/legal decision or numeric impact field is requested from the model. Test doubles exist only in tests; there is no live-response fallback.

A new retry is allowed only from FAILED/NEEDS_REVIEW and preserves its original terminal job/execution. In-process BackgroundTasks are for a **single-worker hackathon deployment**, not a durable production queue. On startup, interrupted QUEUED/PROCESSING jobs with known backend actor provenance become FAILED / INTERNAL_ERROR with an atomic audit entry; the user can retry to a new job. No nonexistent provider execution is fabricated for interrupted work. Do not run multiple Uvicorn workers with this recovery policy.

## Verification

`python -m pytest backend/tests -q`: **59 passed**, one existing Starlette/httpx deprecation warning. Tests cover UUID/UTC/IDR/envelopes, 18 contract route/status pairs, closed schemas, PDF rejection classes, protected bytes/pages, idempotent replay and concurrent duplicate requests, stale versions, cross-case access and indistinguishable hidden-resource errors, verified/unverified/invalid citations, real adapter request construction, no-finding output, job transitions/terminal immutability/retry, rollback atomicity, review-reference deletion guards, restart persistence/recovery, source immutability, legacy migration and OpenAPI reference resolution.

A separate temporary Uvicorn HTTP smoke test passed health 200, case 201, valid PDF upload 201, analysis 202, job polling and OpenAPI 200. With AI deliberately unconfigured, the job failed explicitly with AI_PROVIDER_ERROR/model=null and no findings. Temporary server/database/storage were removed afterwards.

**Live OpenAI inference was not executed**: credentials/model/account access are not configured for a live run. SDK request construction and job failure/quality paths were tested with isolated provider doubles. No simulation/review/audit feature or frontend tests are claimed.

## Remaining dependencies and known limits

- Configure API key/model and a visible trusted demo identity for the integrated UI; perform live OpenAI validation with authorized synthetic PDFs.
- Frontend Lead integrates these real endpoints and polling; Aris integrates simulation; Fazhima integrates review/audit reads and atomic assurance commands. Shared-model additions need owner review during merge.
- Challenge/repair remain skeletons; finding RESOLVED is conservatively blocked until a disposition-evidence shape is approved. DISMISSED must use its rationale-bearing command.
- Existing contract gaps remain: no APPROVE_CASE/fake clean-case proposal, separate supplier versions, challenge readiness, signed simulation delta and health/OpenAPI exception. All operational/default and schema clarifications remain explicitly PROPOSED.
- Operational defaults are not silently declared contract rules: 10 MiB PDF, 100 pages, 500000 extracted characters, 100000 AI input characters, list limit default20/max100, 60-second provider timeout, ADMIN-only deleted-case reads, no automatic reanalysis-result cache even when force_reanalysis=false. New distinct idempotency keys create preserved executions; no prior execution is overwritten.
- Successful upload returns document processing_status=COMPLETED because validation and extraction are synchronous; the QUEUED sample in v1.1 is illustrative in value. This policy is explicitly recorded for owner review.
