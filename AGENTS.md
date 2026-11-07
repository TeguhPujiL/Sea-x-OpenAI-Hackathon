# ProcureMind V4.1 team instructions

Read docs/CONTRACT_LOCK.md, docs/CONTRACT_GAPS.md and docs/OWNERSHIP.md before changes. Primary source: API Contract v1.1; Section 2.3 controls. Preserve exact snake_case wire names, enum values, status codes and canonical envelopes. Reject unknown request fields.

Use UUID v4, UTC with Z and integer IDR. Keep processing and business statuses distinct. AI executions, simulations, reviews and audit events are immutable. Never fabricate findings or live responses. Actor/reviewer identity comes from trusted backend context. Enforce case access on every feature lookup; demo identity is not case authorization.

Shared models/schemas require Teguh review. Work within ownership boundaries. Feature routers are intentionally empty; do not treat the contract inventory as implemented APIs. All proposed corrections stay PROPOSED; do not add APPROVE_CASE or mix supplier fixture versions. Idempotency/version declarations are integration primitives, not working business transactions.

Run backend pytest and frontend typecheck/build for relevant changes. Record only executed checks. No automatic production create_all. New feature owners must introduce migrations and atomic audit/idempotency transaction handling. The local .tools runtime and .venv are ignored and must not be committed.
