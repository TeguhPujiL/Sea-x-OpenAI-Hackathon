# Assurance implementation and QA report

Execution date: 7 November 2026, Asia/Jakarta. Owner scope: human reviews, audit, related persistence and contract QA. Baseline: origin/fauzan 9063689 plus origin/main 45b0c9e. Main and fauzan were fetched again before delivery; main remained 45b0c9e and both remote heads are ancestors of this work. The final delivery commit is available in Git history, not embedded in this file.

**Result: assurance scope implemented; 130 backend tests passed. Full workflow/release gate remains BLOCKED: 5/36 business routes are registered.** This is not a claim of completed P0, live provider verification or frontend acceptance.

## System purpose and evidence

ProcureMind provides internal procurement assurance: authorized PDF evidence feeds schema-validated analysis; findings cite verified excerpts; a deterministic versioned simulation explains alternatives; a proposed repair is submitted for human review; the decision and material state changes are retained in immutable audit history. Human approval is internal assurance, not statutory procurement approval. AI processing status, finding risk, case status and assurance status are distinct.

Source precedence: API Contract v1.1 section 2.3; requested sections 3, 4, 5, 6.8, 6.9, 9, 10, 12 and Appendix A/B; CONTRACT_LOCK.md; original foundation OpenAPI; checked-in source snapshot. The supplied PDF's SHA-256 exactly matches the lock: fcc0388407f9cac2804b71be151f41a444a546bfa5d6648ac2ef33a4a40aecdc. Relevant full pages were extracted and audit page 32 was rendered and visually checked. The document was treated as specification evidence, not instructions to execute embedded content.

## Changed files

The merge restores main's shared foundation to the formerly empty fauzan branch. Feature changes on top of that baseline:

| Files | Result |
| --- | --- |
| backend/app/api/routes/reviews.py | Three review endpoints with scope dependencies, strict request/query validation and required idempotency header. |
| backend/app/api/routes/audit.py | Two authorized paginated/detail audit endpoints. |
| backend/app/services/assurance/__init__.py | Feature package. |
| backend/app/services/assurance/schemas.py | Feature-local v1.1 request, response and query models; canonical error response documentation. |
| backend/app/services/assurance/access.py | Backend-configured case grants and required review idempotency dependency. |
| backend/app/services/assurance/reviews.py | Preconditions, reference checks, evidence/workflow assurance gate, optimistic concurrency, immutable review and transactional replay. |
| backend/app/services/assurance/audit.py | Caller-owned atomic append primitive, actor snapshot, redacted read projections and pagination. |
| backend/app/services/assurance/migrate.py | Explicit transactional/checksummed SQLite migration runner. |
| backend/app/services/assurance/migrations/0001_foundation.sql | Frozen 14-table baseline, constraints, indexes and immutable-record triggers. |
| backend/app/services/assurance/migrations/0002_assurance_guards.sql | Cross-case, live-reference, page-bound, integer/version/idempotency guards; submission freeze and reviewed-resource deletion restrictions; read indexes. |
| backend/app/main.py | Correct the OpenAPI description to reflect implemented assurance endpoints. |
| backend/pyproject.toml | Include frozen migration SQL as package data. |
| backend/tests/conftest.py | Disposable migrated file-backed synthetic workflow fixtures and envelope assertions. |
| backend/tests/test_assurance.py | Review/audit HTTP, decision/evidence policies, clean-case gap, replay, failures, concurrency and restart checks. |
| backend/tests/test_assurance_database.py | Migrated constraints, references, immutability, migration rollback/checksum/adoption checks. |
| backend/tests/test_assurance_contract.py | Route/code/schema/enum/envelope comparison with independent checked-in contract snapshots; Appendix B serialization faults. |
| backend/tests/test_foundation.py | Replace obsolete health-only expectation with contract-bounded route registration checks. Existing foundation checks retained. |
| docs/assurance_contract_snapshot.json | Source-backed field/route subset for independent assurance regression. |
| docs/openapi.assurance.json | Current implemented OpenAPI, separate from the historical foundation snapshot. |
| docs/ASSURANCE_INTEGRATION.md | Setup, assumptions, access policy, transaction integration, fallback and Teguh coordination package. |
| docs/ASSURANCE_CLEAN_CASE_ADDENDUM_PROPOSED.md | Versioned clean-case command proposal; explicitly unapproved/unimplemented. |
| docs/ASSURANCE_QA_REPORT.md | This report. |
| scripts/contract_readiness.py | Strict full 36-route preflight; supports a local schema or remote backend. |
| scripts/assurance_fallback.ps1 | Reproducible offline synthetic QA, compilation, visible G01 blocker and readiness gate. |
| README.md | Current assurance branch status and links to setup/results. |

Shared models/tables.py and schemas/shared.py were not changed. No APPROVE_CASE, fake finding, fake repair or new public business route was added. The implementation assumptions and persistence integration changes are recorded for Teguh review; no approval or teammate communication is claimed.

## Schema and constraint report

