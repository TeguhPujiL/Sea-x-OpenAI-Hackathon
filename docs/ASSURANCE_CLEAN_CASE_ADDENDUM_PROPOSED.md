# G01: clean-case completion addendum

Status: **PROPOSED ONLY. NOT APPROVED. NOT IMPLEMENTED.** Target revision and owner approval remain unset.

API Contract v1.1 pages 29 and 38 require repair_proposal_id and enumerate only APPROVE_DRAFT, REQUEST_REVISION, REQUEST_EVIDENCE and REJECT_DRAFT. Page 37 requires no contradiction to produce finding_ids=[]. A clean case therefore cannot honestly produce the repair required by the review command. The regression suite rejects APPROVE_CASE, omission of repair_proposal_id, and a repair borrowed from another case. No finding or repair is created to bypass this gap.

Proposed direction for formal review: introduce a separate, versioned human confirmation command for a case with no findings, rather than expanding ReviewDecision implicitly. A possible name is POST /cases/{case_id}/assurance-completions; this is documentation, not an available endpoint or an OpenAPI declaration.

The addendum must settle these requirements together:

1. The request identifies the completed analysis and frozen document versions, carries a meaningful reason and expected_case_version, and contains no repair or client-authored identity/assurance status.
2. Backend authentication, explicit case authorization and a reviewed decision scope apply. Human identity is captured as an immutable snapshot.
3. All relevant current analyses are usable and completed, finding_ids=[] agrees with persisted findings, source documents remain accessible and live, and no unresolved evidence warning or in-flight analysis exists. Severity/confidence alone never proves a clean result.
4. A human confirmation means internal assurance only. The server computes the outcome; case_status and assurance_status stay separate. Exact permitted starting states and resulting transitions need an approved table.
5. An immutable completion record references the frozen analysis/document set. Case version increment, record creation, material audit event(s), and idempotency replay persistence are one transaction.
6. The addendum defines canonical request/response shapes, success/error codes, idempotency replay ordering/retention, soft-delete restrictions, concurrency and authorized list/detail reads. There are no completion update/delete routes.
7. Acceptance tests cover successful no-findings confirmation, warning/failure/in-flight analysis, newly introduced findings, concurrent evidence changes, unauthorized cross-case IDs, stale version, transport retry and restart persistence.

Required approvals: contract/integration owner Teguh and the review/QA owner, followed by a versioned contract revision, updated OpenAPI and checked-in regression snapshot. Until then the user-facing state should read **NO_FINDINGS — completion blocked by contract gap G01**. The current frontend is a shell and does not yet implement that state; the fallback command prints the blocker explicitly.
