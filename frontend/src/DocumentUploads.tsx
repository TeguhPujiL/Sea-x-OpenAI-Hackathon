import React from "react";
import { documentTypes, type DocumentResource, type DocumentType } from "./contracts";
import type { UploadItem } from "./uploads";
const human = (value: string) => value.replaceAll("_", " ").toLowerCase();
export function DocumentUploads({ disabled, items, onUpload, onRetry, onClear, autoClassify = false }: {
  autoClassify?: boolean; disabled: boolean; items: UploadItem[]; onUpload: (files: File[], description: string) => void; onRetry: () => void; onClear: () => void;
}) {
  const unresolved = items.some(item => item.status === "unknown" || item.status === "unverified");
  return <><form className="upload-form" onSubmit={e => {
    e.preventDefault(); const form = e.currentTarget; const data = new FormData(form);
    const files = data.getAll("file").filter((v): v is File => v instanceof File && v.size > 0);
    if (files.length) { onUpload(files, String(data.get("description") ?? "")); form.reset(); }
  }}><div className="upload-zone"><span className="upload-symbol" aria-hidden="true">↑</span><strong>Add source PDFs</strong>
    <p>{autoClassify ? "Select all PDFs together. Their contents will be classified into the nine document types after upload." : "Select multiple files. After upload, set the document type for each file below."}</p>
    <label className="field"><span>PDF files</span><input name="file" type="file" multiple accept="application/pdf,.pdf" required disabled={disabled || unresolved} /></label></div>
    <label className="field"><span>Description (optional)</span><input name="description" disabled={disabled || unresolved} /></label>
    <p className="muted">{autoClassify ? "Verified, unambiguous classifications fill the type automatically. Review uncertain results and correct any type before analysis." : "New files start as Other. Assign a TOR and technical specification before analysis."}</p>
    <button className="primary" disabled={disabled || unresolved}>Upload selected PDFs</button></form>
    {!!items.length && <section className="upload-progress" aria-label="Upload progress"><h3>Upload progress</h3><p aria-live="polite">{items.filter(item => item.status === "uploaded").length} of {items.length} uploaded</p>
      {autoClassify && <details><summary>Batch document types (9)</summary><dl className="metadata">{documentTypes.map(type => <React.Fragment key={type}><dt>{human(type)}</dt><dd>{items.filter(item => item.document?.document_type === type).length}</dd></React.Fragment>)}</dl></details>}
      <ul>{items.map(item => <li key={item.id}><strong>{item.file.name}</strong><span>{human(item.status)}</span>{item.error && <p className="inline-warning">{item.error}</p>}
        {item.classificationStatus && <span>{human(item.classificationStatus === "ready" ? "type_assigned" : item.classificationStatus)}</span>}
        {item.classification && <><p>Suggested type: {human(item.classification.suggested_type)}. {item.classification.rationale}</p><details><summary>Classification evidence</summary>{item.classification.evidence.map((ref, index) => <p key={index}>Page {ref.page_number} ({human(ref.verification_status)}): <q>{ref.excerpt}</q></p>)}<p>AI execution: <code>{item.classification.ai_execution_id}</code></p></details></>}
        {item.classificationStatus === "needs_review" && <p className="inline-warning">Check this document and select its correct type below. No uncertain type was automatically applied.</p>}
        {item.classificationError && <p className="inline-warning">PDF uploaded. Classification: {item.classificationError}</p>}{item.status === "unknown" && <p>The server outcome is unknown. Retry uses the same request key.</p>}{item.status === "unverified" && <p>Refresh documents and reconcile the result before uploading this file again.</p>}</li>)}</ul>
      <button className="quiet" disabled={disabled} onClick={onClear}>Clear upload list</button>
      {items.some(item => ["failed", "unknown", "pending"].includes(item.status) || ["failed", "unknown"].includes(item.classificationStatus ?? "")) && <button className="secondary" disabled={disabled} onClick={onRetry}>Retry incomplete processing</button>}
    </section>}
  </>;
}
export function DocumentTypeEditor({ document, disabled, value, onChange, requiresConfirmation = false }: {
  requiresConfirmation?: boolean; document: DocumentResource; disabled: boolean; value?: DocumentType; onChange: (id: string, type: DocumentType) => void;
}) {
  return <div className="document-type-editor"><label className="field"><span>Document type for {document.filename}</span>
    <select name="document_type" value={value ?? document.document_type} onChange={e => onChange(document.document_id, e.target.value as DocumentType)} disabled={disabled}>{documentTypes.map(type => <option value={type} key={type}>{human(type)}</option>)}</select></label>{requiresConfirmation && <button className="secondary" disabled={disabled} onClick={() => onChange(document.document_id, value ?? document.document_type)}>Confirm selected type</button>}</div>;
}
