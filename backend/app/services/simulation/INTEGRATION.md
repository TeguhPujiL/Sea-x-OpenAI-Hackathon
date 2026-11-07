# Deterministic simulation: contract verification and handoff

## Verified sources and precedence

- API Contract v1.1: `8. ProcureMind_V4_1_API_Contract.pdf`, supplied in the user's
  Downloads directory, 39 pages; SHA-256
  `fcc0388407f9cac2804b71be151f41a444a546bfa5d6648ac2ef33a4a40aecdc`.
  Sections 2.3, 3, 6.6 (pages 22-26), 8 (page 35), Appendix A/B (pages 37-39)
  control this implementation. The hash matches the checked-in contract lock.
- PRD: `1. ProcureMind_PRD_V4.1_Enhanced.pdf`, 24 pages; SHA-256
  `f591154dd1c39a3093bd371f550b40b39188c0a46697fb2e978da302a63c84fd`.
  US-D02 on page 11 requests eligibility identifiers, assumptions and input hash.
- Execution Playbook: secondary team/ownership guidance, especially pages 3 and 13.
- Current `docs/CONTRACT_LOCK.md`, `docs/CONTRACT_GAPS.md`, and approved shared
  schemas/models are used directly; no shared declaration was changed.

The PRD's older `/v1/.../scenarios`, scenario request fields, and error naming
are not substituted for v1.1's `/api/v1/.../simulations` and canonical envelope.
Additional PRD reproducibility metadata is retained internally without adding
unapproved fields to the Section 6.6 wire response. Shared schema changes still
require Teguh review. This does not claim integrated release readiness.

## Changed files

- `app/api/routes/simulations.py`: strict three-route API, scopes, idempotency
  header, canonical envelopes, typed OpenAPI and pagination.
- `app/services/simulation/models.py`: simulation-local closed wire schemas and
  `supplier_ref` projection, using the approved shared envelope/money/time types.
- `app/services/simulation/engine.py`: contract engine identifier.
- `app/services/simulation/service.py`: deterministic snapshots, input hashes,
  eligibility identifiers, assumptions, read authorization and wire projection.
- `app/services/simulation/shared_repository.py`: shared-table persistence,
  live reference checks, atomic simulation/audit/idempotency transaction and replay.
- `app/services/simulation/migrate.py`: explicit SQLite immutability guard migration.
- `tests/test_simulation.py`: updated contract assertions and deterministic IDs.
- `tests/test_foundation.py`: user-authorized fix for the obsolete health-only assertion.
- `tests/test_simulation_shared.py`: real shared-database integration regressions.
- `app/services/simulation/INTEGRATION.md`: this handoff.

The existing `repository.py` remains a standalone historical test-store adapter.
It is not used by the HTTP routes and must not be pointed at the shared database.
No shared schemas, models, core code, assurance internals or frontend sources changed.

## Fixture manifest and exact formula

Engine: `supplier-eligibility-v1`. Supplier data: `synthetic-suppliers-v1`.
Source: v1.1 golden fixture, not the negative PDF evidence pack.

File: `fixtures/synthetic-suppliers-v1.json`.
SHA-256 (unchanged exact bytes):
`452fe33326a14d9dccd6f44f2e5c0336243a9243949f5d33f1d9a6e7b60a945e`.
The explicit version/file/digest registry is in `manifest.py`. Published fixture
bytes still use the original internal `supplier_id` key; the loader normalizes
that key and all wire snapshots use the contracted `supplier_ref`. No prices,
RAM mapping, quantity or fixture bytes were rewritten under an existing version.

| Supplier | RAM GB | Unit price IDR | Quantity | Total IDR |
| --- | ---: | ---: | ---: | ---: |
| SYN-A | 16 | 13,200,000 | 50 | 660,000,000 |
| SYN-B | 16 | 13,800,000 | 50 | 690,000,000 |
| SYN-C | 32 | 16,500,000 | 50 | 825,000,000 |

For each scenario:

```text
eligible = supplier.ram_gb >= minimum_ram_gb
eligible_supplier_count = len(eligible)
lowest_total_offer_idr = min(unit_price_idr * quantity for eligible suppliers)
delta.metric = alternative.metric - baseline.metric
```

