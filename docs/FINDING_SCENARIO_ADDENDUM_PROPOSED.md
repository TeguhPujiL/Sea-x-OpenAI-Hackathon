# PROPOSED v1.2 finding what-if scenarios — local opt-in experiment

Status: **PROPOSED / IMPLEMENTED LOCALLY / UNVERIFIED**. The user requested model-generated what-if scenarios for each finding type, with deterministic checks where possible. This extension requires Teguh/shared-contract review before merge or publication. It does not amend API Contract v1.1, replace Aris's supplier fixture engine, create APPROVE_CASE, or establish vendor compliance/approval.

The latest user instruction was to implement revisions without testing. No experimental migration, test suite, provider call, smoke check or application UI validation was executed for these modules. Test source is included for later authorized verification; there is no passing-test claim for this experiment.

## Integration and explicit activation

The package is `app.services.assurance.finding_scenarios`. Its `router.py` exports `router`; `migration.py` exports `migrate(engine)`; `provider.py` exports `OpenAIFindingScenarioProvider(settings)` with `generate(context) -> ProviderResult`. Tests can inject a clearly labeled test double at `app.state.finding_scenario_provider`; there is no fake-success production fallback.

The application composition must mount the router at `/api/v1/experimental` **only** when the local environment explicitly sets `PROCUREMIND_FINDING_SCENARIOS_ENABLED=1`. Default disabled behavior keeps the locked v1.1 route inventory unchanged. The composition must not run database DDL at startup.

The feature uses separate SQLAlchemy metadata. Its explicit migration requires already reviewed core/assurance tables and SQLite foreign keys enabled. A dedicated schema-version/checksum table tracks this experiment without changing the core SQLite `user_version`. Existing unversioned scenario tables or missing versioned tables are refused. Back up the local SQLite database before eventual manual migration:

```powershell
.\.venv\Scripts\python.exe scripts/migrate_finding_scenarios.py --database-url "sqlite:///<dedicated-local-database-path>"
```

This command is provided for later operator use and was **not run** during implementation.

## Proposed endpoints and wire contract

| Method | Experimental path | Success |
| --- | --- | --- |
| POST | `/cases/{case_id}/finding-simulations` | 201 |
| GET | `/cases/{case_id}/finding-simulations?limit=20&offset=0` | 200 |
| GET | `/finding-simulations/{scenario_id}` | 200 |

All paths are relative to `/api/v1/experimental`; no update/delete routes exist. Success responses add `X-Experimental-Contract: PROPOSED-v1.2`. Transport uses the existing canonical success/error envelope and `meta.api_version=v1`; that transport value is not approval of this proposed contract extension.

POST requires `simulation:write` and `Idempotency-Key`. Reads require `simulation:read`. Request properties are exactly:

```json
{
  "finding_id": "<UUID v4>",
  "expected_case_version": 1,
  "expected_finding_version": 1,
  "assumptions": []
}
```

Unknown fields are rejected; actor identity always comes from the trusted backend context. Every case/finding/scenario lookup enforces current case membership. Findings must be active, have a recorded non-deleted DRAFT/READY challenge, and come from a usable source analysis; source documents must remain readable, active, included in that analysis, and independently grounded in stored pages. The active challenge and its version enter the context fingerprint and are revalidated after generation. Original uncertain evidence remains visibly NEEDS_REVIEW.

Responses expose the agreed `scenario_id`, `case_id`, `finding_id`, `analysis_job_id`, `status` (DRAFT/NEEDS_REVIEW), `title`, `baseline` (description/assumptions/evidence), `alternatives` (title/change/expected_effect/limitations/evidence), `remaining_uncertainties`, `deterministic_checks`, actual `ai_execution` provenance, and `created_at` (UTC Z).

## Model scenarios and independent checks

The actual OpenAI Responses adapter uses the configured backend model/key, `max_retries=0`, `store=false`, and a strict structured-output schema adapted through the existing UUID helper. All supplied text, including user assumptions, is treated as untrusted evidence or hypothesis. Every baseline and alternative requires exact authorized source citations. Effects must be conditional and qualitative; uncertainties and limitations are mandatory.

The backend rejects model-generated numeric predictions and generated prose with digits/spelled-out quantities, percentages or unsupported verdicts. Exact source excerpts and verbatim user assumptions may contain source numbers. The guard is conservative and can reject benign English wording; no provider compatibility or response-quality claim is made before testing. Exact citations do not prove that an uncited semantic inference is correct: human source review remains required.

Deterministic checks establish source citation integrity and source document presence. A limited HPS parser independently reconciles integer subtotal/VAT/total figures only if the cited page contains unique, unambiguous matching labels and exact integer tax arithmetic. Multiple competing matches or unsupported rounding yield UNKNOWN. Any discrepancy is an arithmetic concern, never proof of financial loss. Other warranty, delivery, eligibility or financial-impact calculations remain explicitly UNKNOWN/NOT_APPLICABLE; no supplier counts, prices, probabilities or savings are invented by the model.

Every finding type can receive a qualitative what-if draft. Missing numeric methods do not become fabricated numerical results. Because unresolved quantitative methods remain UNKNOWN, these drafts can remain NEEDS_REVIEW even when citation grounding passes.

## Persistence and transaction semantics

`finding_scenarios` stores source case/finding versions, source analysis and execution IDs, trusted actor/request IDs, input-context digest, immutable payload, status and time. Foreign keys cover case, finding, source job and execution. A unique execution constraint, positive-version/status/JSON checks, source-association and citation-source insert guards, and UPDATE/DELETE triggers protect the feature records. Citation-source guards reject deleted/foreign/missing documents, missing or out-of-range pages and documents outside the source analysis. Exact excerpt validation remains a service check. No shared ORM model or core configuration file was modified by this package.

The existing operational generation-lease table scopes actor/route/key and protects in-flight duplicate generation. The model call runs outside the SQLite writer transaction. Final authorization, version and context checks run again before persistence. Execution, successful scenario (if any), delegated audit event and completed idempotency record are written in the same final transaction. A delegated audit failure rolls that final transaction back. The earlier operational lease can remain until expiry after a database/audit failure; it is not an orphan business result.

Completed idempotency replay occurs after authorization and before stale-version checks. Different input under the same key is rejected. Provider/schema/evidence failures preserve an actual immutable execution attempt and failure audit/idempotency response when the final transaction succeeds. Case/finding versions and assurance states are not incremented or changed by scenario generation.

External provider billing is not transactional with SQLite. Crashes, lease expiry, permission revocation or audit/database failure after a provider response can prevent persistence of that response. Exactly-once provider billing is not promised. Migration safety, concurrency, rollback behavior, SDK/schema compatibility and the supplied regression source remain unverified until the user authorizes testing.

The normal audit projection redacts unknown event details by default; the package stores material event detail but does not silently expand the owner-reviewed public audit allowlist. Authorized scenario detail exposes its explicit source evidence and immutable provenance.
