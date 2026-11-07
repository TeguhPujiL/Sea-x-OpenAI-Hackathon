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
