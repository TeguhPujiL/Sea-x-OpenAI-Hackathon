# Vendor findings across Assess, Challenge, Simulate and Assure

The standard workflow uses current v1.1 resources. The optional finding-based AI scenario prototype adds separately gated experimental routes and feature-local persistence; it is documented in FINDING_SCENARIO_ADDENDUM_PROPOSED.md and is not represented as released v1.1 behavior. Original documents, findings, challenges, simulations and reviews remain preserved.

## Finding-count colors

The user's final rubric takes precedence over the earlier severity-based proposal:

| Indicator | Meaning |
| --- | --- |
| Green | Zero distinct active findings, with completed analysis/document/requirement/evidence coverage. |
| Yellow | One or two distinct active findings. |
| Red | Three or more distinct active findings. The badge shows the actual number, without a cap. |
| Yellow / Unscored | The analysis or required coverage is missing/incomplete and no count-based result establishes a green option. |

Only OPEN and UNDER_REVIEW findings count. RESOLVED and DISMISSED records remain preserved without adding to the active count. HIGH/CRITICAL severity remains visible in the finding detail but does not determine this color. Colors are documentation review indicators, not probabilities or verified vendor compliance/award decisions.

Relevant shared points repeat in each vendor/package context, but each finding ID counts once in the vendor total. Vendor totals combine distinct findings across packages included in the current analysis. Excluded earlier packages remain available for inspection without affecting the current vendor total. Associations and vendor names still rely on filenames/cited text, as documented in VENDOR_ASSESSMENT.md; no authoritative vendor entity is invented.

## Navigation and history

Assess shows documentation, scores, individual concerns and repeated shared points by vendor. Challenge lists all active applicable points under those same vendor/package groups. One real challenge record can be shown in several groups when the underlying point is shared. AI challenges remain DRAFT pending human readiness.

Both challenge and simulation histories are loaded from the authorized paginated case endpoints on refresh/reopen. Changing a selected finding does not delete either history. Unsupported simulation points remain visible and never become completed just because a different point was simulated.

Each vendor group has its own Show/Hide button. Every grouped page also has Show all vendor groups and Hide all vendor groups controls. Collapsing content keeps the vendor name and risk indicator visible; it does not change findings, selection or records. These controls are available in Assess, Challenge, Simulate and Assure.

## Vendor simulation batches

Simulate can submit all supported, verified, actively challenged RAM points for a vendor using a common baseline, alternative and supplier data version. The batch deduplicates finding IDs, including repeated shared points. Every actual POST has its own captured Idempotency-Key. On an interrupted response, the same prepared batch skips earlier successes and retries the uncertain request with the original key/body. Saved partial results remain inspectable after refresh.

The existing deterministic simulation engine supports only RAM-based supplier eligibility. The new opt-in model scenario extension can draft qualitative alternatives for every challenged finding type, with separate deterministic evidence/arithmetic checks where inputs support them. It returns the server's immutable snapshot and calculated metrics for the selected supplier dataset. It does not return vendor-specific procurement prices, warranty compliance, actual savings or a final ranking. A shared simulation is shown under each affected vendor, rather than creating a fictitious vendor-specific result. Use this simulation in Repair selects its real finding/snapshot for the existing governed-draft workflow.

Challenge creation does not have a mandatory idempotency contract. An interrupted challenge response therefore prompts inspection of refreshed history instead of presenting it as a guaranteed safe transport replay. No exactly-once provider-billing claim is made.

## Repair and Assure

Repair also supports revised PDF uploads and explicit re-analysis of a selected current evidence set. See REPAIR_REANALYSIS.md. New uploads do not clear the current draft or replace originals; saving revision document types preserves the Repair context. Starting the accepted new analysis moves to Assess, clears browser references to the prior selected downstream chain, and preserves server history. A prior review of a different repair does not block a new submitted repair's review; the same reviewed repair remains protected.

Assure compares current vendor colors/counts, document coverage and actual workflow counts. Users can choose a vendor preference and download the comparison PDF. The preference is stored only in session storage scoped to case ID and analysis job ID. A new analysis invalidates the previous selection. This is a human-review preference, not a server-side award, approval, finding resolution or assurance status update. G01 still blocks final completion of a clean case under v1.1.

## Earlier iteration verification, 7 November 2026 (Asia/Jakarta)

- 113 frontend tests passed after the final count-based rubric, including shared-point deduplication, vendor grouping, partial simulation retries, stale/foreign resources, revision evidence selection, preference validity and immutable-review isolation.
- Frontend typecheck and production build passed; the local app serves the updated bundle at `http://127.0.0.1:8002`.
- Live QA used the isolated mixed test case `34966abe-c832-4054-a6ec-5eece7243c38`: a shared RAM point produced the contract fixture's deterministic result; the same ID was not duplicated within the batch; refresh recovered its simulation history.
- All 14 supplied Positive PDFs were uploaded as a corrected evidence set, typed through the normal document PATCH routes, and explicitly selected for a new analysis. The original 28 documents were retained.
- Re-analysis job `c28c550c-5e0b-41dc-be8b-8cea0f9708a1` completed with 18 requirements and no findings/warnings. Current vendor scores were green/0 for A, B and C. Earlier findings and reviews remained byte-for-byte equal in their returned representations. Preference selection did not approve the case.
- All 20 live API/helper assertions passed. The trace is `.tools/qa-results/vendor-cycle-live.json`; unit output is `.tools/qa-results/vendor-cycle-tests.log`. These checks do not claim production certification or rollback-atomicity proof.

## Latest implementation status

The user subsequently requested scoring thresholds green=0, yellow=1-2 and red=3+, vendor-grouped Repair with the current document inventory collapsed at the bottom, model-generated scenarios for every finding, and PDF comparison export. These source revisions are implemented without running tests, typechecks, builds, migrations, live provider calls or browser checks after the explicit instruction to stop testing. Earlier results above do not verify these latest revisions. The running process and previously built bundle have not been updated for this final iteration.
