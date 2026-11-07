import type { DocumentResource, DocumentType } from "./contracts";
import type { Resources } from "./workflow";

export interface RevisionSelection { key: string; knownIds: string[]; selectedIds: string[] }

export function repairEvidence(resources: Resources) {
  const caseId = resources.caseResource?.deleted_at ? null : resources.caseResource?.case_id;
  const documents = resources.documents.filter(doc => !!caseId && doc.case_id === caseId && !doc.deleted_at);
  const usableDocuments = documents.filter(doc => doc.processing_status === "COMPLETED" && Number.isInteger(doc.page_count) && doc.page_count > 0);
  const job = resources.job?.case_id === caseId ? resources.job : null;
  const currentInputIds = new Set(job?.ai_execution?.input_document_ids ?? []);
  const openPoints = resources.findings.filter(finding => finding.case_id === caseId && finding.analysis_job_id === job?.job_id
    && job?.result?.finding_ids.includes(finding.finding_id) && ["OPEN", "UNDER_REVIEW"].includes(finding.status));
  return { caseId, documents, usableDocuments, job, currentInputIds, openPoints,
    key: `${caseId ?? "no-case"}:${job?.job_id ?? "no-analysis"}:${job?.ai_execution?.execution_id ?? "no-execution"}` };
}

export function initialRevisionSelection(resources: Resources): RevisionSelection {
  const evidence = repairEvidence(resources);
  const knownIds = evidence.usableDocuments.map(doc => doc.document_id);
  return { key: evidence.key, knownIds, selectedIds: evidence.job?.ai_execution
    ? knownIds.filter(id => evidence.currentInputIds.has(id)) : [...knownIds] };
}

export function reconcileRevisionSelection(resources: Resources, previous: RevisionSelection): RevisionSelection {
  const evidence = repairEvidence(resources);
  if (previous.key !== evidence.key) return initialRevisionSelection(resources);
  const knownIds = evidence.usableDocuments.map(doc => doc.document_id);
  const usable = new Set(knownIds), known = new Set(previous.knownIds);
  const selectedIds = [...new Set([...previous.selectedIds.filter(id => usable.has(id)), ...knownIds.filter(id => !known.has(id))])];
  if (knownIds.join() === previous.knownIds.join() && selectedIds.join() === previous.selectedIds.join()) return previous;
  return { key: evidence.key, knownIds, selectedIds };
}

export function validateEvidenceSet(resources: Resources, selectedIds: string[]) {
  const evidence = repairEvidence(resources);
  const errors: string[] = [];
  const documentIds = [...new Set(selectedIds)];
  const selected = new Set(documentIds);
  const documents = evidence.usableDocuments.filter(doc => selected.has(doc.document_id));
  if (!evidence.caseId) errors.push("Create or reopen an active case before analyzing revised evidence.");
  if (["ARCHIVED", "REVIEW_COMPLETED"].includes(resources.caseResource?.case_status ?? "")) errors.push("This case is closed for new evidence assessments.");
  if (!documentIds.length) errors.push("Select the current documents to analyze.");
  if (documentIds.length !== selectedIds.length) errors.push("Select each document only once.");
  if (documents.length !== documentIds.length) errors.push("Selected evidence contains an unavailable, foreign, deleted or unprocessed document. Refresh and select usable documents.");
  for (const type of ["TOR", "TECHNICAL_SPECIFICATION"]) {
    if (!documents.some(doc => doc.document_type === type)) errors.push(`Include a ${type === "TOR" ? "TOR" : "technical specification"} in the selected evidence set.`);
  }
  if (evidence.job && ["QUEUED", "PROCESSING"].includes(evidence.job.status)) errors.push("Wait for the active analysis to finish.");
  return { documentIds, documents, errors, ready: errors.length === 0 };
}

export function revisionReadiness(resources: Resources, selectedIds: string[], reviewedIds: string[], allowExistingEvidence: boolean,
  typeDrafts: Record<string, DocumentType> = {}) {
  const evidence = repairEvidence(resources), validation = validateEvidenceSet(resources, selectedIds);
  const errors = [...validation.errors];
  const reviewed = new Set(reviewedIds);
  if (evidence.openPoints.some(point => !reviewed.has(point.finding_id))) errors.push("Review the evidence needed for every open point before starting re-analysis.");
  const newlyIncluded = validation.documents.filter(doc => !evidence.currentInputIds.has(doc.document_id));
  if (evidence.job && !newlyIncluded.length && !allowExistingEvidence) errors.push("Include revised evidence or confirm that all needed evidence is already in the selected set.");
  if (evidence.documents.some(doc => typeDrafts[doc.document_id] && typeDrafts[doc.document_id] !== doc.document_type)) errors.push("Save document type changes before re-analysis.");
  return { ...validation, errors, ready: errors.length === 0, newlyIncluded };
}

export function revisionDocumentLabel(document: DocumentResource, currentInputIds: Set<string>) {
  return currentInputIds.has(document.document_id) ? "Included in the recorded analysis" : "Not included in the recorded analysis";
}

export function revisionUploadDescription(context: string, reason: string) {
  const explanation = reason.trim();
  if (explanation.length < 10) throw new Error("Explain the revisions in at least ten characters.");
  return `${context}: ${explanation}`;
}
