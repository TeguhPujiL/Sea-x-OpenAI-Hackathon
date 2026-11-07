# Frontend integration handoff

Source: API Contract v1.1 (39 pages), SHA-256 `fcc0388407f9cac2804b71be151f41a444a546bfa5d6648ac2ef33a4a40aecdc`.

This frontend consumes the PDF contracts. The checked-in foundation OpenAPI currently contains health only. Backend business integration is pending; frontend fixture tests do not establish a working real-backend journey. No business response or supplier result is hard-coded in application code.

## Local commands

Run from the application repository's `frontend` directory with Node.js 22+:

```powershell
npm.cmd ci
npm.cmd run typecheck
node --import ./tests/register.mjs --test ./tests/workspace.test.mjs
$env:VITE_API_BASE_URL = '/api/v1'
npm.cmd run build
npm.cmd run dev
```

Vite proxies `/api/v1` to `http://127.0.0.1:8000`. Its existing configuration is unchanged. Development alone defaults to `/api/v1`; production requires an explicit `VITE_API_BASE_URL` at build time. Missing production configuration displays a configuration error. Do not put provider secrets or reviewer identity in browser configuration.

Test-only browser verification, after building: `node tests/browser-fixture.mjs`, then open `http://127.0.0.1:18742`. The server visibly labels its synthetic fixture mode and is never imported into the application. Stop it with Ctrl+C. These tests are distinct from integrated backend acceptance.

## Endpoint coverage

| Method | Path | Expected HTTP |
| --- | --- | --- |
| GET | /health | 200; provisional foundation schema |
| POST | /cases | 201 |
| GET | /cases/{case_id} | 200 |
| POST, GET | /cases/{case_id}/documents | 201, 200 |
| POST | /cases/{case_id}/analyses | 202 |
| GET | /jobs/{job_id} | 200 |
| GET | /cases/{case_id}/jobs | 200 |
| POST | /jobs/{job_id}/retries | 202 |
| GET | /cases/{case_id}/findings | 200 |
| POST | /cases/{case_id}/challenges | 201 |
| GET | /challenges/{challenge_id} | 200 |
| POST | /cases/{case_id}/simulations | 201 |
| GET | /simulations/{simulation_id} | 200 |
| POST | /findings/{finding_id}/repair-proposals | 201 |
| GET, PATCH | /repair-proposals/{repair_proposal_id} | 200 |
| POST, GET | /cases/{case_id}/reviews | 201, 200 |
| GET | /cases/{case_id}/audit | 200 |

Idempotency headers follow Section 3.2 exactly. A prepared request captures normalized JSON or multipart fields and file bytes; only transport retries reuse the key. Every received HTTP response consumes its request. No automatic mutation retries occur. A 409 VERSION_CONFLICT triggers authoritative resource reads, retains the unsaved text, and blocks writes until the human reconciles. A failed refresh remains recoverable through Refresh resources.

An interrupted response-body stream remains an unresolved transport outcome and may retry the same captured request/key; a fully received HTTP response or malformed JSON response does not qualify for key reuse.

## Contract adjustments for dev integration

- User authorized PDF-first frontend implementation while backend/OpenAPI catch up. Shared contracts, backend, merge conflict and teammate files are untouched.
- G01: clean case shows the completion gap, with no fake finding, repair or APPROVE_CASE command.
- G03: accept and display DRAFT, READY or CLOSED returned by the server; never infer initial readiness or mark content READY automatically.
- G04: nonnegative integer budgets/offers, signed integer scenario deltas as in Section 8. No numeric calculations or fixture prices originate in the browser.
- G07: display supplier_data_version only if returned; otherwise show the provenance gap. The request version is not presented as server-returned provenance.
- P0 UI prerequisites are a usable TOR and technical specification. This UI rule does not amend the backend contract. Extraction and upload limits remain server authoritative.
- Missing canonical envelope fields are rejected instead of silently synthesizing error details, retryability or metadata. Resource decoders validate in production as well as development.
- Session storage is an identifier allowlist only. Versions, current step, resources, evidence, drafts and actor identity are not persisted. Current step is recovered from freshly fetched resources.
- API responses must preserve same-case/finding relationships. The frontend checks these as an additional guard; authorization remains a backend responsibility.

