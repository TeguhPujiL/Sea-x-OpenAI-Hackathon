# ProcureMind V4.1 team instructions

Read docs/CONTRACT_LOCK.md, docs/CONTRACT_GAPS.md and docs/OWNERSHIP.md before changes. Primary source: API Contract v1.1; Section 2.3 controls. Preserve exact snake_case wire names, enum values, status codes and canonical envelopes. Reject unknown request fields.

Use UUID v4, UTC with Z and integer IDR. Keep processing and business statuses distinct. AI executions, simulations, reviews and audit events are immutable. Never fabricate findings or live responses. Actor/reviewer identity comes from trusted backend context. Enforce case access on every feature lookup; demo identity is not case authorization.

Shared models/schemas require Teguh review. Work within ownership boundaries. All 28 Teguh case/document/analysis/job/finding/challenge/repair routes are implemented; Simulation/Review/Audit routers remain teammate-owned and excluded. Do not treat the full 36-route contract inventory as implemented APIs. All proposed corrections stay PROPOSED; do not add APPROVE_CASE or mix supplier fixture versions. Owned mutations enforce idempotency/version checks with atomic audit writes; preserve these transaction boundaries.

Run backend pytest and frontend typecheck/build for relevant changes. Record only executed checks. No automatic production create_all. Run the explicit SQLite migration before serving feature requests. Preserve migration data, backend case membership, immutable provenance, and atomic audit/idempotency handling. The local .tools runtime and .venv are ignored and must not be committed.

New decision services must use AuditService delegation inside the caller transaction. Never commit from an adapter or implement teammate decision/calculation logic. Preserve submitted repair snapshots and typed integration ports. Run explicit SQLite migration 0002 before requests; do not fabricate legacy submission history.
