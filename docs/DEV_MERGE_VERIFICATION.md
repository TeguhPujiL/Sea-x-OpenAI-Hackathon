# Aris into dev: vendor recommendations and branding

7 November 2026 (Asia/Jakarta). Merge inputs: dev f92ef02 and aris 809c525.
Both histories are preserved. Includes per-proposal result/recommendation cards,
removal of Human review from the summary, case updated timestamps and the branded
ProcureMind favicon.

History conflicts preserve dev's latest audit activity, six step timestamp groups,
authorized paginated activity loading and fallback behavior. Aris's explicit
Last updated timestamp remains visible using the shared Timestamp component.
Ordering includes latest recorded case/audit activity, then creation time/ID for
stable ties; filtering and five-case pagination remain unchanged. Tests from both
branches are retained; timestamp assertions target the Last updated row field.

Executed on the merged tree:

- Frontend Node tests: 74 passed.
- TypeScript typecheck and Vite production build: passed.
- git diff --check: passed.

No backend implementation changed; backend tests were not rerun for this frontend
merge. No Docker redeployment, interactive browser verification or live AI request
was performed for the merge. Earlier local aris deployment checks are separate.
No credentials, .env files or local data are committed.

---

# Aris into dev: 7 November 2026

Merged aris 185a8ab into dev c3738d7, preserving both histories. Includes local
login, persistent Docker testing, case history/category/pagination/delete,
multi-document uploads, footer document-type saves and provider schema fixes.

Conflict resolution keeps dev's audit-gap/provenance labels and diagnostics,
aris's workflow controls, and regression tests from both branches. The two
provider schema adapters share dev's canonical schema module with aris's UUID v4
pattern; the aris import path remains a compatibility re-export. Public shared
schemas, immutable records, authorization and simulation calculations are unchanged.

Executed on the merged tree:

- Full backend pytest: 304 passed (dependency deprecation warnings only).
- Frontend Node tests: 53 passed.
- TypeScript typecheck and Vite production build: passed.
- git diff --check: passed.

No live provider call or Docker redeployment was performed for this merge.
Earlier aris live synthetic/Docker checks are recorded separately in LOCAL_DOCKER.md.
Credentials and local .env are excluded. G01 clean-case completion remains open.

The sections below retain historical verification from earlier integrations.

---

# Current dev merge: Teguh 22569a3 into dev 2e38296

All 36 business operations plus health register. Current schema: openapi.dev.json. Frontend and teammate Simulation/Review/Audit modules are preserved; dev model default gpt-6.1-sol remains. The merge composes all routers and preserves owner-defined 422 errors while replacing only FastAPI default validation schemas.

Executed verification:

- Teguh tests: 100 passed; one existing Starlette/httpx warning.
- Foundation/OpenAPI focused checks: 15 passed again after the final metadata correction.
- Frontend npm run typecheck: passed.
- Full backend suite: NOT PASSING; stopped after three Assurance fixture setup errors. Its migration creates an older analysis_jobs table without input_document_ids_json required by the merged models.
- The final metadata assertion detected a missing simulation 422 response; fixed the OpenAPI filter to preserve all explicitly supplied error schemas.

Pending integration: coordinate Assurance checksum migrations with core migration 0002, finalize seeded jobs only after results exist, and align case-access adapters. No immutable guard, simulator calculation or assurance decision rule was relaxed. This is an integration merge, not a full release or live OpenAI validation claim.

## Previous dev verification

# Fauzan into dev: integration verification

Date: 7 November 2026 (Asia/Jakarta). Requested direction: fauzan -> dev.