## Accessibility and limitations

Semantic forms and labels, fieldsets, native keyboard controls, current-step semantics, skip link, visible focus, status/error announcements, table captions/headers, responsive panels, reduced-motion support, and textual status labels are included. This is not a formal WCAG conformance claim.

The unresolved README merge pre-existed this work. No branch merge, staging, commit, push, schema change, route implementation or deployment is performed by this frontend task. Real upload/AI, authorization, immutable persistence, review/audit atomicity, and restart persistence require the integrated backend and owner verification.

Browser QA was attempted with a visibly labelled local fixture server. The browser-control tool stopped because it could not confidently determine the active URL on Windows. Visual layout, responsive rendering, interactive keyboard traversal and browser-console verification are therefore not certified; automated markup/logic checks and TypeScript/build results are reported separately.


## Audit refresh compatibility fix

After updating to dev commit 3bcec7b, the backend AuditView permits explicit
null event_hash/previous_hash values because hash chaining is optional. Its
legacy audit actor projection also permits null display_name and role rather
than inventing historical identity. The frontend now accepts those nulls while
requiring the fields, UUID actor ID and valid non-null types. Review identities
remain strict. Missing audit hashes/names are labelled as not recorded.

The old event_hash string-only decoder raised the screenshot's exact
`audit.event_hash does not match API Contract v1.1.` error while reading the
audit timeline; it did not mean that the completed AI analysis had failed.
Regression coverage includes null hashes after clean analysis, legacy actor
metadata, retained hashed records, malformed fields and clean-case rendering.

The separate clean-case completion notice remains intentional under G01:
no findings means no fabricated repair proposal, and v1.1 has no APPROVE_CASE.
This fix does not introduce a new review decision or mutate audit history.


## Local login, case history and multi-file evidence upload

The combined `app.web:create_web_app` now provides operational `/auth/session`,
`/auth/login`, and `/auth/logout` endpoints outside the frozen `/api/v1` business
contract. Configure the single local username and password in the ignored root
`.env` via `PROCUREMIND_LOGIN_USERNAME` and `PROCUREMIND_LOGIN_PASSWORD`.
Login is enabled by default for the combined web app and refuses to start without
credentials. `PROCUREMIND_LOGIN_ENABLED=false` is an explicit isolated-test option,
not the local application's default. The API-only `app.main` composition remains
a developer/test entry point; do not expose it alongside the protected web server.

Sessions are server-side, opaque, HttpOnly, SameSite=Strict, expire after eight
hours, and are revoked on sign-out. Token hashes, not raw cookies, are stored in
memory. Server restart signs users out. Login attempts are rate-limited and
cross-origin mutations rejected. HTTPS cookies are Secure; the local HTTP preview
uses localhost. Credentials are not embedded in frontend bundles or browser
storage. This is a single-account local login protecting the configured demo
actor, scopes and case membership; it does not implement production OIDC or
multi-user account administration. These operational endpoints require integration
owner review before deployment; no business response/schema/enum was changed.

Case history uses the existing authorized GET /cases endpoint, with search, category filtering, five-case pagination and a
reopen action. Reopening loads documents, the latest analysis, findings and any
available audit history from the server. Recent browsing history stores at most 50 UUIDs
in localStorage, with no case titles, document content, cached results or reviewer
identity. Active-workspace recovery continues to store only resource identifiers
in sessionStorage. History can be filtered to recently opened cases; all currently
authorized cases remain available, including after browser-storage loss.

Select multiple PDFs in Upload. Each file is sent as an independent contracted
multipart request with its own Idempotency-Key. New documents start as OTHER;
choose the correct document type on each uploaded row and save it. Metadata PATCH
sends document_type and expected_version and retains the PDF bytes. TOR and
TECHNICAL_SPECIFICATION enable the comparison prerequisite after successful saves.
A stale version is refreshed/reconciled, not silently overwritten.

