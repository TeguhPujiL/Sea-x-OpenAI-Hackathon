# Simulation implementation and integration

Implemented from the user's simulation requirements and supplied playbook/contract-lock excerpt.
The complete API Contract v1.1 sections 6.6 and 8, Appendix A/B, and approved
domain wire schemas are still absent from this checkout. This is not a claim of
full v1.1 compliance. No shared core, schema, model or other-owner file was changed.

## Files

- `app/api/routes/simulations.py`: three synchronous endpoints and local validation/error handling.
- `app/services/simulation/models.py`: closed, frozen, simulation-local input and fixture models.
- `app/services/simulation/engine.py`: pure integer engine, fixture verification and deterministic interpretation.
- `app/services/simulation/manifest.py`: immutable version-to-file registry and SHA-256.
- `app/services/simulation/fixtures/synthetic-suppliers-v1.json`: server-only golden supplier data.
- `app/services/simulation/repository.py`: SQLite append-only persistence.
- `app/services/simulation/service.py`: authorization checks, snapshots, creation, list and detail.
- `app/services/simulation/__init__.py`: package boundary.
- `tests/test_simulation.py`: engine, API, authorization, persistence and version-isolation tests.
- `app/services/simulation/INTEGRATION.md`: this handoff and examples.

## Fixture manifest and formulas

Engine: `simulation-engine-v1`. Supplier data: `synthetic-suppliers-v1`.
Source: user-confirmed contract golden fixture, not the negative PDF evidence pack.
SHA-256 (exact JSON bytes):
`452fe33326a14d9dccd6f44f2e5c0336243a9243949f5d33f1d9a6e7b60a945e`.

| Supplier | RAM GB | Unit price IDR | Quantity | Total IDR |
| --- | ---: | ---: | ---: | ---: |
| SYN-A | 16 | 13,200,000 | 50 | 660,000,000 |
| SYN-B | 16 | 13,800,000 | 50 | 690,000,000 |
| SYN-C | 32 | 16,500,000 | 50 | 825,000,000 |

For each scenario, eligible suppliers satisfy `ram_gb >= minimum_ram_gb`.
`eligible_supplier_count = len(eligible)`.
`lowest_total_offer_idr = min(unit_price_idr * quantity for eligible suppliers)`.
For both metrics, `delta = alternative - baseline`. All arithmetic uses Python
integers, including multiplication; no float conversion, AI output or live price call.

| Scenario | Eligible supplier count | Lowest total offer IDR |
| --- | ---: | ---: |
| Baseline 32 GB | 1 | 825,000,000 |
| Alternative 16 GB | 3 | 660,000,000 |
| Delta | +2 | -165,000,000 |

Deterministic golden interpretation:
“The alternative expands synthetic eligibility. The price delta is illustrative
and is not evidence of actual savings, loss, overpricing, collusion, or wrongdoing.”
For other inputs the eligibility verb is `reduces` or `preserves` as appropriate.

## API examples

These examples require a configured trusted authorization adapter and storage.
Use identifiers for a real persisted case and its related finding; example UUIDs
do not create resources or grant access. No supplier prices/records come from the browser.

```http
POST /api/v1/cases/11111111-1111-4111-8111-111111111111/simulations
Content-Type: application/json

{
  "finding_id": "22222222-2222-4222-8222-222222222222",
  "baseline": {"minimum_ram_gb": 32},
  "alternative": {"minimum_ram_gb": 16},
  "supplier_data_version": "synthetic-suppliers-v1"
}
```

Returns `201` synchronously. The existing four-key envelope is preserved:
`{"success":true,"data":<record>,"error":null,"meta":{}}`.
The record includes a new UUID v4 `simulation_id`, `case_id`, `finding_id`,
`engine_version`, `supplier_data_version`, `input_snapshot`, `result`,
`interpretation`, and server-generated UTC `created_at` ending in `Z`.
The complete input snapshot contains case/finding IDs, both normalized scenarios,
supplier data version, quantity, and all suppliers sorted by supplier ID. It
supports replay without reloading a mutable external dataset.

The exact golden `result` is:

```json
{
  "baseline": {"eligible_supplier_count": 1, "lowest_total_offer_idr": 825000000},
  "alternative": {"eligible_supplier_count": 3, "lowest_total_offer_idr": 660000000},
  "delta": {"eligible_supplier_count": 2, "lowest_total_offer_idr": -165000000}
}
```

```http
GET /api/v1/cases/11111111-1111-4111-8111-111111111111/simulations
GET /api/v1/simulations/<simulation_id-returned-by-post>
```

