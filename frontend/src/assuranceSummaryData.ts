import type { DocumentResource, FindingResource, ReviewDecision } from "./contracts";
import type { Resources } from "./workflow";

export const reviewLabels: Record<ReviewDecision, string> = {
  APPROVE_DRAFT: "Repair draft approved",
  REQUEST_REVISION: "Revision requested",
  REQUEST_EVIDENCE: "More evidence requested",
  REJECT_DRAFT: "Repair draft rejected",
};

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
      ? "The analysis returned integrity findings. Review their evidence and the recorded human decision below."
      : "The completed analysis returned no integrity findings for the documents it analyzed.";
  }
  const relatedFindings = (document: DocumentResource): FindingResource[] => findings.filter(f => f.evidence.some(e => e.document_id === document.document_id));
  const proposals = documents.filter(d => d.document_type === "SUPPLIER_QUOTATION").map(document => {
    const included = !!execution?.input_document_ids.includes(document.document_id);
    const related = included ? relatedFindings(document) : [];
    const coverage = !included ? "Not included in this analysis"
      : job?.status === "QUEUED" || job?.status === "PROCESSING" ? "Analysis in progress"
      : job?.status === "FAILED" ? "Analysis failed"
      : !reliable ? "Evidence review required"
      : related.length ? "Included; see recorded findings" : "Included; no finding cites this proposal";
    return { document, coverage, findings: related };
  });
  // An approval of a correction is scoped to that repair, not every vendor.
  const repair = resources.repair;
  const review = repair && repair.case_id === caseId && findings.some(f => f.finding_id === repair.finding_id)
    ? resources.reviews.filter(v => v.case_id === caseId && v.repair_proposal_id === repair.repair_proposal_id)
      .sort((a,b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0] ?? null : null;
  return { caseResource, job, documents, headline, narrative, requirementCount, findingCount: result?.finding_ids.length ?? null,
    findings, missingFindings, proposals, review };
}
