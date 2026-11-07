# ProcureMind V4.1 contract lock

Status: **SOURCE VERIFIED / OPEN GAPS RECORDED**. The shared foundation and 28 Teguh-owned case/document/analysis/finding/challenge/repair business operations are implemented on this branch; the full inventory below still includes eight unimplemented teammate contracts. This lock is not release approval. All 39 pages of API Contract & Integration Specification v1.1 (normalized implementation edition), dated 7 November 2026, were read. Section 2.3 controls earlier drafts. Paths, wire names, enum values and codes below are transcribed from the primary contract; unresolved conflicts remain in CONTRACT_GAPS.md.

## Source identity

- File: `8. ProcureMind_V4_1_API_Contract.pdf`.
- Supplied location: `C:/Users/teguh/Downloads/8. ProcureMind_V4_1_API_Contract.pdf`.
- Pages: 39.
- SHA-256: `fcc0388407f9cac2804b71be151f41a444a546bfa5d6648ac2ef33a4a40aecdc`.
- API version: `v1`; REST base path: `/api/v1`; OpenAPI 3.1 (pages 1-3).
- Machine-readable transcription: [contract_snapshot.json](contract_snapshot.json). It is a contract inventory, not an OpenAPI document or application schema implementation.

The execution playbook and user instructions supply named ownership and the separate negative-pack dataset. They do not override the primary API contract.

## Exact business endpoint inventory and success codes

Section 6 specifies **36 method/path pairs**. All paths in this table are relative to `/api/v1`. UUID sample values are rendered as named path parameters; query examples are separated from paths. Every DELETE here returns **200 with an envelope**, not 204.

| Method | Path | Success | Required scope | Idempotency-Key | PDF page |
| --- | --- | --- | --- | --- | --- |
| POST | `/cases` | 201 | `case:write` | Yes | 5 |
| GET | `/cases` | 200 | `case:read` | Not required by Section 3.2 | 6 |
| GET | `/cases/{case_id}` | 200 | `case:read` | Not required by Section 3.2 | 7 |
| PATCH | `/cases/{case_id}` | 200 | `case:write` | Not required by Section 3.2 | 8 |
| DELETE | `/cases/{case_id}` | 200 | `case:delete` | Not required by Section 3.2 | 9 |
| POST | `/cases/{case_id}/documents` | 201 | `document:write` | Yes | 9 |
| GET | `/cases/{case_id}/documents` | 200 | `document:read` | Not required by Section 3.2 | 10 |
| GET | `/documents/{document_id}` | 200 | `document:read` | Not required by Section 3.2 | 10 |
| PATCH | `/documents/{document_id}` | 200 | `document:write` | Not required by Section 3.2 | 11 |
| DELETE | `/documents/{document_id}` | 200 | `document:delete` | Not required by Section 3.2 | 12 |
| POST | `/cases/{case_id}/analyses` | 202 | `analysis:write` | Yes | 12 |
| GET | `/jobs/{job_id}` | 200 | `analysis:read` | Not required by Section 3.2 | 13 |
| GET | `/cases/{case_id}/jobs` | 200 | `analysis:read` | Not required by Section 3.2 | 14 |
| POST | `/jobs/{job_id}/retries` | 202 | `analysis:write` | Not required by Section 3.2 | 15 |
| GET | `/cases/{case_id}/findings` | 200 | `finding:read` | Not required by Section 3.2 | 16 |
| GET | `/findings/{finding_id}` | 200 | `finding:read` | Not required by Section 3.2 | 17 |
| PATCH | `/findings/{finding_id}` | 200 | `finding:write` | Not required by Section 3.2 | 17 |
| POST | `/findings/{finding_id}/dismissals` | 201 | `finding:decide` | Not required by Section 3.2 | 18 |
| POST | `/cases/{case_id}/challenges` | 201 | `challenge:write` | Not required by Section 3.2 | 19 |
| GET | `/cases/{case_id}/challenges` | 200 | `challenge:read` | Not required by Section 3.2 | 20 |
| GET | `/challenges/{challenge_id}` | 200 | `challenge:read` | Not required by Section 3.2 | 20 |
| PATCH | `/challenges/{challenge_id}` | 200 | `challenge:write` | Not required by Section 3.2 | 21 |
| DELETE | `/challenges/{challenge_id}` | 200 | `challenge:delete` | Not required by Section 3.2 | 22 |
| POST | `/cases/{case_id}/simulations` | 201 | `simulation:write` | Yes | 22 |
| GET | `/cases/{case_id}/simulations` | 200 | `simulation:read` | Not required by Section 3.2 | 23 |
| GET | `/simulations/{simulation_id}` | 200 | `simulation:read` | Not required by Section 3.2 | 25 |
| POST | `/findings/{finding_id}/repair-proposals` | 201 | `repair:write` | Yes | 26 |
| GET | `/findings/{finding_id}/repair-proposals` | 200 | `repair:read` | Not required by Section 3.2 | 26 |
| GET | `/repair-proposals/{repair_proposal_id}` | 200 | `repair:read` | Not required by Section 3.2 | 27 |
| PATCH | `/repair-proposals/{repair_proposal_id}` | 200 | `repair:write` | Not required by Section 3.2 | 28 |
| DELETE | `/repair-proposals/{repair_proposal_id}` | 200 | `repair:delete` | Not required by Section 3.2 | 29 |
| POST | `/cases/{case_id}/reviews` | 201 | `review:decide` | Yes | 29 |
| GET | `/cases/{case_id}/reviews` | 200 | `review:read` | Not required by Section 3.2 | 30 |
| GET | `/reviews/{review_id}` | 200 | `review:read` | Not required by Section 3.2 | 31 |
| GET | `/cases/{case_id}/audit` | 200 | `audit:read` | Not required by Section 3.2 | 32 |
| GET | `/audit-events/{event_id}` | 200 | `audit:read` | Not required by Section 3.2 | 32 |

