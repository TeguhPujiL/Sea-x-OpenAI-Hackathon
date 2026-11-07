# ProcureMind V4.1 - Teguh backend branch

Shared backend foundation and Teguh-owned router skeletons copied from main commit 45b0c9e. No new feature implementation is introduced by this transfer.

Included: configuration, SQLite infrastructure, trusted demo identity, canonical envelopes, exact shared enums/primitives, shared persistence declarations, foundation tests, case/document/analysis/job/finding/challenge/repair router skeletons and contract documentation.

Excluded: frontend source, simulation router/services/fixtures, review/audit routers and assurance services. Shared models include all integrated resource declarations; these are contract-owned infrastructure, not teammate service implementations. The router registry is adjusted to import only files present on this branch.

## Install and run

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "./backend[test]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m compileall -q backend/app
# Optional empty demo schema bootstrap, not migrations:
.\.venv\Scripts\python.exe -m app.core.init_db
```

Health: /api/v1/health. Native OpenAPI: /openapi.json. Business routers remain empty. Demo identity is disabled by default and must be configured server-side with explicit scopes. Never commit .env, .venv or .tools. Application startup does not create tables.

## Contract and handoff

Read [CONTRACT_LOCK.md](docs/CONTRACT_LOCK.md), [CONTRACT_GAPS.md](docs/CONTRACT_GAPS.md), [OWNERSHIP.md](docs/OWNERSHIP.md) and [TEGUH_P0_HANDOFF.md](docs/TEGUH_P0_HANDOFF.md). Section 2.3 controls. Shared models/schemas require Teguh review. Clean-case completion has no APPROVE_CASE; supplier data versions remain separate. Health/OpenAPI exceptions and other corrections remain PROPOSED.

The main branch's full-foundation test report is retained with its provenance in docs/VERIFICATION.md. Branch-specific transfer verification and exact scope are in the handoff and file inventory. No frontend checks are needed for this backend-only transfer.
