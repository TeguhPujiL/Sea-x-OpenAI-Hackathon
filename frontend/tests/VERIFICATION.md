# Frontend verification — 7 November 2026

## Executed checks

| Check | Result |
| --- | --- |
| npm ci using the existing lockfile | PASS; 136 packages installed, no manifest or lockfile edit |
| TypeScript typecheck | PASS |
| Production Vite build with explicit VITE_API_BASE_URL=/api/v1 | PASS |
| Node frontend tests | PASS: 30 tests, 0 failures |
| git diff --check | PASS for changed tracked frontend source |
| SHA-256 comparison of pre-existing tracked source | Only frontend/src/main.tsx and frontend/src/styles.css changed; no existing file removed |
| Backend, shared schemas, contract docs, package manifests and README | Unchanged by this task |

The runtime is Node.js 24.12.0/npm 11.6.2 on Windows. Node test subprocesses and Vite/esbuild required execution outside the sandbox after EPERM. The installed versions are selected by the existing package lock; no dependency update was made.

## Automated coverage

- Valid multipart upload, server rejection with PDF_EXTRACTION_FAILED, and no fabricated finding/document after rejection.
- Canonical envelope/resource validation, exact expected success statuses, non-JSON failure, development-only API base fallback, and explicit production configuration.
- UUID idempotency scope, normalization, immutable multipart metadata, key reuse only for unresolved transport retry, and fresh keys for new operations.
- Polling delay sequence 1/2/4/5/5 seconds; no completion inferred from 100 percent progress; all three terminal outcomes and cancellation.
- No automatic finding fetch before terminal status; explicit refresh permitted.
- Zero findings and the clean-case completion gap, including retained real NEEDS_REVIEW warnings.
- Evidence excerpts, one-based pages, document identifiers, verification statuses, and out-of-range metadata warnings.
- Server-returned golden simulation values, signed deltas, provenance gaps and disclaimers.
- DRAFT save/submission contracts, read-only submitted UI, stale version error precision, authoritative refetch and reconciliation markup.
- Identifier-only session storage, denied storage, malformed recovery, cross-case rejection, pagination and refresh reconstruction.
- Immutable review display, trusted server reviewer snapshot, audit provenance, and full synthetic contract-client journey through upload/assessment/challenge/simulation/repair/review/recovery.
- Semantic controls, current step, skip link, labels and status announcements via server-rendered React markup.

Fixture transport and rendered markup tests do not exercise the complete interactive browser/controller lifecycle. They do not prove real provider calls, backend authorization, independent PDF excerpt validation, database atomicity, or persistence after backend restart.

## Browser and integration limitations

The local test server was visibly labelled SYNTHETIC FRONTEND TEST FIXTURE. An initial asset-path issue in that test server was corrected. Browser-control then stopped because it could not confidently determine the active Windows browser URL; no further UI actions were attempted. The owned test server was stopped.

Browser visual layout, interactive keyboard traversal, mobile rendering, and browser console verification remain unverified. Static semantic checks and selected computed text contrast checks are not a formal WCAG audit.

The real backend P0 journey remains untested and unavailable in the current foundation, whose OpenAPI exposes health only. G03 challenge readiness is displayed as returned; no readiness amendment is adopted. G07 omitted supplier version remains visible as a provenance gap. Clean-case completion remains blocked without fabricated resources or decisions.

The pre-existing README merge conflict is untouched. No staging, commit, branch merge, push, or deployment was performed.

## Reproduce

From frontend/:

```powershell
node --import ./tests/register.mjs --test ./tests/workspace.test.mjs
$env:VITE_API_BASE_URL = '/api/v1'
npm.cmd run build
npm.cmd run dev
```