List responses use `data.items` and `data.pagination` containing `limit`, `offset`, `total`. Examples use limit=20, offset=0; audit uses limit=50, offset=0. These examples do not define a maximum or necessarily a default. Finding list shows a `status` filter. Case list excludes deleted records unless `include_deleted=true` and the actor is authorized (page 7). The PDF renders some query separators as `&offset;`; this is a publication artifact, not a new query parameter.

Findings are created by analysis: there is no public finding-create or finding-DELETE endpoint. There are no job PATCH/DELETE, simulation PATCH/DELETE, review PATCH/DELETE or audit-create/PATCH/DELETE endpoints. Retry is a new job; changed simulation input is a new simulation. No repair-scoped review or dedicated submit endpoint is specified: submit uses PATCH on the repair proposal (Section 2.3; pages 5, 28-29).

`GET /api/v1/health` and `GET /openapi.json` are foundation verification requirements from the user/playbook, not among these 36 business contracts. Their exact health payload and the native OpenAPI envelope exception require explicit treatment before foundation implementation; see gaps.

## All Appendix A enums

These are the complete 12 named enum declarations in Appendix A (pages 37-38); preserve their spelling and keep status domains separate.

| Enum | Values | PDF page |
| --- | --- | --- |
| ProcessingStatus | `QUEUED`, `PROCESSING`, `COMPLETED`, `FAILED`, `NEEDS_REVIEW` | 37 |
| CaseStatus | `DRAFT`, `UNDER_ASSESSMENT`, `UNDER_REVIEW`, `REVIEW_COMPLETED`, `ARCHIVED` | 37 |
| AssuranceStatus | `ACTION_REQUIRED`, `READY_FOR_REVIEW`, `REVIEW_COMPLETED` | 37 |
| FindingStatus | `OPEN`, `UNDER_REVIEW`, `RESOLVED`, `DISMISSED` | 37 |
| EvidenceStatus | `VERIFIED`, `UNVERIFIED`, `CONFLICTING`, `INSUFFICIENT` | 37 |
| FindingSeverity | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` | 37 |
| ChallengeStatus | `DRAFT`, `READY`, `CLOSED` | 38 |
| RepairStatus | `DRAFT`, `SUBMITTED`, `APPROVED`, `REJECTED`, `WITHDRAWN` | 38 |
| RepairActionType | `REVISE_REQUIREMENT`, `MAINTAIN_WITH_JUSTIFICATION`, `REQUEST_MORE_EVIDENCE` | 38 |
| ReviewDecision | `APPROVE_DRAFT`, `REQUEST_REVISION`, `REQUEST_EVIDENCE`, `REJECT_DRAFT` | 38 |
| DocumentType | `TOR`, `TECHNICAL_SPECIFICATION`, `OWNER_COST_ESTIMATE`, `TECHNICAL_JUSTIFICATION`, `SUPPLIER_QUOTATION`, `WARRANTY_EVIDENCE`, `EVALUATION_REPORT`, `CONTRACT`, `OTHER` | 38 |
| AnalysisType | `REQUIREMENT_EXTRACTION`, `CONTRADICTION_DETECTION` | 38 |

Additional source declarations: Review has only `COMPLETED` (Section 4.2, page 5); roles are `ANALYST`, `REVIEWER`, `ADMIN`, `AUDITOR` (Section 3.1, page 4). These are not additional named Appendix A enums. Strings such as `AI_ASSISTED`, `IT_EQUIPMENT`, `DOCUMENT_ANALYSIS`, `REQUIREMENT_CONTRADICTION`, `FALSE_POSITIVE`, `TECHNICAL_JUSTIFICATION`, `MARKET_COMPARISON`, and operation/event/resource identifiers occur in examples, but the contract does not enumerate complete closed sets for their fields. Do not invent exhaustive enums from individual examples.

`PROPOSED` labels correction decisions in documentation; it is not a new RepairStatus or ReviewDecision. APPROVE_CASE is absent and must not be introduced.

## Canonical success and error envelopes

Sections 2.1-2.3, page 3; detailed error example on page 39. Every application JSON response uses all four top-level keys.

```json
{
  "success": true,
  "data": {"resource_id": "11111111-1111-4111-8111-111111111111"},
  "error": null,
  "meta": {
    "request_id": "req_001",
    "timestamp": "2026-11-07T03:20:08Z",
    "api_version": "v1"
  }
}
```

The data object above is a generic envelope example, not a new endpoint response. Each route keeps its own Section 6 data shape.

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid fields.",
    "details": [
      {"field": "budget_ceiling_idr", "reason": "must be an integer greater than or equal to 0"}
    ],
    "retryable": false
  },
  "meta": {
    "request_id": "req_999",
    "timestamp": "2026-11-07T04:10:00Z",
    "api_version": "v1"
  }
}
```