Only integer arithmetic is used. Quantity belongs to the selected synthetic
fixture version; it is never supplied by the browser or guessed by an LLM.

| Scenario | Count | Lowest total IDR |
| --- | ---: | ---: |
| Baseline 32 GB | 1 | 825,000,000 |
| Alternative 16 GB | 3 | 660,000,000 |
| Delta | +2 | -165,000,000 |

The deterministic golden interpretation states: “The alternative expands
synthetic eligibility. The price delta is illustrative and is not evidence of
actual savings, loss, overpricing, collusion, or wrongdoing.” Other scenarios
use `reduces` or `preserves` when the eligible count changes differently.

## API examples

These requests require a provisioned database, an authenticated backend actor
with the relevant scope and a trusted case-access policy. The example IDs must
refer to an existing case and its persisted finding; examples do not create them.

```http
POST /api/v1/cases/11111111-1111-4111-8111-111111111111/simulations
Content-Type: application/json
Accept: application/json
Idempotency-Key: golden-simulation-001

{
  "finding_id": "22222222-2222-4222-8222-222222222222",
  "baseline": {"minimum_ram_gb": 32},
  "alternative": {"minimum_ram_gb": 16},
  "supplier_data_version": "synthetic-suppliers-v1"
}
```

Returns `201` synchronously with `success`, `data`, `error`, `meta`.
`data` has exactly `simulation_id`, `case_id`, `finding_id`, `engine_version`,
`input_snapshot`, `result`, `interpretation`, `created_at`. IDs are UUID v4;
`created_at` is server-generated UTC with Z. `meta` contains `request_id`,
`timestamp` and `api_version: "v1"`.

The public `input_snapshot` has exactly `quantity`, `baseline`, `alternative`,
`suppliers`; each supplier has `supplier_ref`, `ram_gb`, `unit_price_idr`.
The exact golden result is:

```json
{
  "baseline": {"eligible_supplier_count": 1, "lowest_total_offer_idr": 825000000},
  "alternative": {"eligible_supplier_count": 3, "lowest_total_offer_idr": 660000000},
  "delta": {"eligible_supplier_count": 2, "lowest_total_offer_idr": -165000000}
}
```

```http
GET /api/v1/cases/11111111-1111-4111-8111-111111111111/simulations?limit=20&offset=0
GET /api/v1/simulations/<simulation_id-returned-by-post>
```

List returns `200` and `data.items` plus `data.pagination` (`limit`, `offset`,
`total`), in creation-time/ID order. Detail returns `200` and the same record
projection. There are no PATCH or DELETE endpoints.

Unknown supplier versions, invalid RAM, missing versions and empty eligible
sets return `422 SIMULATION_INPUT_INVALID`. Malformed JSON, unknown fields
(including operators/prices/supplier records), invalid resource IDs and invalid
pagination use `400 VALIDATION_ERROR` per Appendix B. A missing/blank idempotency
key uses the existing shared `400 VALIDATION_ERROR` policy. No unknown error code
is introduced. Errors have `code`, `message`, `details`, `retryable` plus metadata;
request values, document text and internal exception details are not echoed.

## Persistence, reproducibility and PRD mapping

HTTP creation uses existing shared `Simulation`, `AuditEvent` and
`IdempotencyRecord` models. All three writes commit or roll back together.
The engine/supplier versions and complete normalized snapshot are persisted.
The internal snapshot additionally retains case/finding IDs, supplier version
and `provenance` with:

- `input_hash`: SHA-256 of canonical JSON containing the engine version and
  complete normalized input, before adding the provenance object itself.
- `eligible_supplier_ids`: baseline/alternative lists computed by the engine's
  RAM predicate and sorted by supplier reference.
- `assumptions`: explicit synthetic-data, fixed-quantity and RAM-only limits.

This maps PRD US-D02 without introducing PRD-only wire fields or endpoints.
No new database columns are required. The public snapshot is an intentional
Section 6.6 projection; the full persisted snapshot supports internal replay.
G07 remains open: supplier_data_version is persisted but is not silently added
as an outer response field.

