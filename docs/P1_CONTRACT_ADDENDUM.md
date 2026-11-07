# P1.1 Evaluation Integrity and Supplier Readiness

Status: **PROPOSED / NOT AN APPROVED REVISION OF P0 v1.1**.

Source: Prompting P1.pdf, 15 pages, implementation prompts 01 and 02. The user requested both on branch teguh. API Contract v1.1 Section 2.3 remains authoritative for P0. Integration Lead approval of this concrete addendum is still required before enabling P1 for shared environments. Implementations and tests are opt-in using PROCUREMIND_P1_ENABLED=true; default OpenAPI and P0 routes remain unchanged. No frontend, Simulation or Assurance decision logic is changed.

Local pilot only: the user authorized activation on 7 November 2026. The local backend is enabled after explicit migration and backup; this does not approve this addendum for shared environments.

## Proposed routes

All paths are under /api/v1. POSTs require Idempotency-Key, analysis:write and a backend analyst/reviewer/admin role. Reads require analysis:read and persisted case membership. Identity is server-derived. Unknown JSON/query fields are rejected; UUID v4, UTC Z, canonical success/data/error/meta, existing Appendix B errors and integer numerical thresholds apply. Every create returns 202 with an existing JobView. Poll the existing GET /jobs/{job_id}; its DOCUMENT_ANALYSIS job type and requirement_count/finding_ids result shape are retained. The assessment response provides job_id, check_id and detailed results. No separate job/upload/finding/review/audit endpoint is introduced.

| Method | Path | Code |
| --- | --- | --- |
| POST | /cases/{case_id}/evaluation-checks | 202 |
| GET | /cases/{case_id}/evaluation-checks | 200 |
| GET | /evaluation-checks/{check_id} | 200 |
| POST | /cases/{case_id}/supplier-readiness-checks | 202 |
| GET | /cases/{case_id}/supplier-readiness-checks | 200 |
| GET | /supplier-readiness-checks/{check_id} | 200 |
| POST | /supplier-readiness-checks/{check_id}/revalidations | 202 |

List data has items and pagination (limit default20/max100, offset>=0). Create/replay authorization precedes idempotency lookup. A new request after changed documents creates a new immutable assessment. Revalidation POST uses the same fields as readiness create; supplier_ref and requirement_document_ids must match its predecessor, and references a terminal predecessor with expected_version. expected_version is the immutable assessment lineage version (starts1); a prior version can branch deliberately rather than overwrite history. Supplementary documents use existing upload APIs and new IDs. Generic P0 job retries reject P1 jobs; create a new assessment/revalidation instead, preventing accidental dispatch through P0 analysis. No mutation or deletion of assessment/execution/snapshot records is exposed.

## Requests

Evaluation: evaluation_document_id, supplier_document_ids (possibly empty), criteria_document_ids (nonempty), check_types (nonempty unique subset of CRITERIA_CONSISTENCY, EVIDENCE_VERIFICATION, DECISION_CONSISTENCY). The evaluation document must be EVALUATION_REPORT; criteria must be TOR or TECHNICAL_SPECIFICATION. Supplier evidence accepts SUPPLIER_QUOTATION/WARRANTY_EVIDENCE/OTHER. Duplicate IDs or SHA-256 content across any selected roles are rejected. The caller selects an explicit document snapshot; absence conclusions concern only that snapshot.

Readiness: supplier_ref (1-100 characters), requirement_document_ids (nonempty), supplier_document_ids (possibly empty), include_remediation_guidance (boolean default true). Revalidation additionally requires expected_version. Numeric/date checks use the assessment UTC creation date as the recorded reference date, never a mutable wall clock during result rendering. There is no supplier authentication portal: current backend roles and case membership authorize analysts; supplier-role access is unavailable and fails closed pending a versioned supplier ACL design. Document ownership assertions require independently matching supplier identity in source text, not the model's supplier label alone.

## Resources and statuses

