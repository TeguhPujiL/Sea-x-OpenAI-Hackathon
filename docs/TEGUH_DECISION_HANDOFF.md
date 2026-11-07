# Teguh Prompt B: Challenge and AI Decision Repair

Branch: teguh. Prompt A baseline: commit 8ac4327, 59 passing tests. Current combined verification: **100 passing tests**. Primary source: API Contract v1.1, Section 2.3 and docs/CONTRACT_LOCK.md. No simulation calculation, review decision, assurance computation after review or teammate router/service is implemented or changed.

## Endpoint coverage

| Method | Path | Success | Scope | Idempotency-Key |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/cases/{case_id}/challenges` | 201 | `challenge:write` | Not required by v1.1 |
| GET | `/api/v1/cases/{case_id}/challenges` | 200 | `challenge:read` | Not required by v1.1 |
| GET | `/api/v1/challenges/{challenge_id}` | 200 | `challenge:read` | Not required by v1.1 |
| PATCH | `/api/v1/challenges/{challenge_id}` | 200 | `challenge:write` | Not required by v1.1 |
| DELETE | `/api/v1/challenges/{challenge_id}` | 200 | `challenge:delete` | Not required by v1.1 |
| POST | `/api/v1/findings/{finding_id}/repair-proposals` | 201 | `repair:write` | Required |
| GET | `/api/v1/findings/{finding_id}/repair-proposals` | 200 | `repair:read` | Not required by v1.1 |
| GET | `/api/v1/repair-proposals/{repair_proposal_id}` | 200 | `repair:read` | Not required by v1.1 |
| PATCH | `/api/v1/repair-proposals/{repair_proposal_id}` | 200 | `repair:write` | Not required by v1.1 |
| DELETE | `/api/v1/repair-proposals/{repair_proposal_id}` | 200 | `repair:delete` | Not required by v1.1 |

Combined branch coverage: **28 business operations + health**. Eight Simulation/Review/Audit operations remain teammate-owned. Current schema: [openapi.teguh-p0.json](openapi.teguh-p0.json). Canonical envelopes and Appendix B errors are preserved; unknown fields and invalid enums return 400 VALIDATION_ERROR. Repair creation's Idempotency-Key is required in both implementation and OpenAPI; Challenge does not silently require it.

## Exact request and response boundaries

Challenge create accepts finding_id, generation_mode=AI_ASSISTED and requested_evidence. Internal model citations do not add a public evidence field: the public finding_id links to its independently verified evidence. PATCH accepts question/status/expected_version, matching the contract example. Only current DRAFT/READY can be edited; CLOSED cannot be edited. READY requires a human PATCH and current verified sources. Delete is soft and restricted to unreferenced DRAFT with reason/expected_version.

Challenge starts **DRAFT**, following page 19's explicit human-readiness note and Section 6's statement that example values are illustrative. The conflicting READY example remains OPEN / PROPOSED CLARIFICATION in G03; this is not a new enum or an unrecorded approval shortcut.

Repair create accepts action_type, simulation_id, generation_mode=AI_ASSISTED. Action values are exactly REVISE_REQUIREMENT, MAINTAIN_WITH_JUSTIFICATION, REQUEST_MORE_EVIDENCE. before_text, proposed_text, justification, simulation_id, ai_execution_id, human_edits, version and timestamps preserve Section 6.7 names. AI creates DRAFT only. PATCH accepts proposed_text/status/expected_version; client-set review outcomes and provenance fields are rejected. DRAFT deletion checks downstream review references.

Submitting a DRAFT increments its version, records an immutable full submitted snapshot, moves the case to UNDER_REVIEW / READY_FOR_REVIEW and increments case.version. This is readiness for human review, not final assurance approval. The frontend must refresh the case to obtain expected_case_version; no uncontracted case-version field is added to the repair response. Later edit/delete returns 409. Review owners may change disposition status through their own logic without changing the frozen content or snapshot.

## Changed implementation files

- api/routes/challenges.py and repairs.py: all ten contracted routes.
- schemas/decisions.py and api/decision_presenters.py: closed public requests, responses and internal structured generation models.
- services/ai/decisions.py: real synchronous OpenAI adapter.
- services/decision_evidence.py: authorized source revalidation, neutral-language and quantitative-source checks.
- services/decision_generation.py: bounded context, generation, provenance, leases/idempotency and delegated audit orchestration.
- core/integration.py: typed audit/simulation/reference/review-precondition ports and explicit adapters.
- models/decisions.py: generation leases, frozen submission snapshots and SQLite decision guards.
- core/migrations.py, models/__init__.py, models/tables.py: migration 0002 and idempotent response-header retention.
- core/transactions.py and main.py: shared phase-A/B audit delegation and composition-root injection.
- core/security.py: mandatory idempotency header accurately marked required in OpenAPI.
- tests/test_decisions.py and test_foundation.py: acceptance/integration tests and all-owned-route regression.
- Configuration example, README, AGENTS and docs: current scope, verification, gaps and merge notes.

## Prompt and schema versions

| Generation | prompt_version | Structured schema name | Operation |
| --- | --- | --- | --- |
| Challenge | procurement-challenge-v1 | procuremind_challenge_v1 | DRAFT_CHALLENGE |
| Repair | procurement-repair-v1 | procuremind_repair_v1 | DRAFT_REPAIR |

The adapter uses OpenAI Responses strict JSON Schema, configured key/model, store=false and no SDK retry. It captures the actual returned model and provider usage/null, rather than substituting the configured requested model. Runtime model is null if no provider response exists. See [official OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

Each attempted generation stores immutable AI execution provenance: actual provider/model, requested model internally, operation, prompt_version, schema_valid, independent evidence counters/status, warnings, measured latency and usage/null. Malformed/refused/incomplete output is never silently repaired. Delegated audit details retain input resource IDs, source versions and context/request hashes for traceability without storing raw prompts. No provider payload, API key or extra raw document text is logged or retained. The internal evidence schema is separate from the locked public response fields.

## Evidence and quantitative safety

Only active same-case findings with VERIFIED evidence can generate drafts. Each reference is rechecked against accessible, non-deleted documents and stored one-based page text. Internal citations must fall inside a previously VERIFIED finding excerpt. before_text must reproduce a cited complete verified finding excerpt. Source/context versions are checked again after the provider call; changed inputs cannot produce a stale saved draft.

Generated challenge prose must be a neutral question/rationale with only evidence-supported numerals. Repair proposed numerals must come from verified requirements or immutable scenario inputs. Model-authored repair justification is qualitative and cannot introduce numeric/price/count/eligibility/delta claims. The backend appends a deterministic textual rendering of already-stored baseline/alternative/delta values; it performs **no simulation calculation**. The result stays explicitly synthetic and non-statutory. Human proposed_text edits use the same grounding guard. MAINTAIN_WITH_JUSTIFICATION must preserve the evidenced requirement.

Neutral-language checks are conservative lexical guards, not proof of semantic correctness. They can reject benign wording and do not replace human review. Spelled-out number claims and unsupported metric terms are rejected rather than converted into new facts. This is an explicit PROPOSED generation policy, not a new public field or enum.

No endpoint writes official PDF bytes. Tests compare storage contents before and after draft generation/submission.

## Errors, provenance and idempotency

| Condition | HTTP / code | Persistent result |
| --- | --- | --- |
| Missing/inaccessible/cross-case finding or simulation | 404 RESOURCE_NOT_FOUND | No invented resource or generation |
| Missing/unverified/unusable evidence | 422 EVIDENCE_VALIDATION_FAILED | No draft; execution exists only if the provider was actually attempted |
| Invalid stored simulation result shape/types | 422 SIMULATION_INPUT_INVALID | No numeric recomputation or draft |
| Provider timeout | 504 AI_PROVIDER_TIMEOUT | Immutable failed-attempt provenance |
| Provider rate limit | 429 RATE_LIMITED | Retry-After retained when supplied, including idempotent replay |
| Provider error or unusable structured output | 502 AI_PROVIDER_ERROR | Schema error recorded internally as AI_SCHEMA_VALIDATION_FAILED; no invented Appendix B HTTP mapping |
| Unsafe language, fake before_text, invalid citation or model numeric claim | 422 EVIDENCE_VALIDATION_FAILED | Immutable attempt with failed independent validation; no draft |
| Stale expected_version | 409 VERSION_CONFLICT | No overwrite |
| Frozen state, in-flight lease, or changed generation sources | 409 INVALID_STATE_TRANSITION | No concurrent/stale draft commit |
| Same repair key, different normalized input | 409 IDEMPOTENCY_KEY_REUSED | No second generation |

The provider call runs outside SQLite write locks. Repair requests reserve a unique actor/POST-route/key lease after valid input checks. Same-key in-flight requests get a state conflict; completed requests replay the stored full body/status without another model call. Success and attempted-generation failure responses are cached; transport replay retains original metadata. Retry-After is the only persisted replay header; X-Request-ID reflects the current transport request. A deliberate new generation after a cached failure requires a new key.

Lease expiry is provider timeout + 30 seconds (PROPOSED operational policy). Expired leases can be reclaimed after a crash. This prevents ordinary concurrent duplicate work, but does not promise exactly-once external billing across crashes/lease expiry. If an audit adapter fails, the business/provenance transaction rolls back atomically and an in-flight reservation may remain until expiry. Do not have adapters independently commit or swallow failures.

## Typed integration contracts

All ports are in core/integration.py. The factory accepts keyword arguments:

```python
create_app(settings, simulation_lookup=aris_lookup, audit_service=fazhima_audit,
           reference_lookup=downstream_references, review_preconditions=fazhima_preconditions)
