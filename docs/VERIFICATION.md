> Scope: the full foundation report below comes from main commit 45b0c9e. This teguh branch excludes frontend and teammate routers. The transfer was independently verified with 14 passing backend tests; frontend checks below describe main, not files present on this branch. See TEGUH_P0_HANDOFF.md.

# Foundation verification

Verified on Windows with Python 3.13.12, portable Node.js 22.23.4 and npm 10.9.9. This report applies to the current shared foundation, not the previously deleted project or a completed feature workflow.

## Required foundation gates

| Check | Executed command / observation | Result |
| --- | --- | --- |
| Backend dependencies | pip install -e ./backend[test] in project .venv | PASS |
| Python imports | Imported app.main, models, security, pymupdf and openai | PASS |
| Python compile | python -m compileall -q backend/app | PASS |
| pytest smoke/integrity | python -m pytest backend/tests -q | PASS: 14 tests |
| FastAPI starts | Temporary Uvicorn subprocess at 127.0.0.1:18741 | PASS |
| GET /api/v1/health | Live HTTP request; canonical envelope, UTC Z metadata | PASS: 200 |
| GET /openapi.json | Live HTTP request; OpenAPI 3.1.0; only health route | PASS: 200 |
| Frontend dependencies | npm install; package-lock.json generated | PASS |
| TypeScript typecheck | npm run typecheck, also part of npm run build | PASS |
| Frontend production build | npm run build | PASS: 28 modules transformed |
| Frontend dev server | Temporary Vite subprocess at 127.0.0.1:15173 | PASS: HTTP 200 |
| React/TypeScript transformation | HTTP GET /src/main.tsx from Vite | PASS: 200 |

Both temporary servers were stopped after verification. Vite/esbuild required execution outside the restricted sandbox for parent-directory access. Dependencies needed authorized network access. Portable Node was downloaded from nodejs.org and its archive SHA-256 verified against the official release manifest; no system installation was changed.

The backend tests emit one Starlette/httpx deprecation warning. No test failed. A temporary import-check script initially shadowed the FastAPI variable with the app package; it was corrected and imports plus live HTTP checks then passed. The first frontend dependency command used the wrong relative portable-runtime path; it was corrected before successful installation. These were verification-command issues, not hidden passing checks.

## Tested foundation properties

Exact Appendix A enums; closed Pydantic input; UUID v4; UTC with Z; integer/nonnegative IDR rejecting bool/string/float; canonical success and error envelopes; 400 validation behavior without reflected client values; sanitized 500; request ID correlation; fail-closed identity; idempotency header requirement and stale-version primitive; only health registered; SQLite foreign keys; schema initialization; budget constraints; immutable AI/simulation/review/audit records blocked by ORM and raw SQL UPDATE/DELETE.

The DB tests initialize isolated in-memory tables. No fixture records are seeded into the application database. No business commands or provider calls are executed.

## Source transcription

The existing primary-source lock records SHA-256 fcc0388407f9cac2804b71be151f41a444a546bfa5d6648ac2ef33a4a40aecdc for the 39-page v1.1 PDF. Source checks established 36 unique business route/status entries, 6 required idempotent POST patterns, 12 exact Appendix A enums and 16 Appendix B error codes. Current enum tests compare the Python declarations with that source-backed snapshot.

## Integration limits

The 36 business endpoints remain empty router modules, so docs/openapi.foundation.json contains only /api/v1/health. Full API contract regression, business CRUD, resource authorization, concurrent idempotency transactions, lifecycle transitions, terminal-job enforcement, PDF extraction/evidence matching, schema-constrained AI calls, simulation, review/audit workflows and end-to-end UI tests are NOT implemented or claimed as verified. Feature owners provide migrations and atomic service writes. The explicit create_all demo initializer is not a production migration system.

Health payload, native OpenAPI output and proposed operational defaults remain documented gaps. Foundation gate completion does not approve those contract extensions or establish full P0 release readiness.
