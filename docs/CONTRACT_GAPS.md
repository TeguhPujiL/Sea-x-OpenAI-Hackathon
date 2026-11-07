# Contract gaps and proposed decisions

Primary source: API Contract v1.1, 39 pages, recorded in CONTRACT_LOCK.md. No item below authorizes a route, enum, schema or workflow change. All correction recommendations are **PROPOSED** until an approved versioned revision.

## G01 - Clean-case review

Status: **OPEN / PROPOSED ADDENDUM**.

Evidence: review request requires repair_proposal_id (page 29); ReviewDecision has only APPROVE_DRAFT, REQUEST_REVISION, REQUEST_EVIDENCE, REJECT_DRAFT (page 38). No APPROVE_CASE exists. Clean analysis must return finding_ids=[] (pages 36-37).

Current rule: do not invent APPROVE_CASE, a finding or a repair proposal. A future UI must show the clean-case completion gap explicitly.

PROPOSED: a versioned clean-case completion command with reviewed access, preconditions, concurrency, assurance and audit semantics. Not implemented.

## G02 - Supplier datasets

Status: **OPEN / PROPOSED DATA-VERSION MAPPING**.

| Dataset | Total offers for fixture | Source / use |
| --- | --- | --- |
| Contract synthetic-suppliers-v1 | 660000000, 690000000, 825000000 IDR | Pages 23-25; golden P0 simulation |
| Separate negative test pack | 710000000, 835000000, 680000000 IDR | User/playbook report; pack not independently inspected; distinct dataset and RAM mapping |

Contract fixture: 50 units; SYN-A 16 GB at 13200000/unit; SYN-B 16 GB at 13800000/unit; SYN-C 32 GB at 16500000/unit. Golden baseline 32 GB -> 1 supplier / 825000000; alternative 16 GB -> 3 / 660000000; delta +2 / -165000000.

Keep versions separate. PROPOSED: assign a distinct version and verified mapping/golden expectations if the negative pack becomes a supplier fixture. Its new version name is not approved here. No fixture or simulator is implemented.

## G03 - Challenge readiness conflict

Status: **OPEN / PROPOSED CLARIFICATION**.

Page 19 shows AI_ASSISTED creation returning READY and human_edits=false, while its contract note says AI output remains a draft until a human marks it READY. Section 4.2 permits DRAFT/READY edits but does not resolve the initial-state conflict.

PROPOSED: return DRAFT for newly generated AI content and use versioned human PATCH to mark READY. This is not silently adopted; the owner must obtain an explicit clarification before freezing this behavior.

## G04 - Signed money delta versus global rule

Status: **OPEN / PROPOSED CLARIFICATION**.

Appendix A.1 page 38 says integer IDR values are >= 0, but pages 23-25 and Section 8 explicitly require result.delta.lowest_total_offer_idr=-165000000.

The lock preserves the reference result. PROPOSED: clarify nonnegative prices/budgets versus signed integer deltas in a revision. Do not clamp the golden delta or use a floating point representation.

## G05 - Incomplete closed sets and transition rules

Status: **OPEN / PROPOSED SCHEMA ADDENDUM**.

Appendix A defines 12 complete named enum sets. It does not enumerate complete sets for category, finding type, generation_mode, requested_evidence, reason_code, job_type, AI operation, audit event_type or resource.type. Examples are not authority to invent additional values or declare complete enums. Review COMPLETED and roles have separate declarations on pages 4-5.

Detailed business transition graphs, review-to-repair disposition and disposition-evidence request shape for RESOLVED are not fully defined. PROPOSED: publish missing field schemas and transition/precondition tables without guessing new values.

## G06 - Error catalog and retryable precision

Status: **OPEN / PROPOSED ERROR ADDENDUM**.

