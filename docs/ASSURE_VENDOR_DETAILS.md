# Assure vendor offers and repair results

Assure now shows source-labelled offer details for each vendor/package selected in the current analysis: supplier/model, quantity, quoted total and unit price, line-item total, tax basis, memory, processor, storage, display/security/OS, warranty, delivery and offer validity. Missing or unrecognizable labels remain explicitly unavailable. Multiple recorded values remain separate, with source document IDs, filenames, pages and exact excerpts. No prices are borrowed from the synthetic simulation fixture or inferred by an AI model.

An experimental read-only endpoint supplies these facts from the stored extracted pages:

`GET /api/v1/experimental/cases/{case_id}/vendor-assurance-summary?analysis_job_id={analysis_job_id}`

It is mounted only with the existing opt-in prototype flag. It requires case, document, analysis, finding, repair and review read scopes plus current backend case access. Documents are restricted to active, extracted quotation/warranty sources included in the requested case analysis. It adds no database table or migration and performs no AI request or business mutation. Like the existing experimental scenario endpoints, this is an owner-review prototype extension, not an amendment to the locked released v1.1 contract.

The original-finding baseline is the earliest usable case analysis that actually recorded findings; if none recorded findings, the earliest usable analysis is retained. Its immutable finding content is displayed with the finding's current recorded status, real linked repair proposals, and immutable review decisions. Vendor associations use the same filename/source-package rules as Assess. Shared original findings appear under affected vendors.

Results distinguish:

- No linked repair proposal recorded.
- A real repair proposal exists, with its actual draft/submission/disposition status and text.
- A finding is explicitly RESOLVED or DISMISSED in its recorded workflow state.
- New vendor evidence is included in a later analysis.
- A later assessment returns no current vendor findings, without silently changing the original finding to repaired/resolved.

Both the on-screen summary and PDF comparison include offer facts and original repair outcomes. Vendor preference and the existing finding-count colors remain separate from a procurement award or final assurance approval.

Per the user's instruction, implementation is built for manual review without running unit tests, a test bot, provider generation or scenario execution. The label-based parser is deliberately conservative and may leave unfamiliar PDF layouts unextracted; source inspection remains available.

## Local GO / NO-GO addendum - PROPOSED-v1.2

The user requested a final internal procurement conclusion after vendor comparison. This remains an opt-in local prototype under `PROCUREMIND_FINDING_SCENARIOS_ENABLED=1` and demo mode. Shared-model/contract owner review by Teguh remains required before integration as a released contract. No `APPROVE_CASE` command, fabricated repair/finding, CaseStatus mutation or AssuranceStatus mutation is introduced. G01 remains open.

- `GET /api/v1/experimental/cases/{case_id}/procurement-conclusions?analysis_job_id=...` returns `{conclusion: record|null}` in the canonical envelope.
- `POST /api/v1/experimental/cases/{case_id}/procurement-conclusions` returns 201. Strict fields: `analysis_job_id`, `decision` (`GO` or `NO_GO`), `selected_vendor_id` (nullable), `decision_reason`, `expected_case_version`, `vendor_review_confirmed`. Unknown fields, including client-authored reviewer, are rejected.
- POST requires `review:decide`, read scopes for the included resources, case membership, and Idempotency-Key. Replay is actor/route/payload scoped. New writes require current case version, the latest usable terminal assessment and accessible active source documents. One immutable conclusion is permitted per case/analysis. A new analysis allows a new conclusion while preserving history.
- GO requires a selected filename-associated vendor with an analyzed readable quotation, an explicit human evidence-review confirmation and a meaningful reason (four words, 20-4000 characters). This is a human internal recommendation: it does not automatically establish compliance, resolve findings, certify eligibility or authorize an award. Remaining concerns stay visible and must be addressed in the human decision reason.
- NO_GO requires a null selected vendor; its saved conclusion and exported PDF show no chosen vendor even if the browser previously held a preference.
- The backend records the trusted reviewer, UTC timestamp, request ID, source case version, analysis/document snapshots, offer facts and original repair/review history. Conclusion, delegated audit and idempotency replay commit in one transaction. No update/delete routes exist. ORM guards and SQLite triggers reject conclusion update/delete.

New feature-local table `procurement_conclusions` is isolated from core bootstrap metadata. It has case/job foreign keys, unique case/analysis, decision/vendor-disposition/reason/version/JSON checks and immutable/source-state triggers. Back up the local database, then explicitly run:

```powershell
$env:PYTHONPATH = 'backend'
.venv/Scripts/python.exe scripts/migrate_procurement_conclusions.py --database-url sqlite:///<absolute-path-to-local-db>
```

No startup `create_all` installs this table. The existing finding-scenario migration checksum is unchanged. This migration is SQLite-specific; a production database migration and approved public schemas remain release work.

The screenshot's global Assure overview (heading, explanatory legend and workflow counters) has been removed. Per-vendor details, scores, collapsible groups, PDF download and final decision remain.

User-requested reason policy revision: repeated/filler words are accepted for experimental GO/NO_GO conclusions. The reason must still contain 20-4000 characters after trimming and at least four whitespace-separated words. Frontend and backend use these same format rules; no distinct-character/repetition threshold is applied. Invalid conclusion requests retain HTTP 400 / VALIDATION_ERROR and the canonical envelope, with safe field-specific instructions rather than a misleading generic "unknown field" message. Existing v1.1 human-review validation is unchanged.

Saved GO/NO_GO status is visible in the active case context and case history. GO includes the selected vendor; NO_GO explicitly shows no vendor selected. Status comes from the backend conclusion or its authorized redacted audit event, never the browser preference or an unsubmitted radio choice. History checks the latest case analysis before showing a current decision; a newer analysis shows decision pending and identifies the previous outcome. Read failures show status unavailable. The conclusion event is included in the Assure step timestamps and latest-activity ordering. An already-open history refreshes after a successful conclusion.

Case history also filters by All cases, Concluded (GO / NO-GO), Not concluded, or Status unavailable. It applies the saved latest-assessment outcome together with search/category/recent filters before pagination and resets the page when the filter changes. Pending cases, including newer assessments awaiting a fresh decision, are not concluded; unavailable/unknown status is kept separate from pending. No backend contract or workflow state is changed by this display filter.