List returns `200` with `data` containing records in insertion order. Detail
returns `200` with `data` containing the record. There are no PATCH/DELETE routes.
Changed parameters create a separate record. Repeating identical inputs also
creates separate IDs/timestamps, with identical normalized snapshots, results
and interpretation for the same case, finding, fixture and engine version.

All unknown request fields (including operators, prices and supplier records),
missing/unknown data versions, malformed UUIDs/JSON, non-positive or non-integer
RAM, and empty eligible sets return `422` with `SIMULATION_INPUT_INVALID`.
Server fixture validation rejects negative, fractional, string and boolean IDR;
zero IDR is valid. It also rejects invalid quantity/RAM, empty datasets and
duplicate supplier IDs. Fixture integrity/configuration failures abort catalog
construction rather than letting the API run with unverified data.

Example unknown-version error:

```json
{
  "success": false,
  "data": null,
  "error": {"code": "SIMULATION_INPUT_INVALID", "message": "Unknown supplier_data_version"},
  "meta": {}
}
```

The error nesting, metric names, list shape, empty-set mapping and non-input
error codes remain simulation-local proposals pending the missing primary
contract and Teguh's shared-schema review. They must not silently become a
shared contract. No idempotency header semantics have been inferred.

## Teguh integration requirements

1. Provide approved response/error schemas, section 8 empty-set behavior and
   any required idempotency scope. Review the local wire types without altering
   the numerical golden fixture. Shared schemas were not changed.
2. Provision `SimulationRepository(path).provision()` during deployment setup;
   assign `app.state.simulation_service = SimulationService(repository,
   SupplierCatalog.packaged())` and close the repository at shutdown. There is
   no implicit table creation or fabricated case/finding data. This repository
   currently supports SQLite, with its own local table, not a migration in shared
   SQLAlchemy metadata. Coordinate migration/backend selection with persistence owner.
3. Trusted backend middleware must populate `request.state.simulation_access`
   with a request-scoped `SimulationAccess` implementation derived from real
   authenticated identity. `require_case(case_id)` must check persisted case
   access; `require_finding(case_id, finding_id)` must verify persisted finding
   access and case relationship. Both must raise `SimulationError` on denial.
   Demo identity or browser identity headers alone are insufficient. Case/finding
   owners must make these checks consistent with concurrent ownership changes.
   Tests use an explicit test-only adapter; no permissive production adapter exists.
4. Without configured storage/access the routes fail closed with `503
   SIMULATION_UNAVAILABLE`. Missing records return proposed `404
   SIMULATION_NOT_FOUND`; the test adapter's access denial uses proposed `403
   SIMULATION_ACCESS_DENIED`. Map these through the approved shared contract.
5. SQLite triggers reject UPDATE, DELETE and replacement of existing simulation
   IDs or storage sequence IDs, including a separate connection. This does not
   protect against an administrator dropping triggers/schema or replacing the
   database file. Production role and filesystem restrictions remain deployment work.
6. Include `app.services.simulation/fixtures/*.json` as package data in the
   shared build configuration before building wheels; source-checkout execution
   loads it directly. That configuration is outside Aris's ownership boundary.
7. Never overwrite an existing fixture version. Add a separately named fixture
   and manifest digest for any new dataset and new golden expectations. The
   negative PDF evidence pack has no registered supplier version here. Tests use
   a clearly named independent test-only version, not negative-pack prices.

## Verification

From `backend`, use an environment with the backend/test dependencies:

```sh
python -m pytest -q -p no:cacheprovider
```

Coverage includes exact golden values, canonical normalized replay after database
reopen, distinct records on changed parameters, SQL immutability, integer precision,
fixture tampering, version isolation, closed request validation, canonical four-key
envelopes and case/finding authorization on creation/list/detail.

The checked-in contract lock remains blocked; the supplied excerpt confirms
specific requirements but does not replace the missing primary sections/appendices.


## Update after merging origin/main 45b0c9e

The upstream foundation now contains a source-verified contract transcription,
shared envelope types and response helpers. Earlier missing-contract statements
above describe the original implementation baseline; consult the current
docs/CONTRACT_LOCK.md and docs/CONTRACT_GAPS.md for the updated source state.
The simulation router now uses shared success/failure helpers with request_id,
timestamp, api_version, error details and retryable. The service uses the new
UtcTimestamp serializer instead of removed utc_now/utc_z helpers.

This merge compatibility update preserves the local simulation behavior. Full
feature integration with the new foundation remains pending, including the
contract engine-version identifier, persisted response projection, pagination,
scope checks, transactional idempotency/audit, shared persistence and the
contract distinction between 400 VALIDATION_ERROR and 422 semantic errors.
The upstream foundation-only route test assumes no business routes exist and
must be updated by its owner when feature routes are integrated.