Idempotency scope is actor + POST + concrete case route + key. The normalized
request hash includes case ID and the validated request. Reordered JSON keys
replay identically. Same key/different normalized input returns `409
IDEMPOTENCY_KEY_REUSED`; a new key creates a new immutable record. Existing
idempotency rows are checked before recomputation, after access/reference checks.
SQLite writers use BEGIN IMMEDIATE, and the unique key constraint handles races.
Audit records reference the trusted actor, request ID, simulation, versions,
input hash and scenario thresholds. The local `SIMULATION_CREATED` event name is
an implementation identifier, not a newly invented closed shared enum.

PROPOSED operational choices under G09: replay returns the stored `201` envelope
(including original metadata); the current transport X-Request-ID may differ.
No TTL/purge policy is added. List defaults are limit=20 and offset=0, with no
invented contract maximum. Missing/cross-case/deleted references use 404; explicit
ACL denials use the adapter's approved 403/404 policy. These choices require
integration-owner review before release.

## Integration and migration requirements

1. Provision the shared schema through the persistence owner's migration/setup.
   No simulation route creates tables. On an existing SQLite schema run:

   ```sh
   python -m app.services.simulation.migrate --database-url sqlite:///procuremind.db
   ```

   This repeatable migration installs UPDATE, DELETE and REPLACE guards only.
   It does not create or alter shared table/column declarations. It is SQLite-only.
   Database administrators can still drop schema or replace files; deployment
   privileges and backups remain necessary.
2. The router obtains `app.state.session_factory` from the existing application
   lifespan. No manually assigned `app.state.simulation_service` is required.
   It uses shared `simulation:write` / `simulation:read` scope dependencies and
   the shared Idempotency-Key dependency.
3. Trusted authentication/ACL middleware must populate request-scoped
   `request.state.simulation_access`, bound to the backend-authenticated actor.
   Its `require_case(case_id)` and `require_finding(case_id, finding_id)` methods
   must enforce the real policy and raise ApiError or SimulationError on denial.
   `PersistedSimulationAccess` independently verifies case existence, deletion
   state and finding/case relationships. Identity alone or browser headers never
   grant case access. No permissive production adapter or fabricated cases exist.
   Missing identity returns 401; missing scope returns 403; a missing configured
   ACL adapter returns 500 INTERNAL_ERROR without exposing resource data.
4. Coordinate ACL changes and transaction isolation with case owners so concurrent
   access changes follow the team's reviewed policy. SQLite references are checked
   again inside the write transaction. Production OIDC is still outside this module.
5. The shared build owner must include `app.services.simulation/fixtures/*.json`
   as package data before building wheels. Source-checkout execution is verified;
   wheel packaging remains an integration gate outside this ownership boundary.
6. Never overwrite a published supplier version. Add separately named fixtures,
   digests and golden expectations for future data. The negative PDF pack's
   710M/835M/680M values are not registered here. Test-only independent-v2 uses
   separate explicit data and is not a negative-pack fixture.
7. The old standalone store has a different schema. Do not reuse its database as
   the shared database or silently mutate historical records. Coordinate any
   historical migration with persistence owner. Existing records remain immutable.
8. The user explicitly requested fixing the stale foundation route assertion.
   `tests/test_foundation.py::test_registered_routes_follow_contract_inventory`
   now requires health and validates every registered business method/path and
   success status against the checked-in contract inventory. It permits the
   staged addition of contracted feature routers without permitting new APIs.

## Verification commands

```sh
python -m pytest tests/test_simulation.py tests/test_simulation_shared.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
```

Coverage includes exact golden values and wire shapes, normalized replay,
input hash and eligibility provenance, reopen persistence, SQL immutability,
fixture integrity/version isolation, structural/scenario error distinction,
scopes, trusted case ACL, persisted cross-case relationships, soft deletion,
audit rollback, concurrent same-key creation and actor/route idempotency scope.
The stale foundation-only route assertion was replaced with a contract-inventory
check at the user's explicit request. The full backend suite is rerun after this fix.

Frontend typecheck and production build were run successfully against a temporary
copy of the unchanged frontend using its package-lock.json and npm ci. No source,
node_modules, lockfile or build artifacts were added to the repository for that check.