Batch progress reports each file separately. Successful files remain uploaded if
another fails. Retry skips successes; unknown transport outcomes retain their
original request/key. Invalid or cross-case response shapes require refresh and
reconciliation before a new upload for that file. Clearing the upload list never
deletes a server document. New uploads/type edits reset only local downstream
selection, preserving all immutable server executions and review records.

Tests cover authenticated API access, failed/expired/tampered sessions, logout,
CSRF, rate limiting, authorized history, persisted document-type changes, recent-ID
storage, batch partial failure, transport retry keys, UI controls and credential
masking. Visual browser verification was unavailable because the local-origin
browser permission was declined; automated API, rendered markup and build checks
are reported separately.


## Assess and history follow-up

AI execution model is nullable, matching the backend ExecutionView. Failed provider
calls with no returned model/usage now show their real error instead of a client
shape error; malformed non-null values still fail validation. The model name is
never fabricated from the configured requested model.

History defaults to updated_at descending and five cases per page, with category,
text and recently-opened filters. Filter changes reset the page. Pagination clamps
when fewer results remain. Category options come from authorized backend cases;
filtering/pagination are client-side over the existing paginated GET /cases data,
without adding unsupported API query fields or caching case content locally.


## Document type footer and case removal

Document type controls edit local selections. A single **Save document types**
button sits at the bottom next to **Continue to Assess**, sending existing
PATCH /documents/{id} requests sequentially with each document's current version.
Unchanged rows are skipped. Successful responses are applied immediately; a
later failure stops the batch and retains the other choices. Version conflicts
refresh authoritative resources before the user explicitly saves again. Continue
and analysis are blocked until all pending selections are saved.

History rows offer **Delete case** with confirmation and a reason, using the
existing DELETE /cases/{id} request (reason, expected_version). Success removes
that case from the visible history and local recent IDs, and clears the workspace
if it was active. No new backend route or shared schema is introduced. Server
scope/access checks, active-analysis/review protections and soft deletion apply.


## Vendor proposal summaries and recommendations

Assure starts with a card for each active SUPPLIER_QUOTATION document. Every card
shows its recorded analysis coverage, result, recommendation and actionable next
steps. Open findings citing that proposal lead to a clarification recommendation;
unresolved findings without a vendor reference are shown as shared case context.
A finding on one proposal is not attributed to another vendor. Closed findings
recommend checking the recorded resolution before continuing evaluation. Proposals
with no recorded issues receive next steps for detailed technical/commercial
evaluation. Filenames identify proposal documents; vendor identities are not
inferred or merged from filenames.

Unassessed proposals, failed/pending analysis, absent execution metadata, evidence
warnings, incomplete finding lists and absent requirement baseline each produce
an appropriate prerequisite action. No positive compliance verdict is inferred.
Requirements and finding counts remain analysis-wide context, not per-vendor
satisfaction counts. Supporting evidence retains its document/page provenance.

Human review information has been removed from this summary. The separate formal
review controls, immutable decisions and audit timeline remain unchanged. No new
AI request, public schema field, API route or persistence table is introduced.
History reopening and refresh rebuild these recommendations from server records.
The clean-case completion gap remains visible.

Case history shows each case's server updated_at timestamp in local display time
with UTC retained in the time element. Sorting uses updated_at descending, then
created_at and ID for stable ties, before the existing filters/pagination slice.
Recently opened IDs do not override update ordering. Five-case pagination and
category/search/recent filters are retained.

The browser favicon uses public/favicon.svg, matching the existing ProcureMind
P/ascending-arrow brand mark and colors. Vite copies it into the Docker static
build; index.html links it for both the login page and case workspace.


Executed verification for this update: 70 frontend Node tests passed; TypeScript
and Vite production build passed. Docker rebuilt and became healthy. HTTP checks
verified the favicon link/SVG response, deployed recommendation/history assets,
authorized case timestamps and logout. The existing synthetic persistence check
also passed. No extra live AI call or interactive visual browser check was made.
