# Additional simulation methods for owner review

Status: Specialized deterministic methods remain PROPOSED. A separate local opt-in generic AI what-if prototype is implemented in source; see FINDING_SCENARIO_ADDENDUM_PROPOSED.md. It is untested and does not extend the released v1.1 RAM endpoint. The user requested documentation of additional methods after the prototype's RAM-only limitation was identified. API Contract v1.1 remains the source of truth. Aris owns simulation logic/router/fixtures; Teguh owns shared contract/models and integration. This document is a review handoff, not permission to add unapproved public fields or silently change supplier-data versions.

## Existing capability

The current simulation command takes finding_id, baseline.minimum_ram_gb, alternative.minimum_ram_gb and supplier_data_version. It calculates supplier eligibility and offer totals from a server-side versioned catalog. Vendor grouping in the UI does not change those semantics. Warranty, arithmetic, delivery and complete compliance points are explicitly marked as requiring another method.

## Proposed methods

| Method | Required authoritative inputs | Proposed deterministic checks/output | Limits |
| --- | --- | --- | --- |
| Warranty coverage comparison | An approved requirement baseline; vendor quotation and warranty letter; source IDs/pages/excerpts; validated extracted duration, coverage, service terms and applicable equipment/quantity. | Compare each required term with offered/evidenced terms; return supported, conflicting or unknown comparisons with citations. | A present letter is not automatically adequate. Ambiguous scope/authority stays unknown and requires human verification. |
| Estimate reconciliation | Source-backed line quantities/unit prices, fees, discount terms, tax rule and rounding policy from the approved synthetic scenario. | Recompute line extensions, subtotal, configured tax and total using integer money and an explicit rounding rule; expose discrepancies with the displayed source amounts. | Use the scenario's supplied arithmetic policy, not an assumed tax rate or a claim about applicable law. A mismatch is not proof of financial loss or intent. |
| Delivery/configuration deviation | Approved requirement, evaluated offer and proposed revised order; source-backed delivery basis, dates/durations and installed/configurable specification values. | Compare baseline/alternative contractual terms; list changed terms and unresolved authorization references without deciding whether a deviation is legally permitted. | Calendar/business-day conventions, start events, authorized substitutions and missing records must be explicit. Unknown dates cannot be invented. |
| Full requirement/vendor matrix | Explicit authoritative vendor/proposal identities and document ownership; versioned requirement set; source-grounded technical, licensing, warranty, security, delivery and commercial facts. | Evaluate each criterion independently and show satisfied, contradicted or unknown outcomes; summarize coverage without auto-award. | Needs a shared-model/contract addendum. RAM eligibility alone is not full compliance; absence of a contradiction is not evidence that a requirement is satisfied. |

## Contract and persistence work required before implementation

1. Agree the versioned method-selection/request/response contract with the owners. Existing RAM requests and response snapshots must remain backward compatible. No new method enum is implied to exist in v1.1.
2. Define authoritative vendor/proposal and source-revision associations, with case-level authorization and soft-deletion checks. Uploaded filename hints and client-authored assertions are insufficient authority.
3. Define typed, validated inputs, exact evidence references, unknown/unverified behavior, integer arithmetic/rounding, method/data versions and immutable input/result snapshots. Never replace validated source facts with model-generated calculations.
4. Reuse scoped idempotency and atomic business/audit writes; audit the trusted actor, request, source versions, engine/version and material changes. Changed scenario inputs must create a new simulation rather than update/delete the old result.
5. Publish synthetic versioned fixtures and golden expectations for each method. Keep the PDF pack's offers distinct from synthetic-suppliers-v1. Test missing, conflicting, unauthorized, outdated and revised inputs, partial batches, retries, rollback and refresh/restart persistence.
6. Establish human-review acceptance criteria and labels. Simulation output must not silently resolve a finding, approve procurement or select a supplier. Preserve the existing review enums and clean-case gap until an approved addendum changes them.

Until those decisions are reviewed and implemented, the UI keeps all unsupported points visible for evidence review and revised-document re-analysis. It does not manufacture numerical results for them.
