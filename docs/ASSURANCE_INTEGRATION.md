# Assurance implementation and integration handoff

This branch starts at origin/fauzan 9063689 (empty reset) and merges the shared foundation from origin/main 45b0c9e. It implements review/audit ownership only. The source PDF provided during QA has the locked SHA-256 fcc0388407f9cac2804b71be151f41a444a546bfa5d6648ac2ef33a4a40aecdc. Pages 3-5, 29-33, 35-39 were read for this work; the existing contract lock records the full source review.

## Runtime setup

Run from the repository root after installing backend requirements. The application never runs migrations or create_all at startup.

```powershell
.\.venv\Scripts\python.exe -m app.services.assurance.migrate
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend
```

The explicit migration command uses PROCUREMIND_DATABASE_URL or --database-url. It installs two frozen SQLite SQL revisions in one transaction, records checksums, rejects changed/unknown applied revisions and safely repeats without schema writes. Existing unversioned tables are refused without modification. Back up such a database and coordinate a reviewed adoption migration; do not run init_db followed by this migrator against the same database. The package includes SQL resources through backend/pyproject.toml. Non-SQLite migration and transaction locking are deliberately unsupported until implemented and tested.

Demo requests require backend settings PROCUREMIND_DEMO_MODE=true, PROCUREMIND_DEMO_ACTOR_ID=<UUID v4>, an appropriate display name/role, and explicit PROCUREMIND_DEMO_SCOPES. Set scopes to the JSON array ["review:decide","review:read","audit:read"] for a reviewer exercising all five routes. Role names grant no scopes. Production identity remains fail-closed until Teguh integrates OIDC.

Case authorization is additional to scopes. PROCUREMIND_ASSURANCE_CASE_GRANTS is a backend-only JSON object mapping actor UUID strings to arrays of authorized case UUID strings. Example shape: {"<trusted-actor-uuid>":["<authorized-case-uuid>"]}. There are no wildcard grants and no public grant-writing endpoint. Empty/missing grants authorize no cases. get_case_grants is a dependency adapter that Teguh can replace with the shared authorization implementation. Request headers/bodies cannot populate grants. Do not put these settings in VITE variables. The frontend owner still must visibly label demo identity.

Reads hide unauthorized objects using 404. Authorized audit/review history remains readable for a soft-deleted case; new review writes require a live case and references. Existence checks alone do not grant case access. Replay also rechecks current grants.

## Explicit implementation assumptions

The user authorized proceeding on assumptions while no further shared schema clarification was available. These are conservative implementation policies for G05/G09, not approved amendments to v1.1. Teguh should review them during integration.

| Concern | Implemented policy |
| --- | --- |
| Review preconditions | Case must be UNDER_REVIEW, repair must be SUBMITTED, and all referenced provenance/simulation/evidence resources must belong to that live case. DRAFT/APPROVED/REJECTED/WITHDRAWN repairs are not reviewable. |
| Repair disposition | Preserve the submitted version and its status; do not mutate its content or auto-resolve a finding. A later decision is a new immutable review at the refreshed case version. v1.1 does not state that one repair may have only one review. |
| Case status | Update assurance_status and increment case.version; preserve case_status because exact review-to-case transitions are unspecified. |
| Meaningful reason | Trim; require 10-4000 characters, at least three whitespace-separated words and six alphanumeric characters. No sensitive reason text is copied into audit details. |
| Blocking findings | Every OPEN/UNDER_REVIEW finding blocks completion regardless of severity. RESOLVED requires a nonblank disposition note; DISMISSED requires nonblank rationale in the foundation resolution_note field. Exact structured disposition evidence remains G05. |
| Evidence gate | Non-dismissed findings require VERIFIED evidence, valid immutable execution flags, live same-case source pages and independently matching whitespace-normalized excerpts. No evidence is promoted automatically. |
| Processing gate | Current retry-chain leaves must be COMPLETED with no warnings; historical failures superseded by a completed retry do not block. No job is changed by a review. |
| Decision outcome | REQUEST_REVISION, REQUEST_EVIDENCE and REJECT_DRAFT always produce ACTION_REQUIRED. APPROVE_DRAFT produces REVIEW_COMPLETED only if all gates pass; otherwise ACTION_REQUIRED. No finding/repair is fabricated for clean cases. |
| Replay | Scope uniqueness to actor, POST, concrete case route and key; compare SHA-256 of canonical validated JSON. Matching retry returns original 201 resource data with fresh envelope meta/request ID before stale-version/state checks. Changed payload gives 409 IDEMPOTENCY_KEY_REUSED. No automatic TTL/purge. |
| Idempotency limits | Required nonblank key, maximum 200 characters; missing/invalid keys give 400 VALIDATION_ERROR. Required header is reflected in OpenAPI. |
| Pagination | Reviews default 20, audit default 50; limit 1-200, offset >=0. Unknown query fields rejected. Stable chronological ordering uses timestamp then UUID. Defaults/maxima are operational policies. |
| Audit projections | Allowlist scalar material details per known event type; unknown event details are hidden. Actor snapshot is stored under reserved details._actor and projected as actor. Legacy events without a snapshot expose null display_name/role, never guessed identity. |
| Hashes | No hash chain is implemented; previous_hash/event_hash are null. Protected storage and access controls remain necessary. |