Inputs: origin/dev at 10062fb (Aris's shared-persistence simulation API) and origin/fauzan at a2326c5 (immutable human reviews/audit and assurance QA). Both histories are preserved by a merge commit. No changes are pushed to main or fauzan by this merge.

The only textual conflict was backend/tests/test_foundation.py. Resolution keeps dev's method/path/status comparison against the locked contract and requires both simulation and assurance routes. Neither feature's tests were removed.

Two compatibility fixes were required by the combined test suite:

- Pin versioned supplier JSON fixtures to LF using .gitattributes. Windows core.autocrlf had changed the working-copy bytes and broken the manifest check. The original tracked fixture bytes and SHA-256 452fe33326a14d9dccd6f44f2e5c0336243a9243949f5d33f1d9a6e7b60a945e are preserved; the manifest, inputs and prices were not changed.
- Correct simulation OpenAPI to declare the required Idempotency-Key and canonical error envelopes. Missing/invalid headers retain 400 VALIDATION_ERROR. The simulation calculation, persistence and replay policies remain unchanged.

README and application description now name both integrated features. The original ASSURANCE_QA_REPORT.md and openapi.assurance.json remain historical records of the assurance-only branch. The current runtime OpenAPI exposes eight business operations: three simulation and five review/audit operations.

Validation:

- 203 backend tests passed, including a new cross-feature regression that runs the real simulation API against the assurance-migrated SQLite database, replays it, records a review, and reads all three material audit events. Upstream analysis/repair records in that test are explicitly synthetic fixtures.
- All prior simulation and assurance tests remain enabled, covering deterministic prices/counts, schema projections, authorization, idempotency, immutable records, rollback and restart persistence.
- Backend/scripts compilation and the integrated diff whitespace check passed.
- Full-contract preflight registers 8/36 business operations and intentionally returns exit 1. The remaining 28 operations and full product E2E remain integration blockers; this merge is not release approval.
- No frontend sources or dependencies changed, so frontend build checks were outside this merge's relevant scope.

Operational handoff:

Use the explicit assurance migrator for a new shared SQLite database. Apply the repeatable simulation guard installer as documented in services/simulation/INTEGRATION.md; it adds the simulation INSERT OR REPLACE guard without recreating shared tables. Existing unversioned databases still need reviewed adoption. Case authorization adapters for each feature must both be wired to trusted backend authorization; identity alone grants no case access.

G01 remains open and APPROVE_CASE is rejected. G09 replay policies are preserved: simulation returns its original stored envelope while assurance replays resource data with current envelope metadata. Simulation replay therefore retains the original body meta.request_id while the middleware's X-Request-ID header identifies the current transport request; unify this policy with the integration owner before release. Simulation audit details currently use the conservative unknown-event projection in assurance reads, so backend actor ID is available but legacy display-name/role and material details without an approved projection are null/redacted. These are recorded integration limitations, not silently resolved contract changes.


## Audit timeline compatibility fix (7 November 2026)

The frontend rejected real Assurance audit responses because event_hash was required to be a string while the integrated backend returns null (no hash chain implemented). Audit decoding now accepts explicit null hashes and legacy null actor display-name/role metadata, matching current owner OpenAPI. Missing or incorrectly typed fields remain rejected; review reviewer requirements are unchanged. The UI labels unavailable event hashes and historical actor names rather than fabricating provenance. Contract implementation discrepancy is explicitly recorded in CONTRACT_GAPS.md G14; this is not approval of a v1.1 amendment. G01 still blocks clean-case completion.

Executed verification:
- Frontend Node test suite: 31 passed, including real-shaped null-hash audit pagination and invalid-type rejection.
- Backend same-origin demo integration tests: 2 passed, including actual audit response null hashes.
- TypeScript typecheck and Vite production build: passed. Build required execution outside the filesystem sandbox because esbuild could not read parent directories inside it.
- git diff --check: passed.

No simulation calculations, review decisions, stored PDFs, or immutable audit records were modified. No commit, push, or remote deployment was performed for this fix; refresh the local UI to use the rebuilt assets. Remote environments require this patch and a frontend rebuild before refreshing.


## Failed analysis provenance fix (7 November 2026)

A real local job returned FAILED / AI_PROVIDER_ERROR with ai_execution.model=null. The frontend incorrectly required a string, stopped polling with a shape error, and retained its previous QUEUED snapshot. The model decoder now accepts explicit null, consistent with backend ExecutionView and the runtime-provenance policy recorded in CONTRACT_GAPS.md G12. Missing and wrongly typed model fields remain invalid. The UI labels unavailable runtime model provenance without substituting the configured model.

Executed: 32 frontend tests passed; TypeScript typecheck and Vite build passed; the updated decoder successfully read the actual failing local job (HTTP 200, FAILED, AI_PROVIDER_ERROR); localhost:8000 served the new build asset; git diff --check passed. Local Settings reported no configured OpenAI API key (only a boolean presence check; no credentials printed). Live AI success remains unverified and requires backend configuration plus server restart. Existing terminal jobs remain immutable. No commit/push performed.


## Local PDF upload permission repair (7 November 2026)

HTTP 500 on every document upload was reproduced on the real local server. Safe diagnostic logging isolated PermissionError at documents.py when opening a new protected PDF file. The .runtime/pdfs directory was owned by CodexSandboxOffline with owner-only permissions; the restarted server ran as the workspace operator. Granted inheritable Modify to the existing workspace owner's Windows account on that directory only. No global/public grant, document replacement, database reset, or immutable-record rewrite was performed. This is a local ACL repair, not a portable source-code permission bypass; run setup and server under the same Windows identity.

Actual localhost checks: valid PDF 201; malformed PDF 422; non-PDF 415; textless PDF 422; encrypted PDF 400; oversized PDF 413; upload idempotent replay preserved the document ID. Synthetic diagnostic cases/documents were soft-deleted after checks. No existing user documents were modified. New error diagnostics log request ID, exception class and frame locations without exception messages, request bodies, SQL parameters, source lines or locals.


## OpenAI structured-output schema compatibility fix (7 November 2026)

A live isolated request reproduced HTTP 400 invalid_json_schema: Pydantic UUID4 emits format=uuid4, which the provider rejects. Internal schema generation now translates uuid4 to supported uuid for Analysis, Challenge and Repair requests only; local Pydantic UUID4 and evidence authorization/verification remain unchanged. The public API schema, fields, prompt versions, and status enums are unchanged. Official source: https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses (supported string formats).

Executed: 103 tests passed across test_p0.py, test_decisions.py, test_foundation.py, and test_demo_web.py. Regression tests check both provider adapters emit uuid and local validation still rejects non-v4 identifiers. A live adapter request with no documents succeeded using runtime model gpt-6.1-sol, returning valid empty requirements/findings with reported usage. Local server restarted. Retry c161822a-c8cd-472e-9996-52b0f416c210 was created through the API (202) for failed job 9b9df55e-3dcb-4cd1-b763-56d7efe513cb; the original remains immutable. No commit or push performed.


Real-case retry result: COMPLETED in 17054 ms using runtime model gpt-6.1-sol; 19 requirements, finding_ids=[], 22/22 evidence checks passed, no warnings, schema_valid=true. Reported usage: 4310 input / 2176 output tokens. This empty finding result is preserved; G01 clean-case completion remains unresolved.
