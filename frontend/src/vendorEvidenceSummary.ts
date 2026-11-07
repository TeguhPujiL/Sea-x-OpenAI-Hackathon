import type { ApiClient } from "./api";
import { object, uuid, ShapeError, decodeJob, decodeFinding, decodeRepair, decodeReview,
  type JobResource, type FindingResource, type RepairResource, type ReviewResource } from "./contracts";
import type { Resources } from "./workflow";
import { vendorAssessment } from "./vendorAssessmentData";

export interface OfferFact {
  field: string; label: string; value: string; amount_idr: number | null;
  source: { document_id: string; page_number: number; excerpt: string };
}
export interface VendorEvidenceSummary {
  case_id: string; analysis_job_id: string;
  document_facts: { document_id: string; filename: string; facts: OfferFact[] }[];
  initial_analysis: JobResource | null; initial_findings: FindingResource[];
  repair_proposals: RepairResource[]; reviews: ReviewResource[];
  extraction_method: string; limitations: string[];
}
export function decodeVendorEvidenceSummary(value: unknown): VendorEvidenceSummary {
  const v = object(value);
  if (!uuid(v.case_id) || !uuid(v.analysis_job_id) || !Array.isArray(v.document_facts) || typeof v.extraction_method !== "string"
    || !Array.isArray(v.limitations) || !v.limitations.every(item => typeof item === "string")) throw new ShapeError("Invalid vendor source summary.");
  for (const entry of v.document_facts) {
    const document = object(entry);
    if (!uuid(document.document_id) || typeof document.filename !== "string" || !Array.isArray(document.facts)) throw new ShapeError("Invalid offer source document.");
    for (const value of document.facts) {
      const fact = object(value), source = object(fact.source);
      if (![fact.field, fact.label, fact.value, source.excerpt].every(item => typeof item === "string" && item.length > 0)
        || source.document_id !== document.document_id || !Number.isSafeInteger(source.page_number) || Number(source.page_number) < 1
        || !(fact.amount_idr === null || Number.isSafeInteger(fact.amount_idr) && Number(fact.amount_idr) >= 0)) throw new ShapeError("Invalid source-labelled offer fact.");
    }
  }
  if (v.initial_analysis !== null) decodeJob(v.initial_analysis);
  for (const [field, decoder] of [["initial_findings", decodeFinding], ["repair_proposals", decodeRepair], ["reviews", decodeReview]] as const) {
    if (!Array.isArray(v[field])) throw new ShapeError("Invalid original-finding history.");
    for (const item of v[field] as unknown[]) { decoder(item); if (object(item).case_id !== v.case_id) throw new ShapeError("Cross-case repair history rejected."); }
  }
  if (v.initial_analysis && object(v.initial_analysis).case_id !== v.case_id) throw new ShapeError("Cross-case original analysis rejected.");
  return value as VendorEvidenceSummary;
}
export async function loadVendorEvidenceSummary(client: ApiClient, caseId: string, analysisJobId: string, signal?: AbortSignal) {
  const value = await client.get(`/experimental/cases/${caseId}/vendor-assurance-summary?analysis_job_id=${analysisJobId}`, decodeVendorEvidenceSummary, signal);
  if (value.case_id !== caseId || value.analysis_job_id !== analysisJobId) throw new ShapeError("Vendor summary refers to another case or analysis.");
  return value;
}

export function vendorEvidence(resources: Resources, vendorId: string) {
  const snapshot = resources.vendorEvidenceSummary;
  const applicable = snapshot?.case_id === resources.caseResource?.case_id && snapshot?.analysis_job_id === resources.job?.job_id ? snapshot : undefined;
  const current = vendorAssessment(resources).vendors.find(vendor => vendor.id === vendorId);
  const initial = applicable?.initial_analysis ? vendorAssessment({ ...resources, job: applicable.initial_analysis, findings: applicable.initial_findings })
    .vendors.find(vendor => vendor.id === vendorId) : undefined;
  const originalFindings = [...new Map((initial?.packages.flatMap(pack => [...pack.findings, ...pack.sharedFindings]) ?? []).map(f => [f.finding_id, f])).values()];
  const initialInputs = new Set(applicable?.initial_analysis?.ai_execution?.input_document_ids ?? []);
  const currentInputs = new Set(resources.job?.ai_execution?.input_document_ids ?? []);
  const currentCount = current?.risk.score;
  return {
    available: !!applicable, initial_analysis_job_id: applicable?.initial_analysis?.job_id ?? null,
    reassessed: !!applicable?.initial_analysis && applicable.initial_analysis.job_id !== resources.job?.job_id,
    packages: (current?.packages ?? []).filter(pack => pack.inAnalysis).map(pack => {
      const ids = new Set(pack.documents.filter(doc => currentInputs.has(doc.document_id)).map(doc => doc.document_id));
      return { source: pack.source, facts: (applicable?.document_facts ?? []).filter(doc => ids.has(doc.document_id)).flatMap(doc => doc.facts),
        newly_included_document_ids: [...ids].filter(id => !initialInputs.has(id)) };
    }),
    original_findings: originalFindings.map(finding => {
      const repairs = (applicable?.repair_proposals ?? []).filter(repair => repair.finding_id === finding.finding_id);
      const repairIds = new Set(repairs.map(repair => repair.repair_proposal_id));
      const reviews = (applicable?.reviews ?? []).filter(review => repairIds.has(review.repair_proposal_id));
      const outcome = finding.status === "RESOLVED" ? "Resolved in the finding record" : finding.status === "DISMISSED" ? "Dismissed in the finding record"
        : repairs.length ? "Repair proposal recorded; finding resolution is not recorded" : "No repair proposal recorded for this original finding";
      return { finding_id: finding.finding_id, title: finding.title, status: finding.status, severity: finding.severity,
        evidence_status: finding.evidence_status, evidence: finding.evidence, outcome,
        repairs: repairs.map(repair => ({ repair_proposal_id: repair.repair_proposal_id, status: repair.status,
          before_text: repair.before_text, proposed_text: repair.proposed_text, justification: repair.justification, created_at: repair.created_at })),
        reviews: reviews.map(review => ({ review_id: review.review_id, decision: review.decision, decision_reason: review.decision_reason, created_at: review.created_at })) };
    }),
    current_assessment: currentCount === null || currentCount === undefined ? "Current documentation coverage still requires review"
      : currentCount === 0 ? "No current vendor findings returned; this does not mark original findings repaired"
      : `${currentCount} current vendor finding(s) remain`,
    limitations: applicable?.limitations ?? [],
  };
}
