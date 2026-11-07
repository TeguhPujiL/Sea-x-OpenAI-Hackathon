# 06. Assure: nullable audit provenance fix

Investigated on dev 3bcec7b, 7 November 2026 (Asia/Jakarta).

## Cause

The message `audit.event_hash does not match API Contract v1.1.` comes from the frontend resource decoder, not an HTTP error returned by the backend.

After a repair exists, loadWorkspace fetches reviews and the audit timeline for step 06. Assure. The backend AuditView schema and current docs/openapi.dev.json explicitly permit event_hash and previous_hash to be string or null. The audit writer currently leaves both null because no hash chain is implemented. The frontend incorrectly declared event_hash as a required string and checked it with text rather than nullable(text), rejecting a valid response. This can happen during refresh after the review has already committed successfully.

A related mismatch exists for legacy audit actors: the backend retains the trusted actor_id but returns null display_name/role when no historical snapshot exists. The frontend reused the stricter review Actor schema, which could cause audit.actor to fail before reaching the hash field.

Prior frontend tests used a fabricated string hash for every audit fixture, hiding the unchained-backend case. The default synthetic fixture now uses null, matching actual backend serialization.

## Change

- frontend/src/contracts.ts: accept explicit null event_hash; retain a required field and reject undefined/numeric/boolean/object/array values. Add an audit-specific actor type/decoder permitting null labels while still requiring UUID v4 actor_id. Review identity validation remains strict.
- frontend/src/WorkspaceView.tsx: render a null hash as Not recorded, a missing actor name as Actor name not recorded, and include the server actor UUID in provenance details. Stored string hashes still render unchanged.
- frontend/tests/fixtures.mjs: default to explicit null hashes.
- frontend/tests/workspace.test.mjs: cover null/stored hashes, malformed/missing fields, legacy actor labels, strict review identity, and a complete step-06 workspace refresh/render with nullable audit provenance.

Backend wire schemas, existing audit rows, review decisions and transaction boundaries are unchanged. No fake hash, hash chain, actor label or history backfill is created. Missing hash values are not evidence that an event was tampered with, and no tamper-proof claim is made.

## Verification

- Reproduced the exact event_hash ShapeError before the fix. Three new audit/Assure tests failed against the original decoder.
- All 35 frontend tests pass after the fix, including the full synthetic workflow and post-review refresh.
- npm run typecheck: pass.
- VITE_API_BASE_URL=/api/v1 npm run build: pass. The first build was denied filesystem access by the sandbox; rerunning with the required permission passed.
- A disposable SQLite database was initialized using the current core migration runner. Real audit list/detail API responses for both current and legacy synthetic events were serialized, then successfully decoded by the actual frontend contracts module. All event hashes remained null; the legacy actor labels remained null. No provider requests or user database writes were made.
- npm ci used the existing lockfile; no dependency manifest/lock change. Frontend runtime: checksum-verified Node 22.23.4.
- Broader backend run: 194 passed, 97 setup errors. The existing assurance conftest still applies the old assurance-only schema, then inserts current AnalysisJob rows containing input_document_ids_json; SQLite rejects the missing column. This predates the frontend fix and is separate from the Assure decoder error. The focused real-API check used the current core migrations successfully. Full backend regression is therefore not reported as green.

Ignored local evidence is under .tools/qa-results: audit-frontend-before.log, audit-frontend-after.log, audit-api-wire.json and audit-fix-backend.log/XML. The API sample contains disposable synthetic test data only.

## Recovery

Update dev, rebuild the frontend, reload the application and use Refresh resources in Assure. An earlier review may already exist if only its follow-up audit refresh failed; the corrected decoder loads that persisted review and timeline. No resubmission or data migration is needed for this error.
