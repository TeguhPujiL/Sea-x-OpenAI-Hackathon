# ProcureMind V4.1 contributor rules

Read docs/CONTRACT_LOCK.md, docs/CONTRACT_GAPS.md and docs/OWNERSHIP.md first. The primary API Contract v1.1 is currently missing: never claim compliance or infer missing contract details. Section 2.3 takes precedence when supplied.

- Work inside the assigned ownership boundary. Shared models/schemas require Teguh review.
- Use English source code, API fields, UI labels and technical docs.
- Use snake_case and closed request models; UUID v4; UTC with Z; integer IDR.
- Keep status domains separate. Preserve immutable execution, simulation, review and audit records.
- Implement exact idempotency and version semantics from the verified contract.
- Derive identity on the backend; demo identity alone is not access control.
- Never fabricate findings or hard-code live responses. Corrections are PROPOSED.
- Do not implement APPROVE_CASE or mix supplier data versions without approved revisions.
- Foundation scope: configuration, infrastructure, primitives and empty feature routers only.
- Run backend pytest and frontend typecheck; report unexecuted checks honestly.