```

Names above represent real owner-provided adapters, not mocks installed into production. Defaults are explicit read-only/shared-core adapters.

- **SimulationLookup.get(session, actor, case_id, finding_id, simulation_id) -> SimulationSnapshot**: must authorize and return immutable same-case/same-finding inputs/results. Default StoredSimulationLookup reads existing shared Simulation rows only. The snapshot is a frozen dataclass containing immutable JSON strings; as_context returns independent copies. No engine or fixture is generated here.
- **AuditService.record(session, AuditCommand) -> None**: must write within the caller's existing transaction, never commit/roll back it. Default CoreAuditAdapter explicitly delegates to Prompt A's core append writer. Phase A and B application sessions resolve the same audit service; no decision module constructs AuditEvent. Fazhima can replace the port at composition time without changing routes.
- **ReferenceLookup.challenge_in_use / repair_in_use**: protects eligible draft deletion; repair also blocks edits to a referenced DRAFT. Default repair guard checks immutable reviews. v1.1 has no challenge FK in downstream create requests; the default challenge guard honors explicit snapshot challenge_id/challenge_ids metadata. Owners adding new links must extend this port before relying on them; no new public simulation field is introduced.
- **ReviewPreconditionValidator.validate(...) -> ReviewCandidate**: default SubmittedRepairPreconditions is read-only: case version/access, same-case submitted repair, current verified finding/document evidence and immutable submitted snapshot/simulation. It returns case version, frozen proposal version/content and simulation reference. It does not authorize a review endpoint, choose a ReviewDecision, compute assurance_status_after or create Review/Audit rows. Fazhima must enforce review:decide at her boundary and apply her own decision policy.

## Migration and freeze boundary

Run `python -m app.core.migrations` before serving requests. Migration 0002 upgrades user_version to 2, adds generation_leases and submitted_repair_snapshots, and adds response_headers to existing idempotency records without discarding bodies or prior rows. Migration 0001 remains supported in the runner for legacy foundation DBs. Back up the DB first.

SQLite guards preserve source identity for all repair drafts; non-DRAFT content/deletion is frozen while review-owned status changes remain possible. Submitted snapshots are immutable via ORM and SQL guards. Closed challenges are frozen and delete is always soft. No existing Review/Audit trigger or simulation result is rewritten.

Older submitted records lacking a frozen snapshot are not fabricated or automatically approved: the review precondition port fails closed until a reviewed migration/backfill is supplied. The new tables are integration metadata; no public route is invented for them.

## Verification results

`python -m pytest backend/tests -q`: **100 passed**, one existing Starlette/httpx deprecation warning. Prompt A remains green. New tests cover Challenge 201/CRUD/readiness, all repair actions, request fields, draft edits/submission/version conflicts/freeze/delete restrictions, source/cross-case rejection, immutable PDFs, no fake clean-case resources, timeout/rate/schema/citation/neutrality failures, actual runtime model/request construction, audit delegation/rollback, concurrent same-key generation, expired leases, source changes during generation, typed readonly snapshots/review candidates and accurate OpenAPI/header/status schemas.

Temporary Uvicorn smoke: health HTTP 200, OpenAPI HTTP 200, 29 operations against migrated schema version 2. Windows initially held the temporary SQLite file during cleanup; it was removed after process exit. No server or synthetic smoke data remains. Positive generation tests use isolated test providers, never production fallbacks.

**Live OpenAI generation has not been executed** because authorized credentials/model/account access are not configured for a live validation run. No frontend, simulation engine or completed review workflow test is claimed.

## Merge notes for Aris

Merge after this shared-model/migration update, retain your immutable Simulation table and exact engine/data versions. Bind your lookup through SimulationLookup or use the readonly default if you persist the shared row shape. Persist baseline/alternative/delta metrics as integer IDR/counts; the repair renderer uses them verbatim and does not recalculate or substitute the golden fixture. Extend ReferenceLookup for any actual downstream challenge references. Keep contract fixture and negative-pack dataset versions separate.

## Merge notes for Fazhima

Bind your AuditService to the factory and preserve the passed Session transaction. All owned material writes and generation attempts must roll back together if audit recording fails. Consume ReviewCandidate submitted_version/snapshot and current case_version in your own atomic review command; preserve submitted snapshot content when changing repair disposition. Record the submitted version in your governed provenance where appropriate without adding unapproved request fields. Your review:decide authorization, decision semantics, assurance computation and immutable Review/Audit routes remain your responsibility. Do not use READY_FOR_REVIEW as final assurance approval.

## Remaining gaps and dependencies

Clean-case completion remains **OPEN / PROPOSED ADDENDUM**: no APPROVE_CASE, empty finding or fake repair is created. The challenge READY example versus human-readiness note, unspecified operational policies and schema clarifications remain explicitly recorded in CONTRACT_GAPS.md. Shared model/schema/migration changes require Teguh review on integration. Full-system 36-route regression, live provider validation and frontend integration still require owner work.
