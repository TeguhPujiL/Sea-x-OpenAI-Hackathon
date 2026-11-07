# Teguh Prompt A + Prompt B verification

Current scope: 28 Teguh business operations (case/document/analysis/job/finding/challenge/repair) plus health. Prompt A's 59-test baseline remains covered. Simulation, Review/Audit routes/services and frontend remain separate owner work.

| Check | Result |
| --- | --- |
| python -m pytest backend/tests -q | PASS: **100 tests**, one existing Starlette/httpx deprecation warning |
| Python compile/import | PASS |
| Contract route/method/success-code comparison | PASS: 28 owned business operations + health |
| Generated OpenAPI references, request fields, required headers and error envelopes | PASS |
| Prompt A cases/PDF/pages/evidence/jobs/findings/idempotency/access/version/migration/recovery tests | PASS |
| Challenge POST 201, source grounding, human readiness, CRUD restrictions | PASS |
| Repair POST 201, exact fields, all three actions and no invented numeric impact | PASS |
| DRAFT edit/delete, stale version, submit snapshot and frozen content | PASS |
| Review-owned disposition can update without changing submitted snapshot | PASS |
| Same-case finding/simulation, verified source requirements, clean-case zero resources | PASS |
| Synchronous AI timeout/rate/malformed/schema/citation/neutrality failures | PASS; failed attempts retain immutable provenance |
| Actual model/null usage and strict OpenAI request construction | PASS with isolated test providers/client doubles |
| Idempotent success/failure replay, Retry-After, concurrent same-key calls and lease expiry | PASS |
| Source changes during generation cannot save stale drafts | PASS |
| Phase A/B delegated audit and transactional rollback | PASS |
| Read-only typed simulation/review-precondition interfaces and factory composition | PASS |
| Official PDF bytes and versions remain unchanged by decisions | PASS |
| Migration 0001/foundation and v1-to-v2 idempotency-body preservation | PASS |
| Temporary Uvicorn smoke | PASS: health 200, OpenAPI 200, 29 operations, schema user_version=2 |
| Live OpenAI analysis/decision generation | NOT RUN: authorized key/model/account access not configured |
| Frontend / simulation engine / actual review-assurance workflow | NOT RUN; teammate scope |

The temporary smoke server and DB were removed. Windows initially held the SQLite file during automatic cleanup; cleanup succeeded after process exit. Positive generation tests use isolated test providers only; production has no mock/fallback response path. No real provider success, frontend test or full-system 36-route release gate is claimed.

Prompt/schema versions: procurement-analysis-v1, procurement-challenge-v1, procurement-repair-v1. Runtime provider/model, evidence checks, source identifiers/versions and hashes, latency and usage/null persist without raw prompts or secrets. The current schema is openapi.teguh-p0.json. The original openapi.foundation.json and Prompt A handoff are historical source records.

See TEGUH_DECISION_HANDOFF.md for the exact ten new routes, migration 0002, typed owner interfaces, failure behavior and merge notes. CONTRACT_GAPS.md preserves the clean-case addendum, dataset separation and explicit proposed policies.
