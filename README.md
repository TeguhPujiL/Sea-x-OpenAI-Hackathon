# ProcureMind V4.1 shared foundation

React/Vite/TypeScript/Tailwind shell and Python 3.11+ FastAPI/Pydantic v2/SQLAlchemy/SQLite infrastructure, aligned with the supplied API Contract v1.1. Section 2.3 controls. Business routers are empty; no teammate-owned features or synthetic live responses are implemented.

## Backend setup and run

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "./backend[test]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

For the exact dependency versions verified on Windows/Python 3.13, install backend/requirements.lock.txt first, then install the local package with `pip install --no-deps -e ./backend`. The normal manifest installation supports Python 3.11+; the lock records the tested platform and includes pytest/httpx.

Health: http://127.0.0.1:8000/api/v1/health. OpenAPI: http://127.0.0.1:8000/openapi.json. API docs: http://127.0.0.1:8000/docs.

Health uses the contract envelope with dynamic request_id, UTC Z timestamp and api_version=v1. Its data `{status: "ok", demo_mode: false}` is a PROPOSED foundation schema, not procurement data. OpenAPI remains native JSON outside the REST base path; its exception is explicitly recorded in docs/CONTRACT_GAPS.md. Liveness is not business or provider readiness.

## Frontend setup and run

Use Node.js 22 and npm. From the repository root:

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run typecheck
npm run build
npm run dev
```

Vite proxies /api/v1 to http://127.0.0.1:8000. VITE_API_BASE_URL is reserved for the Frontend Lead's API client; the shell does not make business API calls. Never put API keys or trusted actor/reviewer identity in VITE variables.

This workspace also has a checksum-verified portable Node runtime in ignored .tools. To use it from the repository root before the frontend commands:

```powershell
$nodeDirectory = (Get-ChildItem .tools -Directory -Filter 'node-*-win-x64' | Select-Object -First 1).FullName
$env:Path = $nodeDirectory + ';' + $env:Path
```

## Tests and explicit database bootstrap

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m compileall -q backend/app
# Optional: initialize empty tables in the configured demo SQLite database.
.\.venv\Scripts\python.exe -m app.core.init_db
```

The application never creates tables on startup. init_db uses create_all only as an empty demo bootstrap; it does not migrate existing tables. Relative SQLite paths resolve from the process working directory, so run from the repository root. Future production/feature integration requires reviewed migrations.

## Shared contract and identity

The shared schema module defines the exact 12 Appendix A enums, closed Pydantic models, UUID v4, UTC Z serialization, integer IDR, envelopes, pagination and version primitives. Wire job status, finding type/evidence and review expected_case_version remain unchanged in the lock.

Demo identity is disabled by default. Enable PROCUREMIND_DEMO_MODE only with a backend-configured UUID v4 actor and explicit scopes. Role alone grants no scopes. The frontend owner must visibly label demo identity when consuming it. Production requests requiring identity fail closed until real OIDC verification exists. Every feature must authorize case access and reject cross-case references.

The shared model module declares 14 tables and foreign keys, status/version/money/page constraints and idempotency uniqueness. SQLite triggers and an ORM guard reject mutation of persisted AI executions, simulations, reviews and audit events. Database owners still implement migrations, complete workflow constraints, JSON validation and atomic business/audit/idempotency writes. No simulator, AI execution, PDF extraction, human review or audit command is provided.

PyMuPDF and OpenAI SDK dependencies and backend-only provider/model configuration are prepared for Teguh's feature implementation. Schema-constrained AI calls and their output validation are not pre-implemented. Secrets and raw documents are never logged by the scaffold.

## Contract, ownership and results

- [Contract lock and exact endpoint table](docs/CONTRACT_LOCK.md): 36 business method/path pairs and codes, 12 enums, 16 Appendix B codes, canonical envelopes, headers and concurrency.
- [Source-backed machine snapshot](docs/contract_snapshot.json) and [foundation OpenAPI](docs/openapi.foundation.json): the latter exposes only health.
- [Ownership](docs/OWNERSHIP.md): Frontend Lead owns frontend/src; Teguh owns core/shared and AI/document/business integration; Aris owns simulation; Fazhima owns review/audit/assurance QA. Shared models/schemas require Teguh review.
- [Gaps](docs/CONTRACT_GAPS.md): no APPROVE_CASE or fake repair for clean cases; separate contract 660M/690M/825M fixture from negative-pack 710M/835M/680M. All corrections stay PROPOSED. Challenge readiness and signed-delta conflicts remain explicit.
- [Verification results](docs/VERIFICATION.md) and [exact file inventory](docs/FOUNDATION_FILES.md).

The foundation is ready for owner handoff; it is not the completed P0 workflow or a full API contract regression pass.