## Atomicity and other owners

create_review owns a SQLite BEGIN IMMEDIATE transaction before its first read. It checks authorization, replay and expected_case_version, conditionally increments the case version, inserts the immutable review, appends REVIEW_COMPLETED and CASE_ASSURANCE_CHANGED events, and inserts replay data before committing. A response is returned only after commit. The second event records the case's material status/version write, including when the assurance status itself remains unchanged.

Other owners can call services.assurance.audit.append_audit inside their own business transaction. It flushes and never commits, so exceptions roll back with the caller. It captures backend actor ID/snapshot, request ID, UTC timestamp, resource type/ID/version and material details. It requires an active caller-owned transaction. The primitive does not automatically audit teammate-owned commands; integration must call it on each material write. Register each new event's safe read projection after reviewing sensitive fields. No claim is made that upstream writes are already audited.

The SQL revisions add validation triggers and read indexes to the foundation schema without changing shared model/schema source or adding shared columns. SQLite continues to require database-file/backup access protection; immutability triggers do not protect against an administrator replacing a file or removing triggers.

## Teguh coordination package

No shared models/tables.py or schemas/shared.py changes were made. This handoff documents coordination items; no message was sent or approval inferred.

- Review the frozen baseline migration, cross-case/page/soft-delete guards, submitted-repair freeze, new indexes, package-data entry and backend case-grant adapter before merging into shared persistence.
- Decide G05/G09 review preconditions, structured finding disposition, subsequent review behavior, repair disposition and case_status transitions. Current conservative behavior may keep an otherwise accepted draft ACTION_REQUIRED until the finding owner records valid disposition.
- Replace the feature-local demo grants with shared case authorization and production OIDC. All referenced-resource lookups must use it.
- Coordinate atomic audits for case/document/analysis/finding/challenge/simulation/repair commands. Existing schema JSON payloads do not enforce every business invariant; services still must validate them.
- Source raw PDF pages and retained historical snapshots must be protected against unauthorized mutation/deletion. The reviewed-document tombstone guard covers evidence references through reviewed repair findings, not an unspecified full frozen document-set snapshot.
- Specify an adoption migration for existing unversioned databases and a production database locking/migration plan. SQL revisions are reviewed integration candidates, not production deployment approval.
- Review the clean-case addendum in ASSURANCE_CLEAN_CASE_ADDENDUM_PROPOSED.md. No candidate route or APPROVE_CASE appears in the implementation/OpenAPI.

## Fallback and recovery

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/assurance_fallback.ps1
# Read-only preflight against an integrated backend:
.\.venv\Scripts\python.exe scripts/contract_readiness.py --base-url http://127.0.0.1:8000
```

Fallback runs all backend tests and compilation, using disposable migrated synthetic databases. It needs no provider credentials or requests, never resets a user's database, and prints G01 explicitly. It is an offline QA replay, not a live AI demonstration. JUnit and route readiness are written to ignored .tools/qa-results. Exit 1 after successful tests means the full contract gate is blocked; inspect readiness.json. Script execution does not convert unimplemented workflows into passing tests.

Provider failure recovery is tested only at the assurance boundary using persisted synthetic FAILED/NEEDS_REVIEW/retry records and fault-injected Appendix B envelopes. Live provider calls, job retry commands, clean-analysis false-positive behavior and UI recovery need owner integration plus authorized test PDF datasets. Their full E2E execution is blocked on this branch.
