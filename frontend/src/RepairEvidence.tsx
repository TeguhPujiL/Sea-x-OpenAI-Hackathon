import React, { useEffect, useState } from "react";
import type { DocumentType } from "./contracts";
import { DocumentTypeEditor } from "./DocumentUploads";
import { DocumentationRisk } from "./DocumentationRisk";
import { VendorGroup, VendorGroups } from "./VendorGroup";
import { vendorWorkflow } from "./vendorWorkflowData";
import type { UploadItem } from "./uploads";
import type { Resources } from "./workflow";
import { initialRevisionSelection, reconcileRevisionSelection, repairEvidence, revisionDocumentLabel, revisionReadiness, revisionUploadDescription } from "./repairEvidenceData";

export function RepairEvidence({ resources, disabled, onUpload, onReanalyze, documentTypeDrafts = {}, onDocumentType, onSaveDocumentTypes, uploadItems = [] }: {
  resources: Resources; disabled: boolean; onUpload: (files: File[], description: string) => void; onReanalyze: (documentIds: string[]) => void;
  documentTypeDrafts?: Record<string, DocumentType>; onDocumentType?: (id: string, type: DocumentType) => void;
  onSaveDocumentTypes?: () => void; uploadItems?: UploadItem[];
}) {
  const evidence = repairEvidence(resources), workflow = vendorWorkflow(resources);
  const [selection, setSelection] = useState(() => initialRevisionSelection(resources));
  const [reviewedIds, setReviewedIds] = useState<string[]>([]);
  const [allowExisting, setAllowExisting] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  useEffect(() => { setSelection(previous => reconcileRevisionSelection(resources, previous)); }, [evidence.key, resources.documents]);
  useEffect(() => { setReviewedIds([]); setAllowExisting(false); }, [evidence.key]);
  const readiness = revisionReadiness(resources, selection.selectedIds, reviewedIds, allowExisting, documentTypeDrafts);
  const currentSelection = new Set(selection.selectedIds);
  const unresolvedUpload = uploadItems.some(item => ["unknown", "unverified", "uploading", "pending"].includes(item.status));
  const locked = disabled || !evidence.caseId || unresolvedUpload || ["ARCHIVED", "REVIEW_COMPLETED"].includes(resources.caseResource?.case_status ?? "")
    || !!evidence.job && ["QUEUED", "PROCESSING"].includes(evidence.job.status);
  const typeChanges = evidence.documents.some(doc => documentTypeDrafts[doc.document_id] && documentTypeDrafts[doc.document_id] !== doc.document_type);
  function uploadForm(context: string) {
    return <form aria-label={`Revised PDF upload for ${context}`} onSubmit={event => {
      event.preventDefault(); setUploadError(null);
      const form = event.currentTarget, data = new FormData(form);
      const files = data.getAll("revised_files").filter((file): file is File => file instanceof File && file.size > 0);
      if (!files.length || files.some(file => !/\.pdf$/i.test(file.name))) {
        setUploadError("Select readable PDF revisions before uploading."); return;
      }
      try {
        const description = revisionUploadDescription(context, String(data.get("revision_reason") ?? ""));
        onUpload(files, description); form.reset();
      } catch (error) { setUploadError(error instanceof Error ? error.message : "Explain the revisions before uploading."); }
    }}>
      <label className="field"><span>Revised PDF files for {context}</span><input name="revised_files" type="file" multiple accept="application/pdf,.pdf" required disabled={locked} /></label>
      <label className="field"><span>Revision description</span><textarea name="revision_reason" rows={3} minLength={10} required disabled={locked} placeholder="Explain which challenge points these revisions address." /></label>
      <button className="secondary" disabled={locked}>Upload revised PDFs for {context}</button>
    </form>;
  }
  return <section className="repair-evidence" aria-labelledby="repair-evidence-title">
    <div className="section-title"><h3 id="repair-evidence-title">Upload and reassess revised evidence</h3><span className="count">{evidence.openPoints.length} open points</span></div>
    <p>Upload revisions under the vendor whose challenge points they address. Each upload creates new documents; originals and earlier findings remain available.</p>
    <p className="muted">Preserve the Vendor_A, Vendor_B or other vendor filename labels on quotations and warranty documents for consistent grouping. The description records upload context; it does not establish vendor ownership or replace a source document.</p>
    <h4>Evidence needed for open points</h4>
    <p className="muted">Check each point after reviewing its evidence needs. Shared points appear under every affected vendor; reviewing one updates that same recorded point wherever it appears. This acknowledgement does not resolve the finding.</p>
    <VendorGroups label="Repair vendor groups">{workflow.groups.map(group => <VendorGroup key={group.id} title={group.label} summary={<DocumentationRisk risk={group.risk} />}>
      {group.packages.map(pack => <section className="vendor-package" key={pack.source}>
        <h5>{pack.source === "uploaded" ? "Uploaded documents" : `${pack.source} package`}</h5>
        {!pack.points.length && <p>No open point is recorded for this option. Its documents can still be revised if needed.</p>}
        <fieldset disabled={locked}><legend className="sr-only">Review open points for {group.label}: {pack.source}</legend>{pack.points.map(point => <article className="repair-evidence-point vendor-concern" key={point.finding.finding_id}>
          <label className="checkbox"><input type="checkbox" data-finding-id={point.finding.finding_id} checked={reviewedIds.includes(point.finding.finding_id)} onChange={event => setReviewedIds(previous => event.target.checked ? [...new Set([...previous, point.finding.finding_id])] : previous.filter(id => id !== point.finding.finding_id))} />
            <span><strong>{point.finding.title}</strong> — evidence reviewed for re-analysis</span></label>
          {point.shared && <span className="shared-point-label">Shared point · same finding across affected vendors</span>}
          {point.challenges.map(challenge => <p key={challenge.challenge_id}><strong>Recorded challenge:</strong> {challenge.question}</p>)}
          <details><summary>Source evidence needing attention</summary>{point.finding.evidence.map((ref, index) => <p key={index}>{evidence.documents.find(doc => doc.document_id === ref.document_id)?.filename ?? "Document unavailable"} · Page {ref.page_number}: {ref.excerpt}</p>)}</details>
        </article>)}</fieldset>
      </section>)}
      {uploadForm(group.label)}
    </VendorGroup>)}</VendorGroups>
    {!evidence.openPoints.length && <p>No open point is recorded in the current analysis. A further evidence assessment remains available when needed.</p>}
    <details className="shared-revision-upload"><summary>Upload shared requirement or case documents</summary>
      <p>Use this for revisions to the TOR, specification or other evidence affecting multiple vendors.</p>{uploadForm("Shared case evidence")}
    </details>
    {uploadError && <p className="inline-warning" role="alert">{uploadError}</p>}
    {!!uploadItems.length && <section className="upload-progress" aria-label="Revised evidence upload progress"><h4>Revision upload progress</h4>
      <p role="status">{uploadItems.filter(item => item.status === "uploaded").length} / {uploadItems.length} uploaded</p>
      <ul>{uploadItems.map(item => <li key={item.id}><strong>{item.file.name}</strong><span>{item.status}</span><p>{item.description}</p>{item.error && <p>{item.error}</p>}</li>)}</ul>
      {unresolvedUpload && <p>Finish or reconcile pending uploads before re-analysis. An unknown server outcome must be refreshed or retried with its original request key.</p>}
    </section>}
    <details className="repair-evidence-selection"><summary>Current documents and evidence selection ({evidence.documents.length})</summary>
      <p>Select the documents to analyze together. Deselect superseded versions explicitly; uploading a similarly named file does not replace an earlier document.</p>
      <fieldset disabled={locked}><legend className="sr-only">Current evidence set</legend>{evidence.documents.map(doc => {
        const usable = evidence.usableDocuments.some(value => value.document_id === doc.document_id);
        return <div className="repair-evidence-document" key={doc.document_id}>
          <label className="checkbox"><input type="checkbox" checked={currentSelection.has(doc.document_id)} disabled={locked || !usable} onChange={event => setSelection(previous => ({ ...previous,
            selectedIds: event.target.checked ? [...new Set([...previous.selectedIds, doc.document_id])] : previous.selectedIds.filter(id => id !== doc.document_id) }))} />
            <span><strong>{doc.filename}</strong> · {doc.document_type.replaceAll("_", " ").toLowerCase()} · {doc.processing_status.toLowerCase()}</span></label>
          <p className="muted">{revisionDocumentLabel(doc, evidence.currentInputIds)} · {doc.page_count} pages</p><code>{doc.document_id}</code>
          {onDocumentType && <DocumentTypeEditor document={doc} disabled={locked} value={documentTypeDrafts[doc.document_id]} onChange={onDocumentType} />}
        </div>;
      })}</fieldset>
      {onSaveDocumentTypes ? <button className="secondary" disabled={locked || !typeChanges} onClick={onSaveDocumentTypes}>Save revision document types</button> : <p className="muted">Assign the correct types in Upload before replacing the selected TOR or technical specification.</p>}
    </details>
    <p role="status">{readiness.documentIds.length} documents selected for re-analysis.</p>
    <label className="checkbox"><input type="checkbox" checked={allowExisting} onChange={event => setAllowExisting(event.target.checked)} disabled={locked} />All needed evidence is already in the selected set; no additional upload is required.</label>
    <p className="muted">Selected evidence must include a usable TOR and technical specification. Recognizable filenames get a suggested document type; other names use Other. Review and save any type changes before re-analysis. The new analysis may still return concerns or evidence warnings.</p>
    {!!readiness.errors.length && <ul className="inline-warning" aria-label="Re-analysis requirements">{readiness.errors.map(error => <li key={error}>{error}</li>)}</ul>}
    <button className="primary" disabled={locked || !readiness.ready || selection.key !== evidence.key} onClick={() => onReanalyze(readiness.documentIds)}>Analyze selected revised evidence</button>
  </section>;
}