AI_SCHEMA_VALIDATION_FAILED and EVIDENCE_EXCERPT_NOT_FOUND occur in job error/warning examples on page 34 but not Appendix B's 16-code HTTP catalog. Do not invent HTTP statuses for them. Appendix B gives conditional retry guidance for several failures while the envelope uses a boolean retryable; exact per-condition mapping needs clarification. Unknown fields use 400 VALIDATION_ERROR, as explicitly cataloged.

PROPOSED: document nested job error/warning schemas, mappings, retryable rules and malformed/encrypted-upload mappings. Keep current source identifiers intact.

## G07 - Simulation version exposure

Status: **OPEN / PROPOSED RESPONSE CLARIFICATION**.

The simulation request has supplier_data_version (page 22) and Section 8 requires persistence (page 35), but the response examples omit it (pages 23-25). Persist it internally. PROPOSED: explicitly specify response exposure via approved schema revision; do not silently add fields to a locked wire response.

## G08 - Foundation health and OpenAPI

Status: **OPEN / PROPOSED FOUNDATION EXCEPTION**.

User/playbook require GET /api/v1/health and GET /openapi.json, but Section 6's 36-endpoint inventory specifies neither. Section 2.3 says every JSON response uses the envelope; FastAPI's native OpenAPI document is itself JSON.

PROPOSED: define a minimal health data schema and status, and explicitly permit native OpenAPI output outside the application envelope. Do not claim this exception is already in v1.1. Foundation currently implements PROPOSED health data {status: "ok", demo_mode: boolean} with the canonical envelope and serves native OpenAPI outside /api/v1. These support the user-required foundation checks but remain explicitly provisional contract exceptions, not silent amendments.

## G09 - Operational policy details

Status: **OPEN / PROPOSED IMPLEMENTATION DECISIONS**.

Not fully specified: upload byte/page limits, list defaults/maxima, idempotency TTL/replay/in-flight behavior and canonical hashing of multipart bodies, missing-key errors, concurrency-vs-replay ordering, full role grants, exact reviewer preconditions, document storage/retention/malware policy and 403-versus-404 anti-enumeration choice. Required security controls remain binding (page 4); record reviewed policy choices separately from contract amendments.

PROPOSED: document concrete operational policies with Teguh/owners, escalating any changed wire semantics to a versioned revision.

## G10 - Foundation implementation

Status: **FOUNDATION IMPLEMENTED / FEATURE INTEGRATION PENDING**.

The shared FastAPI/SQLite/schema/model infrastructure and React/Vite/TypeScript/Tailwind shell are implemented and verified. The 36 business routes remain empty router ownership boundaries. No PDF/AI service, simulator, review/audit service, business transaction, seed or product flow is pre-implemented. Production OIDC, case authorization, transactional idempotency, optimistic-concurrency commands, durable jobs and migrations remain owner integration work.

The empty demo database initializer is explicit and never runs on application startup. It is not a migration runner. JSON contents and cross-resource case consistency require service validation. Shared SQLite guards forbid updates/deletes for AI executions, simulations, reviews and audit events; they do not implement their business workflows.

## G11 - PROPOSED foundation operational defaults

Status: **OPEN / PROPOSED IMPLEMENTATION DECISIONS**.

A missing/blank Idempotency-Key is mapped by the shared dependency to 400 VALIDATION_ERROR; no new error code is invented. Missing production identity fails closed with 401 until OIDC is implemented. Framework errors not enumerated by Appendix B retain their HTTP status with a provisional VALIDATION_ERROR/INTERNAL_ERROR code. Client correlation IDs are accepted only as printable ASCII up to 128 characters; otherwise the backend generates a req_ identifier. These policies are explicitly PROPOSED, subject to owner review.

## Editorial notes

Page 26 labels repair creation under a duplicated 6.4 Findings heading; the route text, page 5 resource matrix and pages 27-29 establish the repair-proposal path. Query examples contain &offset; / &limit; publication artifacts. These are recorded as editorial issues, not changed route or parameter semantics. Section 7.2's compact job examples are nested job fragments; Section 2.3 still controls the outer envelope.
