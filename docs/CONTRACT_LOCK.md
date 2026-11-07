# Contract lock - BLOCKED / NOT VERIFIED

The 39-page ProcureMind V4.1 API Contract & Integration Specification v1.1 has not been supplied. Section 2.3 must take precedence when it becomes available. The 19-page execution playbook is secondary guidance, not a substitute for the primary contract. No contract lock or feature integration gate is passed.

## Confirmed user requirements

- REST base path `/api/v1`; snake_case JSON; reject unknown request fields.
- Application JSON responses contain success, data, error, meta.
- UUID v4 identifiers, aware UTC timestamps serialized with Z, integer IDR.
- Distinct job, case, finding, repair and assurance status domains.
- Immutable AI execution, simulation, review and audit records.
- Contracted Idempotency-Key scope and optimistic concurrency must be enforced when implementing features.
- Actor/reviewer identity comes from trusted backend context.
- Never fabricate findings or live responses.

## Endpoint inventory

| Method | Path | Success | Source / state |
| --- | --- | --- | --- |
| GET | /api/v1/health | 200 | Playbook foundation gate; implemented; data shape PROPOSED |
| GET | /openapi.json | 200 | Framework schema; native OpenAPI format |

Feature router modules are empty. Exact endpoint inventory, statuses, request fields, business enums, error codes, idempotency scope and nested envelope schemas remain BLOCKED on the primary contract. Do not infer missing methods or paths from module names.

## PROPOSED development envelope

Success: `{"success": true, "data": {"status": "ok"}, "error": null, "meta": {}}`.
Error: `{"success": false, "data": null, "error": {"message": "..."}, "meta": {}}`.
Only the four top-level keys are user-confirmed. All nested shapes above are PROPOSED and must be replaced or confirmed from v1.1 before integration. OpenAPI is a framework document, not an application response; this exception needs primary-contract verification. API error details and codes are deliberately not guessed.

## Lock completion gate

1. Read all 39 pages; record source path and SHA-256.
2. Extract Section 2.3, endpoint/method/status inventory and Appendix A/B.
3. Verify every enum, envelope, request schema, header and version field.
4. Add reviewed domain declarations, constraints, exact wire schemas and router signatures.
5. Verify application errors, idempotency, access and concurrency against the contract.
6. Check in reviewed OpenAPI snapshot and run contract regression.

No feature implementation or release compliance is claimed by this scaffold.
