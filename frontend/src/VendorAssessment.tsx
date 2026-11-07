import React from "react";
import type { FindingResource } from "./contracts";
import type { Resources } from "./workflow";
import { vendorAssessment } from "./vendorAssessmentData";

const human = (value: string) => value.replaceAll("_", " ").toLowerCase();
export function VendorAssessment({ resources, disabled, onChallenge }: {
  resources: Resources; disabled: boolean; onChallenge?: (id: string) => void;
}) {
  const result = vendorAssessment(resources);
  function concern(finding: FindingResource) {
    const available = result.canChallenge(finding);
    return <article className="vendor-concern" key={finding.finding_id}>
      <h5>{finding.title}</h5><p>{finding.summary}</p>
      <p className="muted">{human(finding.severity)} severity · {human(finding.status)} · {human(finding.evidence_status)} evidence</p>
      <details><summary>Cited evidence</summary>{finding.evidence.map((ref, i) => <div key={i} className="evidence-card">
        <strong>{result.summary.documents.find(d => d.document_id === ref.document_id)?.filename ?? "Document unavailable"} · Page {ref.page_number}</strong><blockquote>{ref.excerpt}</blockquote>
      </div>)}</details>
      <button className="secondary" disabled={disabled || !onChallenge || !available} onClick={() => onChallenge?.(finding.finding_id)}
        aria-label={`Challenge finding: ${finding.title}`}>Challenge finding</button>
      {!available && <p className="muted">A formal challenge requires an active finding with verified, available evidence and an open case.</p>}
    </article>;
  }
  return <section className="vendor-assessment" aria-labelledby="vendor-assessment-title">
    <div className="section-title"><h3 id="vendor-assessment-title">Assessment by vendor</h3><span className="count">{result.vendors.length}</span></div>
    <p>Compare the participating vendors, review their documentation, and challenge recorded concerns.</p>
    {!!result.candidateCount && <p className="notice info-notice">{result.candidateCount} {result.candidateCount === 1 ? "option has" : "options have"} an analyzed quotation and warranty with no linked open finding. These options remain available for detailed evaluation while other concerns are reviewed.</p>}
    <p className="muted">Groups use vendor names in uploaded filenames. Separate package labels preserve document context. Document presence and the absence of a finding do not establish full compliance.</p>
    {result.vendors.map(vendor => <article key={vendor.id} className="vendor-assessment-card" aria-labelledby={`vendor-${vendor.id}`}>
      <h4 id={`vendor-${vendor.id}`}>{vendor.label}</h4>
      {vendor.packages.map(pack => <section key={pack.source} className={`vendor-package ${pack.candidate ? "vendor-candidate" : ""}`} aria-label={`${vendor.label}: ${pack.source} package`}>
        <div className="split"><h5>{pack.source === "uploaded" ? "Uploaded documents" : `${pack.source[0].toUpperCase()}${pack.source.slice(1)} package`}</h5><span className="proposal-outcome">{pack.status}</span></div>
        <ul className="vendor-document-checks"><li>Quotation: {pack.quotationPresent ? "present" : "not linked"}</li><li>Warranty: {pack.warrantyPresent ? "present" : "not linked"}</li><li>Analysis coverage: {pack.analyzedDocuments} / {pack.documents.length} documents</li></ul>
        <details><summary>Review documents ({pack.documents.length})</summary><ul className="vendor-document-list">{pack.documents.map(doc => <li key={doc.document_id}>
          <strong>{doc.filename}</strong><p>{human(doc.document_type)} · {doc.page_count} pages · {human(doc.processing_status)}</p>
          <code>{doc.document_id}</code>{doc.description && <p>{doc.description}</p>}
        </li>)}</ul><p className="muted">Review the original PDFs alongside the cited passages. This view lists saved metadata and evidence references.</p></details>
        {pack.findings.length ? <><h5>Concerns referencing this option</h5><p className="muted">A reference is a request for clarification, not an automatic vendor rejection.</p>{pack.findings.map(concern)}</> : <p>No recorded finding is linked to this option.{!pack.candidate && " Confirm analysis and document coverage before drawing a conclusion."}</p>}
      </section>)}
    </article>)}
    {!result.vendors.length && <p>No vendor-labelled supplier quotations are available. Classify quotations in Upload and confirm the vendor names in the filenames.</p>}
    {!!result.unassigned.length && <details><summary>Quotations without a vendor label ({result.unassigned.length})</summary><ul>{result.unassigned.map(doc => <li key={doc.document_id}>{doc.filename}</li>)}</ul><p>Confirm vendor ownership before grouping these documents.</p></details>}
    {!!result.sharedFindings.length && <section className="vendor-shared-concerns"><h4>Shared evaluation concerns</h4>
      <p>These concerns affect the requirements or evaluation context. They remain separate from individual vendor documentation and must be addressed before a final decision.</p>
      {result.sharedFindings.map(concern)}
    </section>}
  </section>;
}
