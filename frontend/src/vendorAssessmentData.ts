import type { DocumentResource, EvidenceRef, FindingResource } from "./contracts";
import { assuranceSummary } from "./assuranceSummaryData";
import type { Resources } from "./workflow";

const vendorPattern = /(?:^|[\s_.-])vendor[\s_-]+([a-z0-9]+)(?=[\s_.-]|$)/i;
export function documentVendor(document: DocumentResource): string | null {
  return document.filename.match(vendorPattern)?.[1].toUpperCase() ?? null;
}
export function documentPackage(document: DocumentResource): string {
  // Keep distinct uploaded packages distinct; their names never determine validity.
  return document.filename.match(/^(Positive|Negative)__/i)?.[1].toLowerCase() ?? "uploaded";
}
export const activeConcern = (finding: FindingResource) => ["OPEN", "UNDER_REVIEW"].includes(finding.status);

export function vendorAssessment(resources: Resources) {
  const summary = assuranceSummary(resources);
  const { job, documents, findings, caseResource } = summary;
  const inputIds = new Set(job?.ai_execution?.input_document_ids ?? []);
  const byId = new Map(documents.map(d => [d.document_id, d]));
  const validCitation = (ref: EvidenceRef) => {
    const doc = byId.get(ref.document_id);
    return !!doc && inputIds.has(doc.document_id) && ref.verification_status === "VERIFIED"
      && Number.isInteger(ref.page_number) && ref.page_number >= 1 && ref.page_number <= doc.page_count && !!ref.excerpt.trim();
  };
  const evidenceReliable = !!job?.result && job.status === "COMPLETED" && !!job.ai_execution?.schema_valid
    && job.ai_execution.evidence_validation_passed && job.ai_execution.evidence_checks.failed === 0
    && !job.warnings.length && !summary.missingFindings && findings.every(f => f.evidence_status === "VERIFIED" && f.evidence.length > 0 && f.evidence.every(validCitation));
  const baselineIncluded = ["TOR", "TECHNICAL_SPECIFICATION"].every(type => documents.some(d => d.document_type === type
    && d.processing_status === "COMPLETED" && inputIds.has(d.document_id))) && (summary.requirementCount ?? 0) > 0;
  const quotationDocuments = documents.filter(d => d.document_type === "SUPPLIER_QUOTATION");
  const vendorIds = [...new Set(quotationDocuments.map(documentVendor).filter((id): id is string => !!id))].sort();
  const knownGroups = new Set(quotationDocuments.flatMap(d => documentVendor(d) ? [`${documentVendor(d)}:${documentPackage(d)}`] : []));
  const findingGroups = new Map<string, Set<string>>();
  for (const finding of findings) {
    const groups = new Set<string>();
    for (const ref of finding.evidence) {
      if (!validCitation(ref)) continue;
      const doc = byId.get(ref.document_id)!;
      const namedVendor = documentVendor(doc);
      if (namedVendor && knownGroups.has(`${namedVendor}:${documentPackage(doc)}`)) groups.add(`${namedVendor}:${documentPackage(doc)}`);
      // A cited evaluation/order may name a vendor without having that vendor in
      // its filename. Scope that association to the cited document's package.
      for (const match of ref.excerpt.matchAll(/\bvendor[\s_-]+([a-z0-9]+)\b/gi)) {
        const key = `${match[1].toUpperCase()}:${documentPackage(doc)}`;
        if (knownGroups.has(key)) groups.add(key);
      }
    }
    findingGroups.set(finding.finding_id, groups);
  }
  const sharedFindings = findings.filter(f => !findingGroups.get(f.finding_id)?.size);
  const vendors = vendorIds.map(id => ({ id, label: `Vendor ${id}`, packages: [...new Set(quotationDocuments
    .filter(d => documentVendor(d) === id).map(documentPackage))].sort().map(source => {
      const relatedDocuments = documents.filter(d => documentVendor(d) === id && documentPackage(d) === source);
      const relatedFindings = findings.filter(f => findingGroups.get(f.finding_id)?.has(`${id}:${source}`));
      const ready = (type: string) => relatedDocuments.some(d => d.document_type === type && d.processing_status === "COMPLETED" && inputIds.has(d.document_id));
      const quotationPresent = relatedDocuments.some(d => d.document_type === "SUPPLIER_QUOTATION");
      const warrantyPresent = relatedDocuments.some(d => d.document_type === "WARRANTY_EVIDENCE");
      const analyzedDocuments = relatedDocuments.filter(d => inputIds.has(d.document_id)).length;
      const openFindings = relatedFindings.filter(activeConcern);
      const candidate = evidenceReliable && baselineIncluded && ready("SUPPLIER_QUOTATION") && ready("WARRANTY_EVIDENCE") && !openFindings.length;
      const status = !job || !job.result ? "Assessment pending" : !evidenceReliable ? "Evidence review required"
        : openFindings.length ? "Clarification available" : !ready("SUPPLIER_QUOTATION") || !ready("WARRANTY_EVIDENCE")
        ? "Document coverage incomplete" : !baselineIncluded ? "Requirement coverage incomplete" : "Candidate for detailed evaluation";
      return { source, documents: relatedDocuments, findings: relatedFindings, openFindings, candidate, status,
        quotationPresent, warrantyPresent, analyzedDocuments };
    }) }));
  const canChallenge = (finding: FindingResource) => findings.some(f => f.finding_id === finding.finding_id)
    && finding.case_id === caseResource?.case_id && finding.analysis_job_id === job?.job_id
    && activeConcern(finding) && finding.evidence_status === "VERIFIED"
    && finding.evidence.length > 0 && finding.evidence.every(validCitation)
    && !["ARCHIVED", "REVIEW_COMPLETED"].includes(caseResource?.case_status ?? "") && !!caseResource;
  return { vendors, sharedFindings, summary, canChallenge,
    candidateCount: vendors.flatMap(v => v.packages).filter(p => p.candidate).length,
    unassigned: quotationDocuments.filter(d => !documentVendor(d)) };
}
