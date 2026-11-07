# Assure vendor comparison and preference

`VendorDecisionSummary` presents the current vendor documentation scores and lets the user choose a preferred vendor for human review. It is a frontend preference, not an award or approval operation. It does not call a new API route, create a review, resolve a finding, or change assurance status.

The component uses `vendorAssessment` so Assess and Assure share the same scoring rules and document associations. Green means zero applicable active findings with completed documentation coverage; yellow means one applicable active finding; red means two or more applicable active findings. The score is the actual count, with no severity weighting or two-point cap. Incomplete or unknown coverage with zero findings stays unscored/yellow. RESOLVED/DISMISSED findings do not count.

The summary shows each vendor's risk color/count, package scores, analyzed quotations, relevant/shared open points, and actual loaded workflow counts. The vendor total is the union of unique applicable active findings across packages included in the current analysis. A shared concern repeated across those packages counts once for that vendor, and packages excluded from the current analysis do not inflate its score. Challenge and simulation histories are deduplicated by immutable resource ID and restricted to the current case and current-analysis finding IDs.

A vendor can be selected only when a usable current COMPLETED/NEEDS_REVIEW analysis includes a successfully extracted supplier quotation for that vendor. There is no automatic lowest-score winner. Missing, stale, foreign, deleted or outside-analysis vendor choices do not become a current preference. A warning-bearing or unresolved analysis permits a provisional preference while explicitly preserving its concerns.

The parent application owns preference storage and must scope it to case and analysis job. The controlled component receives `selectedVendorId` and `onSelectVendor`; it will label an unavailable prior preference as stale. Changing an analysis must not silently reuse an old award-like decision.

The comparison report can be downloaded as PDF. It includes actual case/job IDs, vendor scores and document references, selected preference, workflow resource IDs and current finding citations. It contains no credentials or session headers. It labels its role as comparison for human review and preserves the G01 clean-case completion gap.

The progress summary counts saved resources. It does not claim that every workflow step is complete, treat a RAM simulation as a warranty/arithmetic/delivery simulation, or infer success for unimplemented methods. Full vendor compliance and statutory selection require reviewing the original documents and applicable requirements.

Verification: `frontend/tests/vendor-decision.test.mjs` covers no automatic winner, provisional red selection, exact selected ID callback, stale/failed/outside-analysis choices, deduplicated current workflow records, clean preferences/G01, and deleted/foreign documents.

The latest revisions, including PDF export, grouped Repair and experimental model scenarios, are implementation-only and remain untested at the user's request. Earlier verification statements describe only the earlier iteration.
