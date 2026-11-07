# ProcureMind V4.1 - Teguh P0 backend

Implemented: cases, protected PDF upload/page extraction, asynchronous AI analysis jobs/retries and evidence-linked findings with versioned triage/dismissal. API Contract v1.1 Section 2.3 controls. Wire fields remain type/evidence, job status and expected_version as specified. Simulation and Review/Audit services/routes are not changed; challenge/repair remain skeletons.

## Install and migrate

From the repository root in PowerShell (Python 3.11+):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "./backend[test]"
Copy-Item .env.example .env
# Edit .env: configure trusted demo identity/scopes, API key and model.
.\.venv\Scripts\python.exe -m app.core.migrations
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

Back up any existing SQLite file before migration. The versioned migration preserves previous rows, adds membership/job provenance, relaxes unavailable runtime-model storage to null and reinstalls integrity guards. Legacy actor/input provenance is never guessed. Startup does not migrate or create tables automatically. Relative paths resolve from the repository root. Do not run multiple Uvicorn workers: the MVP startup recovery marks interrupted nonterminal jobs FAILED for explicit retry.

## Backend configuration

Demo identity is off by default. For a hackathon run, set PROCUREMIND_DEMO_MODE=true, generate a UUID v4 with `python -c "from uuid import uuid4; print(uuid4())"`, set PROCUREMIND_DEMO_ACTOR_ID, and grant only required PROCUREMIND_DEMO_SCOPES from .env.example. Identity is backend-controlled; no browser actor/reviewer field is trusted. Role alone does not grant scopes. API access also requires case membership; case creation grants it only to the creator.

Set PROCUREMIND_OPENAI_API_KEY and PROCUREMIND_OPENAI_MODEL to an authorized model supporting strict Structured Outputs; provider is openai. Missing configuration creates a visible FAILED job, never a fake finding. No live AI request has been claimed as tested. Never commit .env, stored PDFs, API keys or raw provider output. The frontend owner must label demo identity visibly.

Storage defaults to .storage with generated UUID filenames and no download/static route. Upload, page, text, AI input and timeout limits are explicit configuration values. These operational defaults are PROPOSED and documented; they are not invented contract constants.

Trusted operators can grant another backend actor case membership using `python -m app.core.access --case-id <uuid-v4> --actor-id <uuid-v4>` under configured ADMIN context with case:write; the grant is audited. Production OIDC and operator policy remain deployment work.

## Run and test

Health: http://127.0.0.1:8000/api/v1/health. OpenAPI: http://127.0.0.1:8000/openapi.json. API docs: http://127.0.0.1:8000/docs.

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m compileall -q backend/app
```

Current result: **59 passed** plus a Uvicorn HTTP smoke test. Live OpenAI inference is not executed. There is no frontend source in this branch; no frontend check is claimed.

## Integration documentation

- [P0 handoff](docs/TEGUH_P0_HANDOFF.md): changed files, migration, exact 18-route matrix, AI failure modes, security and owner dependencies.
- [Current P0 OpenAPI](docs/openapi.teguh-p0.json): 18 business operations + health. openapi.foundation.json is an archival snapshot.
- [Contract lock](docs/CONTRACT_LOCK.md) and [source snapshot](docs/contract_snapshot.json): all 36 full-system contracts, not all implemented here.
- [Gaps](docs/CONTRACT_GAPS.md), [ownership](docs/OWNERSHIP.md), [verification](docs/VERIFICATION.md), and [file inventory](docs/FOUNDATION_FILES.md).

Do not introduce APPROVE_CASE, fake clean-case repairs, client-authoritative review identity, or mix supplier fixture versions. Corrections are PROPOSED. Finding resolution requiring disposition evidence remains blocked pending an approved schema; dismissal is implemented. The integrated six-step workflow still requires teammate services and the separate challenge/repair phase.
