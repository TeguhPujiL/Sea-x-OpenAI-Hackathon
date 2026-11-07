import React, { useState } from "react";
import type { Resources } from "./workflow";
import { activeConcern, vendorAssessment } from "./vendorAssessmentData";
import { DocumentationRisk } from "./DocumentationRisk";
import { VendorGroup, VendorGroups } from "./VendorGroup";

export function comparisonData(resources: Resources, selectedVendorId: string | null) {
  const assessment = vendorAssessment(resources);
  const { caseResource, job, documents, findings } = assessment.summary;
  const inputIds = new Set(job?.ai_execution?.input_document_ids ?? []);
  const usableAnalysis = !!job?.result && ["COMPLETED", "NEEDS_REVIEW"].includes(job.status)
    && !!job.ai_execution?.schema_valid && !assessment.summary.missingFindings;
  const findingIds = new Set(findings.map(f => f.finding_id));
  const unique = <T,>(items: T[], id: (item: T) => string): T[] => [...new Map(items.map(item => [id(item), item])).values()];
  const challenges = unique([...(resources.challengeHistory ?? []), ...(resources.challenge ? [resources.challenge] : [])]
    .filter(item => item.case_id === caseResource?.case_id && findingIds.has(item.finding_id)), item => item.challenge_id);
  const simulations = unique([...(resources.simulationHistory ?? []), ...(resources.simulation ? [resources.simulation] : [])]
    .filter(item => item.case_id === caseResource?.case_id && findingIds.has(item.finding_id)), item => item.simulation_id);
  const findingScenarios = unique((resources.findingScenarioHistory ?? []).filter(item => item.case_id === caseResource?.case_id
    && item.analysis_job_id === job?.job_id && findingIds.has(item.finding_id)), item => item.scenario_id);
  const repair = resources.repair && resources.repair.case_id === caseResource?.case_id && findingIds.has(resources.repair.finding_id) ? resources.repair : null;
  const reviews = unique(resources.reviews.filter(item => item.case_id === caseResource?.case_id), item => item.review_id);
  const vendors = assessment.vendors.map(vendor => {
    const analyzedQuotations = vendor.packages.flatMap(pack => pack.documents)
      .filter(doc => doc.document_type === "SUPPLIER_QUOTATION" && doc.processing_status === "COMPLETED" && inputIds.has(doc.document_id));
    const points = unique(vendor.packages.flatMap(pack => pack.challengePoints), item => item.finding_id);
    return { id: vendor.id, label: vendor.label, risk: vendor.risk, selectable: usableAnalysis && analyzedQuotations.length > 0,
      analyzed_quotation_ids: analyzedQuotations.map(doc => doc.document_id),
      open_point_ids: points.map(point => point.finding_id),
      packages: vendor.packages.map(pack => ({ source: pack.source, status: pack.status, risk: pack.risk,
        documents: pack.documents.map(doc => ({ document_id: doc.document_id, filename: doc.filename, sha256: doc.sha256,
          document_type: doc.document_type, included_in_analysis: inputIds.has(doc.document_id), processing_status: doc.processing_status })),
        finding_ids: pack.findings.map(f => f.finding_id), shared_finding_ids: pack.sharedFindings.map(f => f.finding_id) })) };
  });
  const selectedVendor = vendors.find(vendor => vendor.id === selectedVendorId && vendor.selectable) ?? null;
  const openFindings = findings.filter(activeConcern);
  const unresolved = openFindings.length > 0 || !!job?.warnings.length || job?.status === "NEEDS_REVIEW";
  return { report_type: "VENDOR_COMPARISON_FOR_HUMAN_REVIEW", case_id: caseResource?.case_id ?? null,
    analysis_job_id: job?.job_id ?? null, analysis_status: job?.status ?? null,
    case_status: caseResource?.case_status ?? null, assurance_status: caseResource?.assurance_status ?? null,
    selected_vendor_id: selectedVendor?.id ?? null, selected_vendor_label: selectedVendor?.label ?? null,
    stale_selection: !!selectedVendorId && !selectedVendor,
    preference_status: !selectedVendor ? "NO_CURRENT_PREFERENCE" : unresolved ? "PROVISIONAL_PREFERENCE_UNRESOLVED_POINTS" : "PREFERENCE_FOR_HUMAN_REVIEW",
    usable_analysis: usableAnalysis, vendors,
    progress: { uploaded_documents: documents.length, analyzed_documents: documents.filter(doc => inputIds.has(doc.document_id)).length,
      extracted_requirements: assessment.summary.requirementCount, current_findings: findings.length, unresolved_findings: openFindings.length,
      recorded_challenges: challenges.length, recorded_simulations: simulations.length,
      recorded_finding_scenarios: findingScenarios.length,
      repair_status: repair?.status ?? null, loaded_reviews: reviews.length },
    records: { challenge_ids: challenges.map(item => item.challenge_id), simulation_ids: simulations.map(item => item.simulation_id),
      finding_scenario_ids: findingScenarios.map(item => item.scenario_id),
      repair_proposal_id: repair?.repair_proposal_id ?? null, review_ids: reviews.map(item => item.review_id) },
    findings: findings.map(finding => ({ finding_id: finding.finding_id, title: finding.title, status: finding.status,
      severity: finding.severity, evidence_status: finding.evidence_status, evidence: finding.evidence })),
    finding_scenarios: findingScenarios,
    limits: ["Vendor labels are inferred from filenames; confirm document ownership.",
      "Documentation risk scores are review indicators, not vendor eligibility or award decisions.",
      "A preferred vendor does not resolve findings or approve a procurement.",
      "G01: clean-case final completion requires a contract addendum; no APPROVE_CASE command is issued.",
      "Only loaded current-analysis challenge/simulation records are counted; unsupported simulation methods are not inferred complete."] };
}

