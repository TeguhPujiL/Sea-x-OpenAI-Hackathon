import React from "react";
import type { Resources } from "./workflow";
import { vendorEvidence } from "./vendorEvidenceSummary";

const fields = [
  ["supplier_name", "Supplier"], ["model", "Model"], ["quantity", "Quantity"], ["unit_price_idr", "Unit price (IDR)"],
  ["total_price_idr", "Total quoted price (IDR)"], ["tax_basis", "Tax basis"], ["memory", "Memory"], ["processor", "Processor"],
  ["line_total_idr", "Quoted line item total (IDR)"],
  ["storage", "Storage"], ["display", "Display"], ["security", "Security"], ["operating_system", "Operating system"],
  ["warranty", "Quoted warranty"], ["warranty_term", "Warranty letter term"], ["delivery", "Delivery"], ["offer_validity", "Offer validity"],
] as const;
export function VendorOfferSummary({ resources, vendorId }: { resources: Resources; vendorId: string }) {
  const summary = vendorEvidence(resources, vendorId);
  return <section className="vendor-offer-summary"><h5>Offer and specification summary</h5>
    {summary.available && resources.vendorEvidenceSummaryError && <p className="inline-warning">The latest source refresh failed: {resources.vendorEvidenceSummaryError}. Previously loaded source details are shown.</p>}
    {!summary.available ? <p role="status">{resources.vendorEvidenceSummaryError ?? "Source details are loading or unavailable. Prices and specifications are not inferred from filenames."}</p> : <>
      {summary.packages.map(pack => <section className="vendor-package" key={pack.source}><h5>{pack.source === "uploaded" ? "Selected offer documents" : `${pack.source} package`}</h5>
        <dl className="vendor-offer-facts">{fields.map(([field,label]) => {
          const facts = pack.facts.filter(fact => fact.field === field);
          const values = [...new Set(facts.map(fact => fact.value))];
          return <React.Fragment key={field}><dt>{label}</dt><dd>{!facts.length ? <span className="muted">Not extracted from selected evidence</span> : <>
            {values.map(value => <p key={value}>{value}</p>)}{values.length > 1 && <p className="inline-warning">Multiple recorded values - review the source documents.</p>}
            <details><summary>View sources</summary>{facts.map((fact,index) => <div className="evidence-card" key={index}>
              <strong>{resources.documents.find(doc => doc.document_id === fact.source.document_id)?.filename ?? "Source document"} · Page {fact.source.page_number}</strong><blockquote>{fact.source.excerpt}</blockquote>
            </div>)}</details>
          </>}</dd></React.Fragment>;
        })}</dl>
        {!!pack.newly_included_document_ids.length && <p>{pack.newly_included_document_ids.length} vendor document(s) included since the original finding baseline. This records evidence changes, not automatic repair completion.</p>}
      </section>)}
      <h5>Result from the original findings</h5>
      <p>{summary.current_assessment}</p>
      {summary.initial_analysis_job_id && <p className="muted">Original finding baseline: <code>{summary.initial_analysis_job_id}</code>{summary.reassessed ? " · A later assessment is being shown." : " · This is the original assessment."}</p>}
      {!summary.original_findings.length ? <p>No original finding is linked to this vendor in the loaded baseline.</p> : summary.original_findings.map(finding => <article className="vendor-repair-outcome" key={finding.finding_id}>
        <h6>{finding.title}</h6><p><strong>{finding.outcome}</strong></p><p className="muted">Finding status: {finding.status.replaceAll("_", " ").toLowerCase()}</p>
        {finding.repairs.map(repair => <details key={repair.repair_proposal_id}><summary>Repair proposal · {repair.status} · {repair.created_at}</summary>
          <p><strong>Original:</strong> {repair.before_text}</p><p><strong>Proposed repair:</strong> {repair.proposed_text}</p><p>{repair.justification}</p><code>{repair.repair_proposal_id}</code>
        </details>)}
        {finding.reviews.map(review => <p key={review.review_id}><strong>Review: {review.decision.replaceAll("_", " ")}</strong> · {review.decision_reason}</p>)}
      </article>)}
      <p className="muted">A repair draft, revised document, and finding resolution are separate records. A clean reassessment does not silently resolve the original findings.</p>
    </>}
  </section>;
}
