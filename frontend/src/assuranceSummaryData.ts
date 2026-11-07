import type { DocumentResource, FindingResource } from "./contracts";
import type { Resources } from "./workflow";

// Read-only projection of recorded resources. No new compliance verdict is inferred.
export function assuranceSummary(resources: Resources) {
  const caseResource = resources.caseResource?.deleted_at ? null : resources.caseResource;
  const caseId = caseResource?.case_id;
  const job = caseId && resources.job?.case_id === caseId ? resources.job : null;
  const documents = resources.documents.filter(d => !!caseId && d.case_id === caseId && !d.deleted_at);
  const result = job?.result;
  const findings = resources.findings.filter(f => !!job && f.case_id === caseId && f.analysis_job_id === job.job_id && result?.finding_ids.includes(f.finding_id));
  const missingFindings = !!result?.finding_ids.some(id => !findings.some(f => f.finding_id === id));
  const execution = job?.ai_execution;
  const checked = !!execution && execution.schema_valid && execution.evidence_validation_passed && execution.evidence_checks.failed === 0;
  const reliable = !!result && job?.status === "COMPLETED" && checked && !job.warnings.length && !missingFindings;
  const requirementCount = result && Number.isSafeInteger(result.requirement_count) && result.requirement_count! >= 0 ? result.requirement_count! : null;
  let headline = "Analysis not available";
  let narrative = "Run an analysis to summarize the recorded requirements and findings.";
  if (!caseId) {
    narrative = "Create or reopen a case to see its assurance summary.";
  } else if (job?.status === "QUEUED" || job?.status === "PROCESSING") {
    headline = "Analysis in progress";
    narrative = "Wait for the analysis to finish before drawing a conclusion about the proposal.";
  } else if (job?.status === "FAILED") {
    headline = "Analysis failed";
    narrative = "No usable assessment conclusion is available from this analysis. Check the execution error in Assess.";
  } else if (job?.status === "NEEDS_REVIEW" || job?.status === "COMPLETED" && !reliable) {
    headline = "Evidence review required";
    narrative = "The recorded analysis needs further evidence checks before its results can support a conclusion.";
  } else if (reliable && result) {
    headline = result.finding_ids.length ? "Integrity findings recorded" : "No integrity findings returned";
    narrative = result.finding_ids.length
      ? "The analysis returned integrity findings. Review the findings and the recommendations for each proposal below."
      : "The completed analysis returned no integrity findings for the documents it analyzed.";
  }
  const relatedFindings = (document: DocumentResource): FindingResource[] => findings.filter(f => f.evidence.some(e => e.document_id === document.document_id));
  const quotationIds = new Set(documents.filter(d => d.document_type === "SUPPLIER_QUOTATION").map(d => d.document_id));
  const open = (finding: FindingResource) => !["RESOLVED", "DISMISSED"].includes(finding.status);
  const sharedFindings = findings.filter(f => !f.evidence.some(e => quotationIds.has(e.document_id)));
  const comparisonInputs = ["TOR", "TECHNICAL_SPECIFICATION"].every(type => documents.some(d => d.document_type === type && execution?.input_document_ids.includes(d.document_id)));
  const proposals = documents.filter(d => d.document_type === "SUPPLIER_QUOTATION").map(document => {
    const included = !!execution?.input_document_ids.includes(document.document_id);
    const related = included ? relatedFindings(document) : [];
    const shared = included ? sharedFindings : [];
    const coverage = !execution ? job ? "Analysis coverage not yet reported" : "Not analyzed" : !included ? "Not included in this analysis"
      : job?.status === "QUEUED" || job?.status === "PROCESSING" ? "Analysis in progress"
      : job?.status === "FAILED" ? "Analysis failed"
      : !reliable ? "Evidence review required"
      : related.length ? "Included; see recorded findings" : "Included; no finding cites this proposal";
    let status = "Not assessed";
    let tone: "ready" | "attention" | "pending" = "pending";
    let resultSummary = "This proposal has not been included in a completed analysis.";
    let recommendation = "Analyze this proposal";
    let nextSteps = ["Include this supplier quotation, the TOR and the technical specification in a new analysis."];
    if (document.processing_status === "FAILED") {
      status = "Document extraction failed";
      resultSummary = "The proposal could not be read successfully.";
      recommendation = "Provide a readable proposal";
      nextSteps = ["Upload a readable PDF, save its document type as Supplier quotation, and run a new analysis."];
    } else if (document.processing_status !== "COMPLETED") {
      status = "Document processing incomplete";
      resultSummary = "The proposal document is not ready for assessment.";
      recommendation = "Complete document processing";
      nextSteps = ["Check the document processing status in Upload before starting a new analysis."];
    } else if ((included || !execution) && (job?.status === "QUEUED" || job?.status === "PROCESSING")) {
      status = "Analysis in progress";
      resultSummary = included ? "This proposal is included in the running analysis. A result is not available yet." : "The case analysis is running. Coverage for this proposal is not yet reported.";
      recommendation = "Wait for the analysis result";
      nextSteps = ["Return to Assess to monitor the current analysis, then refresh these recommendations."];
    } else if ((included || !execution) && job?.status === "FAILED") {
      status = "Analysis failed";
      resultSummary = "The case analysis failed. An assessment of this proposal cannot be confirmed.";
      recommendation = "Resolve the analysis error";
      nextSteps = ["Check the execution error in Assess and address its cause before running a new analysis."];
    } else if (job && !execution) {
      status = "Analysis coverage unavailable";
      tone = "attention";
      resultSummary = "The execution record does not confirm that this proposal was assessed.";
      recommendation = "Confirm analysis coverage";
      nextSteps = ["Refresh the analysis records. If coverage remains unavailable, run a new analysis that includes this proposal and the requirement documents."];
    } else if (included && !reliable) {
      status = "Evidence checks required";
      tone = "attention";
      resultSummary = "The available analysis has incomplete evidence checks, warnings or missing finding details.";
      recommendation = "Verify the evidence before deciding";
      nextSteps = ["Review the processing warnings and cited source pages in Assess.", "Refresh missing records and rerun the analysis if the source documents change."];
    } else if (included && related.some(open)) {
      status = "Clarification needed";
      tone = "attention";
      resultSummary = "This proposal is cited in findings that are still open or under review.";
      recommendation = "Request clarification from this vendor";
      nextSteps = ["Ask the vendor to respond to the findings below and provide evidence for the cited requirements.", "Compare the response with the TOR and technical specification before deciding whether to proceed."];
    } else if (included && shared.some(open)) {
      status = "Evaluation basis needs clarification";
      tone = "attention";
      resultSummary = "No open finding directly cites this proposal, but unresolved case findings may affect its evaluation.";
      recommendation = "Clarify the evaluation basis";
      nextSteps = ["Review the shared findings below and resolve the affected requirements or evidence before the final comparison."];
    } else if (included && (!comparisonInputs || requirementCount === null || requirementCount === 0)) {
      status = "Requirement coverage needs confirmation";
      tone = "attention";
      resultSummary = "The recorded result does not establish an extracted requirement baseline for this proposal.";
      recommendation = "Confirm the requirement baseline";
      nextSteps = ["Check that the TOR and technical specification were included and that requirements were extracted.", "Run a new analysis with the complete source documents before making a compliance decision."];
    } else if (included && related.length) {
      status = "Recorded findings closed";
      tone = "ready";
      resultSummary = "The findings citing this proposal are recorded as resolved or dismissed.";
      recommendation = "Review resolutions, then continue evaluation";
      nextSteps = ["Read the recorded resolution or dismissal notes and supporting evidence.", "Confirm every mandatory requirement and the proposal's commercial terms before final selection."];
    } else if (included) {
      status = "No recorded issues";
      tone = "ready";
      resultSummary = "No returned integrity finding directly cites this proposal in the completed analysis.";
      recommendation = "Continue with detailed evaluation";
      nextSteps = ["Confirm each mandatory technical requirement against the proposal and its supporting documents.", "Check delivery, warranty and commercial terms, then compare the eligible proposals and document your decision."];
    }
    return { document, coverage, findings: related, sharedFindings: shared, status, tone, resultSummary, recommendation, nextSteps };
  });
  return { caseResource, job, documents, headline, narrative, requirementCount, findingCount: result?.finding_ids.length ?? null,
    findings, missingFindings, proposals };
}