export function VendorDecisionSummary({ resources, selectedVendorId, onSelectVendor, disabled }: {
  resources: Resources; selectedVendorId: string | null; onSelectVendor: (id: string) => void; disabled: boolean;
}) {
  const comparison = comparisonData(resources, selectedVendorId);
  return <section className="vendor-decision-summary" aria-labelledby="vendor-decision-title">
    <div className="section-title"><h3 id="vendor-decision-title">Vendor score summary and preference</h3></div>
    <p>Compare the current documentation risk for each vendor, then record your preference for human review. No vendor is selected automatically.</p>
    <p className="muted">Green = no applicable active findings with completed documentation coverage; yellow = 1-2 active findings; red = 3 or more active findings. The score shows the actual finding count. Incomplete coverage with no findings remains unscored. Scores do not establish full compliance.</p>
    <dl className="metadata"><dt>Uploaded / analyzed documents</dt><dd>{comparison.progress.uploaded_documents} / {comparison.progress.analyzed_documents}</dd>
      <dt>Current analysis</dt><dd>{comparison.analysis_status ?? "Not run"}</dd><dt>Extracted requirements</dt><dd>{comparison.progress.extracted_requirements ?? "Not reported"}</dd>
      <dt>Unresolved current findings</dt><dd>{comparison.progress.unresolved_findings}</dd><dt>Recorded current challenges</dt><dd>{comparison.progress.recorded_challenges}</dd>
      <dt>Recorded current simulations</dt><dd>{comparison.progress.recorded_simulations}</dd><dt>Current repair</dt><dd>{comparison.progress.repair_status ?? "Not loaded"}</dd>
      <dt>Finding-based scenario drafts</dt><dd>{comparison.progress.recorded_finding_scenarios}</dd>
      <dt>Loaded case reviews</dt><dd>{comparison.progress.loaded_reviews}</dd></dl>
    <p className="muted">These are saved record counts, not a declaration that every workflow step or simulation method is complete.</p>
    {comparison.stale_selection && <p className="notice warning-notice" role="status">The previous preference is unavailable in this analysis. Select an analyzed vendor again.</p>}
    <fieldset disabled={disabled}><legend>Preferred vendor for human review</legend>
      <VendorGroups label="Assure vendor groups">{comparison.vendors.length ? comparison.vendors.map(vendor => <VendorGroup key={vendor.id} title={vendor.label} summary={<DocumentationRisk risk={vendor.risk} />}>
        <p>{vendor.analyzed_quotation_ids.length} analyzed quotation(s) · {vendor.open_point_ids.length} open related/shared point(s)</p>
        <ul className="risk-reasons">{vendor.risk.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
        <details><summary>Document packages and scores</summary>{vendor.packages.map(pack => <section className="vendor-package" key={pack.source}>
          <h5>{pack.source === "uploaded" ? "Uploaded documents" : `${pack.source} package`}</h5><DocumentationRisk risk={pack.risk} />
          <p>{pack.status}</p><ul>{pack.documents.map(doc => <li key={doc.document_id}>{doc.filename} · {doc.included_in_analysis ? "included in current analysis" : "outside current analysis"}</li>)}</ul>
        </section>)}</details>
        <label className="checkbox"><input type="radio" name="preferred_vendor" value={vendor.id} checked={comparison.selected_vendor_id === vendor.id}
          disabled={!vendor.selectable} onChange={() => onSelectVendor(vendor.id)} />Select {vendor.label}</label>
        {!vendor.selectable && <p className="muted">A usable current analysis including this vendor's readable quotation is required before selection.</p>}
      </VendorGroup>) : <p>No vendor-labelled supplier quotation is available for comparison.</p>}</VendorGroups>
    </fieldset>
    {comparison.selected_vendor_label ? <div className="notice info-notice" role="status"><strong>Preferred vendor: {comparison.selected_vendor_label}</strong>
      <p>{comparison.preference_status === "PROVISIONAL_PREFERENCE_UNRESOLVED_POINTS" ? "This preference is provisional. Unresolved findings or processing warnings still require review." : "This preference is available for the authorized human review."}</p>
      <p>Selection does not approve a procurement, close findings, or change server assurance status.</p></div> : <p role="status">No current vendor preference selected.</p>}
    <VendorComparisonDownload comparison={comparison} disabled={disabled} />
  </section>;
}

function VendorComparisonDownload({ comparison, disabled }: { comparison: ReturnType<typeof comparisonData>; disabled: boolean }) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  async function download() {
    setExporting(true); setExportError(null);
    try {
      const [pdf, fontResponse] = await Promise.all([import("./vendorComparisonPdf"), fetch("/fonts/NotoSans-Regular.ttf", { credentials: "same-origin" })]);
      if (!fontResponse.ok) throw new Error("The report font could not be loaded. Refresh the application and try again.");
      const bytes = new Uint8Array(await fontResponse.arrayBuffer());
      let font = "";
      for (let index = 0; index < bytes.length; index += 8192) font += String.fromCharCode(...bytes.subarray(index, index + 8192));
      const report = pdf.createVendorComparisonPdf(comparison, btoa(font));
      report.save(`vendor-comparison-${comparison.case_id ?? "workspace"}.pdf`);
    } catch (error) { setExportError(error instanceof Error ? error.message : "The PDF report could not be generated."); }
    finally { setExporting(false); }
  }
  return <>
    {exportError && <p className="notice error-notice" role="alert">{exportError}</p>}
    <button className="secondary" disabled={disabled || exporting || !comparison.case_id} onClick={() => void download()}>{exporting ? "Preparing PDF report…" : "Download vendor comparison report (PDF)"}</button>
  </>;
}
