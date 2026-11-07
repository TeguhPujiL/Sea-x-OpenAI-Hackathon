# ProcureMind V4.1 - Teguh backend

Prompt A and Prompt B are implemented: **28 owned business operations** for case, PDF document, analysis/job, finding, challenge and AI repair, plus health. API Contract v1.1 Section 2.3 controls. Simulation calculations and Review/Audit decision/read routes remain teammate-owned.

## Install, migrate and run

From the repository root in PowerShell (Python 3.11+):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "./backend[test]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env: configure trusted demo identity/scopes and an authorized OpenAI key/model.
.\.venv\Scripts\python.exe -m app.core.migrations
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

Back up an existing DB first. Migration **0002 / user_version=2** preserves Prompt A rows/cache bodies, adds generation leases and immutable submitted-repair snapshots, and retains cached Retry-After headers. Startup does not create or migrate tables. Existing submitted rows without snapshots fail review preconditions until a reviewed backfill is provided. Run from the repository root because relative DB/storage paths resolve there. The MVP uses one Uvicorn worker; Prompt A startup recovery is not a production queue.

Health: http://127.0.0.1:8000/api/v1/health. OpenAPI: http://127.0.0.1:8000/openapi.json. Interactive docs: http://127.0.0.1:8000/docs.

## Trusted backend configuration

Demo identity is disabled by default. Set PROCUREMIND_DEMO_MODE=true, generate a UUID v4 using `python -c "from uuid import uuid4; print(uuid4())"`, configure PROCUREMIND_DEMO_ACTOR_ID and explicitly grant only needed scopes from .env.example. Prompt B requires challenge:read/write/delete and repair:read/write/delete as appropriate. Role alone grants no scopes. Both API scope and backend-managed case membership are required; browser-supplied identity is never authoritative. The integrated UI must label demo mode.

Set PROCUREMIND_OPENAI_API_KEY and PROCUREMIND_OPENAI_MODEL to an authorized model supporting strict Structured Outputs. Never commit secrets or PDFs. There is no canned AI fallback. Missing provider configuration produces an explicit failure. Live OpenAI inference/generation has not been tested without authorized credentials/model/account access.

Protected bytes use generated UUID filenames under .storage with no public file route. Documents/pages are retained on soft delete. A trusted ADMIN with case:write can run `python -m app.core.access --case-id <uuid-v4> --actor-id <uuid-v4>` to grant backend membership; the grant is audited. Production OIDC remains deployment work.

## Challenge and repair behavior

Challenge POST returns **201** and creates DRAFT, following page 19's human-readiness note; the conflicting READY example remains documented. Human PATCH may mark READY. Only DRAFT/READY is editable; only eligible DRAFT is deletable.

Repair POST returns **201**, requires Idempotency-Key and validates same-case finding/simulation plus VERIFIED source evidence. Actual runtime model, prompt/schema version, checks, latency and usage/null persist. before_text reproduces verified evidence; generated numeric impact is rejected. Quantitative interpretation is formatted from immutable stored simulation output without recalculating Aris's results. No official PDF is edited.

Only DRAFT repair proposals can be edited. PATCH status=SUBMITTED freezes a new immutable content snapshot, sets case readiness for human review and increments case.version; refresh the case before sending expected_case_version to the future review endpoint. Submission does not itself approve the case or compute final assurance.

Provider calls run outside the SQLite write lock. Same-key repair concurrency uses a bounded lease; successful and attempted-generation failure responses are replayed without another model call. A deliberate new generation after a cached failure requires a new key. Shared AuditService participates in the caller transaction across phases A/B; no adapter should independently commit.

## Tests and owner integration

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m compileall -q backend/app
```

See [verification](docs/VERIFICATION.md) for the current executed result. No frontend source is included in this branch. Live provider validation, full-system regression and integrated frontend/simulation/review workflows remain owner work.

- [Prompt B handoff](docs/TEGUH_DECISION_HANDOFF.md): ten new endpoints, prompt/schema versions, typed service ports, tests, errors, migration and merge notes for Aris/Fazhima.
- [Prompt A handoff](docs/TEGUH_P0_HANDOFF.md): preserved historical baseline and 18 phase-A endpoints.
- [Current OpenAPI](docs/openapi.teguh-p0.json): 28 business operations + health. openapi.foundation.json is archival.
- [Contract lock](docs/CONTRACT_LOCK.md), [source snapshot](docs/contract_snapshot.json), [gaps](docs/CONTRACT_GAPS.md), [ownership](docs/OWNERSHIP.md), [file inventory](docs/FOUNDATION_FILES.md).

Bind real owner adapters through `create_app(settings, simulation_lookup=..., audit_service=..., reference_lookup=..., review_preconditions=...)`. Defaults are read-only shared-model lookups and the explicit core audit adapter, not a fake simulator or review service. Read the handoff contracts before merge.

Clean-case completion remains OPEN / PROPOSED ADDENDUM: no APPROVE_CASE, fabricated finding or fake repair is added. Supplier data versions remain separate. Operational defaults, conservative language/numeric guards, health/OpenAPI exception and schema clarifications remain explicit PROPOSED policies.