Absent optional values are null; empty collections are []. Unknown request fields are rejected. Nested job.error is not the outer envelope error; preserve the job representation (pages 13-15, 34). Validation errors use 400 VALIDATION_ERROR per Appendix B, rather than accepting framework-default validation responses silently.

## Headers, identity and access

Section 3, page 4:

| Header | Contract rule |
| --- | --- |
| Authorization | Bearer token validated by backend in production; optional only in explicitly configured demo mode |
| Content-Type | application/json except multipart document upload |
| Accept | application/json |
| Idempotency-Key | Required for POST cases, document uploads, analyses, simulations, repair proposals and reviews |
| X-Request-ID | Optional client correlation ID; server creates one if absent |

Production uses OAuth 2.0/OIDC. Demo mode must be visibly labeled in the UI and still derive actor/reviewer identity from trusted backend context. Every object lookup is authorized; all references must exist, be accessible, belong to the same case where applicable and not be soft-deleted. Cross-case unauthorized lookup may return 403 or 404 under an explicit anti-enumeration policy (page 37). No public PDF URLs. Redact tokens, secrets and unnecessary raw document text from logs.

The role table provides representative scopes, not a complete role-to-scope mapping. ADMIN cannot rewrite audit history. Do not assume that demo identity alone authorizes every case.

## Idempotency and optimistic concurrency

Section 3.3, page 4:

- Scope keys to actor, method, route and normalized request hash. Reusing a key with a different payload returns 409 IDEMPOTENCY_KEY_REUSED. Section 3.2 supplies the exact mandatory route set above; challenges, dismissals and retries are not silently added to it.
- PATCH and state-changing DELETE carry `expected_version`; stale values return 409 VERSION_CONFLICT.
- DELETE examples explicitly include `reason` and `expected_version` in the JSON body (pages 9, 12, 22, 29).
- Finding dismissal POST explicitly takes `reason_code`, `rationale`, `expected_version` (page 18).
- Review POST explicitly takes `repair_proposal_id`, `decision`, `decision_reason`, **`expected_case_version`** (page 29). Never rename this field to expected_version or accept browser-supplied reviewer/assurance fields.
- Idempotency retention, in-flight requests, replay response policy, normalization details and ordering versus version checks are not fully specified; proposed decisions belong in the gap register.

## Wire fields and immutable boundaries

- Case create fields: title, category, description, quantity, budget_ceiling_idr, currency. Currency is IDR. PATCH allows title, description, quantity, budget_ceiling_idr plus expected_version. Case status is workflow-derived, never freely client-set (pages 5-8).
- Upload multipart fields: **file**, document_type, optional description. Metadata PATCH uses description, document_type, expected_version. Bytes are never replaced; use a new document record/version. Reject deletion when a finalized review references the document; case deletion is blocked if an immutable review exists (pages 9-12).
- Analysis create fields: document_ids, analysis_types, force_reanalysis. Job output uses **status** even though Section 4.1 names the state family processing_status; do not rename this wire field. Retry body uses reason; response includes retry_of_job_id (pages 12-16).
- Findings use **type**, title, summary, confidence, status, evidence_status and **evidence** with document_id/page_number/excerpt/verification_status. Do not rename type to category or evidence to evidence_refs on the wire. AI evidence, severity and source excerpts are immutable; human workflow fields are mutable (pages 16-19).
- Challenge create: finding_id, generation_mode, requested_evidence. Creation returns 201, not 202. Only DRAFT/READY content is editable; only unreferenced DRAFT can be deleted. AI-generated READY example conflicts with the human-readiness note; see gap register (pages 19-22).
- Simulation create: finding_id, baseline.minimum_ram_gb, alternative.minimum_ram_gb, supplier_data_version. Server loads suppliers; response retains engine_version, complete input_snapshot, result, interpretation and created_at. Persist supplier_data_version per Section 8 even though response examples omit it; its wire exposure remains an open gap. No AI numeric results (pages 22-26, 35).
- Repair create: **action_type**, simulation_id, generation_mode. AI output is DRAFT. PATCH may edit/submit a DRAFT using proposed_text, status, expected_version; submission freezes that version. Delete only an unreferenced DRAFT. No invented repair_action field (pages 26-29).
- Reviews are case-scoped immutable human decisions; reviewer snapshot is backend-derived. Server computes assurance_status_after. APPROVE_DRAFT is internal assurance, not statutory approval (pages 29-31, 35).
- Audit is append-only and created atomically with material business writes. Retain actor, request_id, time, resource type/id/version, event type and details; authorized reads are paginated and may redact fields. Hash chaining is tamper-evident, not tamper-proof (pages 32-35).

## Processing and workflow rules

Section 4, pages 4-5; retry restriction on page 16:

- QUEUED -> PROCESSING or FAILED.
- PROCESSING -> COMPLETED, NEEDS_REVIEW or FAILED.
- COMPLETED and NEEDS_REVIEW require a usable result; FAILED has result=null. QUEUED/PROCESSING have result=null.
- Only FAILED or NEEDS_REVIEW jobs may be retried; a retry creates a new QUEUED job and preserves the original. The specific page-16 restriction narrows the generic terminal-retry diagram.
- A COMPLETED analysis can contain a HIGH-severity finding. NEEDS_REVIEW expresses processing/evidence quality uncertainty, not risk severity.
- Poll after 1 second with exponential backoff capped at 5 seconds; stop on COMPLETED, FAILED or NEEDS_REVIEW. status, not progress_percent, determines completion (page 36).
- DISMISSED requires rationale; RESOLVED requires disposition evidence. No contradiction produces finding_ids=[] without fabricated findings.
- APPROVE_DRAFT yields REVIEW_COMPLETED only when no unresolved blocking finding remains. REQUEST_REVISION, REQUEST_EVIDENCE and REJECT_DRAFT yield ACTION_REQUIRED; server evaluates evidence/workflow conditions (page 35).

