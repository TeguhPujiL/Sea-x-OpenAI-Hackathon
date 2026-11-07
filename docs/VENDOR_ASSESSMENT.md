# Assess results by vendor

The local prototype now presents Assess results grouped by participating vendor, while retaining the current API v1.1 workflow and source records. This change was requested after testing the combined Positive/Negative corpus.

## Behavior

- Vendor cards group supplier quotations and warranty documents using vendor labels in uploaded filenames, such as `05A_Vendor_A_Quotation.pdf` and `06A_Vendor_A_Warranty_Letter.pdf`.
- `Positive__` and `Negative__` prefixes remain separate packages inside each vendor card. Package names never determine whether an option is a candidate. Other filenames are shown as the uploaded document set; quotations without a recognizable vendor label remain explicitly unassigned.
- Each package shows quotation/warranty presence, the number of documents included in the recorded analysis, and an expandable document inventory.
- A candidate for detailed evaluation requires a completed usable analysis with successful evidence checks, included requirement documents and an extracted requirement count, analyzed quotation/warranty documents, and no linked open finding. Missing findings, processing warnings, invalid citation metadata and incomplete coverage prevent this presentation.
- A concern referencing a vendor is shown with its source pages, evidence status, summary and a Challenge finding action. Being cited does not automatically mean that a vendor is invalid: a warranty may itself be the evidence contradicting an evaluator's missing-document assertion.
- Findings without a supported vendor association stay in a separate Shared evaluation concerns section. They do not automatically label every vendor's own documents defective, and remain relevant before a final procurement decision.
- Associations from a cited passage naming a vendor use only that passage's document package. A Negative evaluation mentioning Vendor C cannot silently attach its concern to Vendor C's Positive package.
- Challenge finding selects the existing real finding and navigates to phase 03. Changing findings preserves the existing confirmation for unsaved repair text and clears only browser references to downstream resources. It does not delete history or automatically send a generation request.
- Formal challenge actions require a current active finding, verified available citations and an open case. Options without findings support document review and never receive fabricated findings or formal challenges. This follows the user's explicit clarification.
- All recorded findings remain available in an expandable list. The original clean-case completion gap and assurance workflow remain intact.

## Limits and proposed follow-up with the shared-model owner

The contract currently exposes document metadata and finding evidence, without a vendor entity, vendor-to-document ownership field, complete requirement-by-vendor assessment, verified compliance verdict or public PDF-content route. Consequently:

- Filename-based grouping is a presentation aid; it does not establish vendor ownership.
- Quotation/warranty presence is document coverage, not proof that all mandatory requirements or commercial conditions are correct. A price or delivery term can still require evaluation even when no contradiction finding cites the quotation.
- Candidate for detailed evaluation is not an eligibility, award or approval decision.
- Document review here exposes saved metadata and cited passages. Original PDFs must also be reviewed; this UI does not invent download URLs or expose private storage paths.

PROPOSED for Teguh/shared-model review: explicit vendor identity, authoritative proposal/document associations and source-grounded per-requirement technical/warranty/commercial assessment, with provenance and revision handling. Such a contract addendum would permit verified vendor compliance results independently of contradiction findings. No new public fields, enums, endpoints, database schema or AI outputs are introduced by this frontend change. Formal challenges for options without a finding would require a separate approved contract change and are outside the accepted scope.

## Verification executed

- 88 frontend tests passed, including mixed vendor/package separation, source-scoped associations, missing/out-of-analysis documents, evidence warnings/failure, unknown identities, deleted/foreign resources, challenge preconditions and exact finding-ID navigation.
- Typecheck and Vite production build passed. The updated static bundle is served by the existing local app at `http://127.0.0.1:8002`.
- Read-only live validation used the three persisted scenarios from bot run `20261107T064251Z-05f54f45`; no additional paid generation was needed.

| Scenario | Vendor groups | Candidate options | Shared findings | Challengeable findings |
| --- | --- | --- | --- | --- |
| Positive control | 3 | 3 | 0 | 0 |
| Negative control | 3 | 1 | 2 | 5 |
| Mixed | 3 | 4 | 2 | 4 |

Candidate counts refer to distinct vendor/package options rather than unique vendors. These measurements describe the saved analysis results, not full compliance certification. The live validation report is `.tools/qa-results/vendor-assessment-live.json`; automated test output is `.tools/qa-results/vendor-assessment-tests.log`.

To inspect the mixed example, open case `34966abe-c832-4054-a6ec-5eece7243c38` in Case history and select 02 Assess. Expand each vendor's document packages and challenge a recorded concern when clarification is needed.