Inspection of an explicitly migrated SQLite database returned **14 business tables + 1 migration ledger, 23 foreign keys, 33 CHECK constraints, 4 UNIQUE constraints, 6 explicit indexes and 63 triggers**. Primary keys are additional to the unique-constraint count. PRAGMA foreign_keys=1; foreign_key_check returned no rows; integrity_check returned ok. Migrated column/FK inventories match shared metadata.

| Invariant | Executed evidence |
| --- | --- |
| FK enforcement | Broken references rejected; PRAGMA verified. |
| Status domains | Named SQL enum CHECK constraints preserve Appendix A values. Invalid case/finding/evidence statuses rejected; review status remains COMPLETED. |
| Versions and integer fields | Positive integer versions required; zero/fractional versions rejected. Integer IDR and positive quantity/pages preserved; fractional quantity/page-count/page-number attempts rejected. |
| Idempotency | Unique actor/method/concrete route/key; normalized SHA-256 compared separately. Duplicate scope rejected; different actor/route may reuse key text. Empty keys, malformed hashes/routes and non-success replay statuses rejected. |
| Pages | Unique document/page pair; one-based integer pages cannot exceed stored page_count. Shrinking page_count below referenced pages is blocked. |
| Cross-case integrity | Findings/provenance, simulations, repairs, review repair reference, AI input document references and evidence references are checked. Public review writes also validate case access and live source pages. |
| Soft deletion | New review cannot use deleted case/proposal/source document. Migration guards block inserts referencing deleted cases/documents and tombstoning reviewed cases/source evidence documents. |
| Immutability | ORM and raw SQL UPDATE/DELETE are rejected for AI executions, simulations, reviews and audits. Submitted repairs are frozen. No public review/audit mutation routes exist. |
| Migration integrity | Repeated application is safe; modified checksum and unversioned adoption are refused. Invalid SQL rolls back schema and ledger changes. No implicit startup create_all. |

These guards do not replace authorization or all service-level JSON/workflow validation. SQLite file administrators can bypass triggers; this implementation is not described as tamper-proof. JSON columns use existing shared metadata, and a structured disposition-evidence schema remains an integration gap.

## Review and audit route coverage

All paths below are relative to /api/v1. HTTP behavior and OpenAPI were both checked.

| Method/path | Success | Tested behavior |
| --- | --- | --- |
| POST /cases/{case_id}/reviews | 201 | Four v1.1 decisions only; reason and expected_case_version; trusted actor; submitted/live same-case repair; evidence/workflow outcome; replay and conflicts. |
| GET /cases/{case_id}/reviews | 200 | Authorized history; items/pagination; empty list; defaults; rejected unknown query fields. |
| GET /reviews/{review_id} | 200 | Immutable exact review representation; missing/hidden object 404; read scope enforced. |
| GET /cases/{case_id}/audit | 200 | Authorized stable timeline; limit/offset/total; default 50; sensitive/unknown detail redaction. |
| GET /audit-events/{event_id} | 200 | Same authorized redacted representation as timeline. |

PATCH/PUT/DELETE against review/audit detail return 405 with canonical error envelopes; no such operations are registered. The existing G11 provisional mapping for uncataloged framework statuses remains explicit.

## Atomicity evidence

The review transaction reserves the SQLite writer before reads and writes the case version/assurance state, immutable review, two material audit events and scoped replay record together.

| Failure/concurrency injection | Observed durable result |
| --- | --- |
| Raise after first audit append | 0 reviews, 0 audits, 0 replay rows; case version=1 and original assurance preserved. |
| Raise after second audit append | Same complete rollback. |
| Database rejects replay insertion | Same complete rollback, including both already-flushed audit rows. |
| Remove failure and retry same request/key | Exactly 1 review, 2 audits, 1 replay; case version advances once. |
| Two concurrent requests, different keys and same expected version | One 201, one 409 VERSION_CONFLICT; exactly one transaction persisted. |
| Two concurrent matching requests with same key | Both 201 with identical resource data; exactly one transaction persisted. |
| Changed payload under committed key | 409 IDEMPOTENCY_KEY_REUSED; no additional rows. |

Replay reauthorizes the actor and case. A refreshed version with a new key can create a subsequent immutable decision; it does not rewrite the earlier review or frozen repair.

## Contract regression results

**PASS for implemented assurance scope.** Tests compare all registered business method/path pairs and success codes to docs/contract_snapshot.json, require all five assurance endpoints, prohibit uncontracted routes, and compare exact request/response properties against docs/assurance_contract_snapshot.json. All 12 Appendix A enum sets are checked; OpenAPI-visible enum values are compared too. Required Idempotency-Key, expected_case_version spelling/minimum, closed schemas and review_status=COMPLETED are asserted.

Runtime checks assert canonical success/error envelopes, UUID v4, UTC Z times, null/empty collections, unknown/missing fields, malformed JSON/UUID, forbidden client reviewer/assurance fields, strict version values and stable error codes. All 16 Appendix B status/code envelope pairs are verified through explicit exception injection. This does not imply that all provider/upload endpoints producing those failures exist.