## Evidence, provenance and validation

Sections 7-8 and Appendix A, pages 34-35, 38:

Strict schema-constrained AI requirements/findings cite document_id, one-based page_number and exact excerpt. Independently normalize whitespace and compare with authorized page text; never silently repair quotations. Unverified usable output ends NEEDS_REVIEW; schema-invalid unusable output ends FAILED with AI_SCHEMA_VALIDATION_FAILED. Persist immutable execution_id, actual provider/model, operation, prompt_version, input_document_ids, schema_valid, evidence_validation_passed, checked/passed/failed counters, warnings, measured latency_ms and provider usage or null. Do not fabricate runtime measurements.

IDs are UUID v4 except human-readable case_number and supplier_ref; request correlation IDs follow the illustrated req_ form rather than UUID resource constraints. Timestamps are UTC with Z. Confidence is 0.0 through 1.0 and never substitutes for evidence status. IDR is integer with nonnegative prices/budgets; the contract explicitly demonstrates a negative signed price delta (see gap). Page number must be within the stored page_count.

Golden synthetic simulation: quantity=50, synthetic-suppliers-v1, supplier-eligibility-v1. SYN-A: 16 GB x 13200000; SYN-B: 16 GB x 13800000; SYN-C: 32 GB x 16500000 IDR/unit. Eligibility uses ram_gb >= minimum_ram_gb; lowest total is min(eligible unit_price_idr * quantity); delta is alternative minus baseline. Baseline 32 GB -> 1 / 825000000; alternative 16 GB -> 3 / 660000000; delta +2 / -165000000. Results are illustrative, not evidence of actual savings, financial loss or wrongdoing.

## Complete Appendix B error catalog

Page 38; retry guidance is reproduced as guidance, not converted into guessed booleans for every condition.

| HTTP | Code | Retry guidance |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | No |
| 401 | `AUTHENTICATION_REQUIRED` | After re-auth |
| 403 | `FORBIDDEN` | No |
| 404 | `RESOURCE_NOT_FOUND` | No |
| 409 | `VERSION_CONFLICT` | After refresh |
| 409 | `INVALID_STATE_TRANSITION` | No |
| 409 | `IDEMPOTENCY_KEY_REUSED` | New key only |
| 413 | `FILE_TOO_LARGE` | No |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | No |
| 422 | `PDF_EXTRACTION_FAILED` | Maybe after new file/OCR |
| 422 | `EVIDENCE_VALIDATION_FAILED` | Human review/new evidence |
| 422 | `SIMULATION_INPUT_INVALID` | After correction |
| 429 | `RATE_LIMITED` | Yes; honor Retry-After |
| 500 | `INTERNAL_ERROR` | Maybe |
| 502 | `AI_PROVIDER_ERROR` | Usually |
| 504 | `AI_PROVIDER_TIMEOUT` | Yes |

AI_SCHEMA_VALIDATION_FAILED and EVIDENCE_EXCERPT_NOT_FOUND also appear in Section 7.2 as nested job error/warning identifiers but are absent from Appendix B; do not invent outer HTTP mappings for them. See gaps.

## Ownership and release state

[OWNERSHIP.md](OWNERSHIP.md) defines the user-assigned team boundaries. Shared models/schemas require Teguh review. [CONTRACT_GAPS.md](CONTRACT_GAPS.md) records all unresolved decisions and labels proposed corrections. [VERIFICATION.md](VERIFICATION.md) separates source-transcription checks from unexecuted foundation/runtime checks.

This branch implements 28 Teguh-owned case/document/analysis/finding/challenge/repair business operations plus health. docs/openapi.teguh-p0.json is the current branch schema; docs/openapi.foundation.json is archived source evidence. The 36-route full-system inventory is not a claim that teammate contracts are implemented. See TEGUH_DECISION_HANDOFF.md for the route matrix and reviewed integration surface. Changes to routes, enums, envelopes, state transitions, evidence or decision semantics require a versioned approved revision and synchronized OpenAPI update (page 39).
