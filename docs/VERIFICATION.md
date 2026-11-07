# Foundation verification

Recorded for the current local scaffold using Python 3.13.12 on Windows.

| Check | Result |
| --- | --- |
| Isolated .venv and backend dependency installation | PASS; installation required network escalation |
| Python compileall | PASS |
| pytest backend/tests -q | PASS: 3 tests; one dependency deprecation warning |
| FastAPI lifespan, health and OpenAPI via TestClient | PASS |
| Live Uvicorn HTTP health | PASS: 200 on temporary localhost port 18741 |
| Live Uvicorn HTTP OpenAPI | PASS: 200; only /api/v1/health is registered |
| Unknown resource application error envelope | PASS: 404 |
| Closed shared input primitive and naive datetime rejection | PASS |
| SQLite foreign_keys PRAGMA | PASS: 1 |
| Frontend package.json and tsconfig.json parsing | PASS |
| git diff --check | PASS |
| Frontend install/typecheck/build/dev server | NOT RUN: node and npm unavailable in PATH and checked standard installation paths |
| Contract v1.1 regression and exact schema verification | BLOCKED: primary 39-page contract missing |

The TestClient dependency emits a Starlette httpx deprecation warning. Tests still pass. No feature integration, immutable domain persistence, idempotency, optimistic concurrency, AI output or PDF processing behavior is claimed as verified. Frontend JSON parsing is not TypeScript validation.

The live backend process was stopped after verification. Start commands are in README.md. No external service calls or domain fixture generation were made.
