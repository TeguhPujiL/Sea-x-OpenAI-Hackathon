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
