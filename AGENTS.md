# ProcureMind V4.1 team instructions

Read docs/CONTRACT_LOCK.md, docs/CONTRACT_GAPS.md and docs/OWNERSHIP.md before changes. Primary source: API Contract v1.1; Section 2.3 controls. Preserve exact snake_case wire names, enum values, status codes and canonical envelopes. Reject unknown request fields.

Use UUID v4, UTC with Z and integer IDR. Keep processing and business statuses distinct. AI executions, simulations, reviews and audit events are immutable. Never fabricate findings or live responses. Actor/reviewer identity comes from trusted backend context. Enforce case access on every feature lookup; demo identity is not case authorization.

Shared models/schemas require Teguh review. Work within ownership boundaries. Case/document/analysis/job/finding P0 routes are implemented. Challenge/repair remain empty, and teammate routers are excluded from this branch. Do not treat the full 36-route contract inventory as implemented APIs. All proposed corrections stay PROPOSED; do not add APPROVE_CASE or mix supplier fixture versions. Owned mutations enforce idempotency/version checks with atomic audit writes; preserve these transaction boundaries.

Run backend pytest and frontend typecheck/build for relevant changes. Record only executed checks. No automatic production create_all. Run the explicit SQLite migration before serving feature requests. Preserve migration data, backend case membership, immutable provenance, and atomic audit/idempotency handling. The local .tools runtime and .venv are ignored and must not be committed.