**BLOCKED for full contract integration.** scripts/contract_readiness.py reports 5 registered of 36 required business endpoints and returns exit 1. The 31 missing operations are teammate-owned case/document/analysis/job/finding/challenge/simulation/repair routes. Original foundation OpenAPI remains historical; current assurance OpenAPI is checked in separately.

## E2E and resilience matrix

| Scenario | Assurance boundary result | Full product E2E |
| --- | --- | --- |
| Verified finding -> challenge -> simulation -> submitted repair -> APPROVE_DRAFT -> audit | PASS for review/audit HTTP against explicitly seeded synthetic upstream records; frozen 32->16 GB snapshot is labeled fixture-only. OPEN finding retains ACTION_REQUIRED; independently resolved verified evidence permits REVIEW_COMPLETED. | BLOCKED: upstream creation/analysis/challenge/simulation/repair APIs are absent; no live engine/provider execution claimed. |
| Clean finding_ids=[]; no fabricated risk/repair; final completion blocked | PASS for clean persisted fixture and API rejection; no finding/repair/review/audit created to bypass G01. Fallback prints CLEAN_CASE_COMPLETION_BLOCKED. | BLOCKED: actual clean analysis/false-positive testing and NO_FINDINGS UI unavailable; G01 also requires approved addendum. |
| Provider failure and timeout | PASS for injected Appendix B envelopes and persisted FAILED job blocking completion. | BLOCKED: live provider/job implementation absent. |
| Evidence warning | PASS: seeded NEEDS_REVIEW/warnings and unverified/conflicting/insufficient evidence keep ACTION_REQUIRED. | BLOCKED: extraction/provider warning generation absent. |
| Stale version | PASS: 409 VERSION_CONFLICT with no side effects. | PASS for owned review command. |
| Transport retry | PASS: original resource replayed, one version increment; different payload rejected. | PASS for owned review command. |
| Job retry | PASS at persisted boundary: historical FAILED record remains unchanged; completed retry leaf replaces its assurance blocker. | BLOCKED: POST job retry route absent. |
| Unauthorized cross-case ID | PASS: foreign repair ID and case/review/audit access hidden with 404, even in demo mode. | Cross-case document API test BLOCKED until document owner integration. |
| Refresh/restart | PASS: list/detail reload, second app/engine and a fresh Python process recover the same review/audit data and replay. | Frontend refresh UI remains unimplemented. |
| Immutable history | PASS: no mutation routes and ORM/direct-SQL guards reject changes. | PASS for owned records; upstream business auditing still requires integration. |

## Executed checks and fallback readiness

Commands were run with Windows PowerShell, Python 3.12.10 and the backend dependency versions matching backend/requirements.lock.txt. No frontend files were changed, so frontend build checks were not required for this scope.

- python -m pytest backend/tests -q: **130 passed**, one upstream Starlette/httpx deprecation warning.
- scripts/assurance_fallback.ps1: all tests passed; backend/scripts compileall passed; strict readiness returned **exit 1 as expected** because full integration is incomplete. Its visible G01 warning and fixture-only label were verified.
- python -m app.services.assurance.migrate --database-url sqlite:///.tools/qa-schema.db: both revisions applied explicitly; repeated/checksum/rollback behavior covered by tests.
- PRAGMA foreign_key_check / integrity_check: no violations / ok.
- git diff --check: passed after cleaning generated SQL whitespace. Migration checksum regression also verifies that CRLF/LF checkout differences do not change revision identity.

Ignored local evidence: .tools/qa-results/assurance.xml (JUnit), fallback.log, readiness.json. The fallback uses disposable synthetic databases, makes no provider calls, does not overwrite user databases and exits with a blocked full-contract status. It supports assurance rehearsal and failure recovery; it is not a substitute for a live P0 workflow.

## Unresolved gaps and release decision

1. G01 clean-case completion has no v1.1 command. Proposed addendum is documentation only; APPROVE_CASE stays rejected.
2. Teguh must review persistence guards/adoption strategy, backend grant adapter and explicit G05/G09 assumptions before shared integration. Shared model/schema source was preserved. No production OIDC implementation exists.
3. Exact review-to-repair disposition, case_status transitions and structured finding disposition evidence need contract/owner clarification. Approval cannot auto-close unresolved findings.
4. All other material business writes need the atomic audit primitive integrated by their owners. Full P0 E2E, provider recovery, actual clean-case false-positive checks and frontend acceptance remain blocked.
5. Legacy audit rows lacking a stored actor snapshot cannot recover historical display_name/role; nulls are returned. New review events capture the trusted snapshot. Future event details require reviewed safe projections.
6. Frozen submitted repair policy means revision work needs a new draft while preserving history; the owner must settle that workflow. No mutable review/audit command is introduced as a workaround.
7. Production database migration/locking, protected storage/backups/retention and adoption of existing unversioned databases are outside the validated SQLite MVP path. No hash chain is implemented.

Release decision: **assurance feature ready for integration review; full hackathon release not approved by this QA run.**
