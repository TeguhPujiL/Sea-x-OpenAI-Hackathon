# Teguh P0 handoff - partial / contract blocked

## Branch and base

The teguh branch was fast-forwarded from ee49d6c to foundation commit d9f0bde. This brought in the existing empty teammate modules without changing their implementation. The PDF and evidence helpers are prepared for publication on teguh; full P0 implementation remains blocked on the primary contract.

## Changed files

- backend/app/services/__init__.py
- backend/app/services/documents/__init__.py
- backend/app/services/documents/pdf.py
- backend/app/services/documents/evidence.py
- backend/tests/test_pdf_evidence.py
- docs/TEGUH_P0_HANDOFF.md

## Implemented internal behavior

PyMuPDF parsing checks MIME, signature, byte/page/extracted-text limits, encryption, repaired/malformed documents and usable text. Results include UUID v4 document identity, SHA-256, one-based pages and normalized page text. Raw text is transient and not retained. Textless PDFs raise a dedicated internal extraction exception; no findings are created. Caller supplies explicit limits pending contract verification.

Evidence validation preserves case, punctuation and numeric content and normalizes whitespace only. Missing documents/pages and empty excerpts fail closed. The caller must load authorized persisted page text; this utility does not establish authorization.

## Schema and migration

No new tables, migrations, request/response schemas, business enums or error-code mappings. ExtractedPdf and ExtractedPage are immutable internal dataclasses, not wire schemas or durable records. No storage, database persistence or append-only record enforcement is claimed.

## Route matrix

| Area | State |
| --- | --- |
| GET /api/v1/health | Existing provisional foundation route |
| Cases create/list/detail/patch/delete | BLOCKED on exact contract schemas and status/error definitions |
| Document upload/list/detail/patch/delete | Internal extraction ready; HTTP/storage integration BLOCKED |
| Analysis create/job detail/list/retry | BLOCKED on contract and execution/persistence definitions |
| Finding list/detail/patch/dismissal | BLOCKED on enums, permissions and request/response definitions |
| Simulation, Review/Audit | Teammate-owned modules unchanged |

## Verification

Command: `.\.venv\Scripts\python.exe -m pytest backend/tests -q`

Result: 13 passed; one existing Starlette/httpx dependency deprecation warning. Covers real multipage PDFs/checksum, MIME/signature/malformed/oversized/encrypted/textless rejection, page/text limits, page-scoped matching, unauthorized-document absence, whitespace normalization and fabricated numeric/case changes. Also includes the original foundation smoke checks. AI, jobs, retries, stale versions, storage and endpoint authorization tests are NOT implemented or run. Frontend unchanged.

## AI failure modes and dependencies

No AI call or model output is implemented. Provider failures, invalid schemas, unresolved citations and terminal job persistence remain unverified. Required next input: the primary 39-page API Contract v1.1, including Section 2.3 and Appendix A/B. Also needed: configured provider/model, protected storage policy, trusted case-access policy and finalized-review evidence dependency from assurance. Do not infer these from the execution playbook or claim full P0 completion.

## Security and limits

No document contents or secrets are logged. Parser errors return generic internal messages. Bytes are not written or overwritten by this service. Future upload handlers must reject oversize streams before buffering; parser execution needs process-level time/memory limits. Finalized-review deletion protection and cross-case authorization require persistence integration. Encrypted PDFs are rejected rather than decrypted.

Reference: [PyMuPDF Document API](https://pymupdf.readthedocs.io/en/latest/document.html) and [Page API](https://pymupdf.readthedocs.io/en/latest/page.html).