AssessmentView contains check_id, case_id, job_id, kind (EVALUATION/READINESS), version, previous_check_id/null, supplier_ref/null, status (existing ProcessingStatus), ai_execution_id/null, reference_date, summary, items (evaluation) or requirements (readiness), finding_ids, changes, created_at. Queued/failed results have empty summary/items/requirements, never a clean-success assertion. All result fields are required in the proposed schema. changes lists requirement_id, before_status and after_status relative to the previous immutable snapshot; duplicate requirement/supplier keys are invalid AI output. Independent citation evidence always includes verification_status; invalid citations never create a VERIFIED result or finding.

Readiness item: requirement_id, description, mandatory (boolean/null), required_value/actual_value (integer/null), unit, readiness_status (VERIFIED/MISSING/NEEDS_REVIEW/NOT_APPLICABLE/NON_COMPLIANT), evidence, explanation, recommended_action/null, requires_human_review. Governing criterion citations and supplier citations are included together. NOT_APPLICABLE requires a verified explicit criterion supplier restriction; uncertainty stays NEEDS_REVIEW.

Evaluation item: supplier_ref, criterion_id, criterion_description, recorded_decision (COMPLIANT/NON_COMPLIANT/NOT_EVALUATED/AMBIGUOUS), evidence_assessment (SUPPORTED/UNSUPPORTED/MISSING/AMBIGUOUS/NOT_APPLICABLE), consistency_result (CONSISTENT/INCONSISTENT/NEEDS_REVIEW), explanation, evidence, recommended_action. INCONSISTENT yields an existing P0 finding with type EVALUATION_DECISION_INCONSISTENCY, severity MEDIUM and VERIFIED source citations only; no finding is made for inconclusive or matching results. These new labels do not extend P0 closed enums. Risk severity remains distinct from processing status.

AI performs schema-constrained requirement/observation/decision extraction. Backend verifies every excerpt against authorized stored page text, then independently parses explicit RAM GB, warranty years/months, delivery days, quantity and ISO validity dates. Ambiguous numeric contexts, mixed suppliers, unverifiable identity, contextual-only compliance or ambiguous/expired validity produce NEEDS_REVIEW; presence alone never proves compliance. Values claimed by AI must equal unique values parsed from cited excerpts. Dates must be explicitly cited. Neither legal validity, signature authenticity nor misconduct is determined. Guidance is controlled, neutral, conditional on permitted clarification, and never directs altering official evidence.

## Persistence, provenance and human workflow

Explicit P1 migration adds p1_checks and p1_check_results plus a migration ledger, referencing existing AnalysisJob/AiExecution/case tables. No P0 columns/enums/records are rewritten. Creation snapshots, results and migration revisions are append-only, protected by SQLite triggers. Worker uses existing job transitions and trusted actor authorization, rechecks document snapshots before persistence, stores actual runtime model or null, operation, prompt_version, schema/evidence flags, checks, latency, usage/null, warnings; immutable findings/evidence use existing tables. AuditService records creation, completion and revalidation inside caller transactions, never commits from an adapter. P1 migration is an explicit CLI step and is not run automatically on app startup.

Human confirmation uses existing finding PATCH status=UNDER_REVIEW with expected_version; dismissal uses existing dismissals with rationale. Request additional evidence via existing evidence-grounded Challenge creation; request re-evaluation by creating another evaluation check after authorized supplementary uploads. These commands already write delegated audit records. No fabricated repair or APPROVE_CASE decision is added. Formal assurance continues to require an actual submitted repair under v1.1; G01 remains open. Prior evaluations, uploaded bytes, assessments and reviewer history are retained.

## Open decisions

Integration Lead must approve route/status/scope/schema policies above before activation. Dedicated supplier identity bindings/ACL, document validity authority, OCR, a distributed queue, clean-case completion and general semantic compliance automation remain unresolved. Contextual assessments always require a person; numeric checks are bounded to explicit supported units and unambiguous citations. Frontend integration is a separate owner task after addendum approval. No live inference or deployment is implied by fixture tests.
