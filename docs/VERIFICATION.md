# Contract documentation and foundation verification

Branch: main. Current tree contains documentation only after the user-requested cleanup. Source verification is separate from runtime compliance. No historical test result is carried forward for deleted application code.

## Executed source and documentation checks

Executed with Python against the supplied PDF and its temporary page-addressable text extraction:

| Check | Result |
| --- | --- |
| PDF page count and SHA-256 identity | PASS: 39 pages; hash matches CONTRACT_LOCK.md and snapshot |
| Endpoint extraction from Section 6 method/purpose/scope/success blocks | PASS: 36 unique method/path pairs |
| Snapshot and Markdown endpoint/code correspondence | PASS: 36 entries; GET/PATCH/DELETE 200, creates 201 except analyses/retries 202 |
| Idempotency route set from Section 3.2 | PASS: 6 mandatory POST route patterns |
| All named enum transcriptions compared with Appendix A text | PASS: 12 exact declarations |
| Appendix B code sequence and count | PASS: all 16 codes in source order |
| Success and error envelope examples | PASS: JSON parses; exact top-level/meta keys; timestamps end Z |
| APPROVE_CASE exclusion | PASS: absent from ReviewDecision |
| Markdown links and source-document whitespace | PASS: local targets exist; no trailing spaces; final newlines |

The temporary full-text PDF extraction was removed after checking; the source PDF remains unchanged in Downloads. Snapshot source_page values point to the physical PDF pages. Snapshot is not a generated OpenAPI schema or a passing API contract regression test.

## Required foundation checks

| Required check | Current result | Reason |
| --- | --- | --- |
| FastAPI starts | NOT RUN / BLOCKED | Backend absent |
| GET /api/v1/health returns canonical envelope | NOT RUN / BLOCKED | Backend absent; health schema is an open foundation gap |
| GET /openapi.json works | NOT RUN / BLOCKED | Backend absent; envelope exception remains proposed |
| Frontend development server starts | NOT RUN / BLOCKED | Frontend absent |
| Python application imports | NOT RUN / BLOCKED | Application absent |
| pytest smoke test | NOT RUN / BLOCKED | Tests and manifest absent |
| TypeScript typecheck | NOT RUN / BLOCKED | Frontend and manifest absent |
| Implemented OpenAPI contract regression | NOT RUN / BLOCKED | Runtime OpenAPI absent |

No teammate-owned features, application tests, dependency installation or runtime behavior are claimed as completed. See README.md for conditional future install/run commands and CONTRACT_GAPS.md for decisions needing review.
