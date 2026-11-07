# Teguh P0 verification

Current branch scope: cases, documents/PDF evidence, analysis/jobs/retry and findings. Simulation and Review/Audit modules are not changed; frontend and challenge/repair are outside this task.

| Check | Result |
| --- | --- |
| python -m pytest backend/tests -q | PASS: 59 tests, one existing Starlette/httpx deprecation warning |
| Python application compile/import | PASS |
| Contract route/method/success-code comparison | PASS: 18 owned business operations plus health |
| Public request/response schema and closed-input checks | PASS |
| Generated OpenAPI reference resolution | PASS; validation documents 400, upload documents 413/415/422 |
| Valid/malformed/non-PDF/oversized/encrypted/owner-only-encrypted/textless PDFs | PASS |
| Page extraction, byte retention, upload replay and collision protection | PASS |
| UUID v4, UTC Z, integer IDR, canonical envelopes and stale version | PASS |
| Cross-case access, scope denial and hidden-resource anti-enumeration | PASS |
| Concurrent same-key case creation and changed-payload conflict | PASS |
| Exact citations, unmatched citations, invalid locations and clean result | PASS |
| Job transitions, immutable terminal, retry/new ID and startup recovery | PASS |
| Real SDK adapter strict-schema request construction | PASS with isolated transport-facing test double; no network inference |
| Atomic business/audit/idempotency rollback and file cleanup | PASS |
| Final-review document/case deletion protection | PASS via shared test records; no review service implemented |
| Restart persistence and row-preserving legacy migration | PASS |
| Immutable AI/source/evidence records via ORM and raw SQL | PASS |
| Temporary Uvicorn live HTTP smoke | PASS: health200, case201, upload201, analysis202, polling and OpenAPI200 |
| Live OpenAI inference | NOT RUN: authorized key/model/account access not configured |
| Frontend / simulation / review-audit workflows | NOT RUN; teammate scope |

The HTTP smoke used a temporary synthetic database and PDF storage, real backend demo context and the real provider adapter with configuration deliberately absent. The analysis failed explicitly with AI_PROVIDER_ERROR and model=null, with no fabricated finding. Server and temporary data were cleaned up. No live provider response is claimed.

Tests deliberately inject isolated provider results/errors to cover schema failures, citation warnings, HIGH findings, no contradiction, timeouts and rate limits. Production code contains no canned AI or simulation fallback. Remaining operational risks and integration dependencies are in TEGUH_P0_HANDOFF.md and CONTRACT_GAPS.md.

The initial foundation-only route assertion was updated to the source-backed 18-operation phase-A scope. This does not remove ownership or source-contract checks. Full-system 36-route regression and production load/durability guarantees are not claimed.
