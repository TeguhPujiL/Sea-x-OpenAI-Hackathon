import { RequestError, TransportError, type ApiClient, type PreparedRequest } from "./api";
import { decodeDocument, ShapeError, type DocumentResource, type DocumentType } from "./contracts";
import { detectDocumentType } from "./documentTypeDetection";
export type UploadStatus = "pending" | "uploading" | "uploaded" | "failed" | "unknown" | "unverified";
export interface UploadItem {
  id: string; file: File; description: string; status: UploadStatus; error?: string;
  documentType?: DocumentType;
  request?: PreparedRequest<DocumentResource>; document?: DocumentResource;
}
export function newUploadItems(files: File[], description: string): UploadItem[] {
  return files.map(file => ({ id: crypto.randomUUID(), file, description, status: "pending", documentType: detectDocumentType(file.name) }));
}
export async function uploadBatch(client: ApiClient, caseId: string, items: UploadItem[],
  changed: (items: UploadItem[]) => void, uploaded: (doc: DocumentResource) => void,
  signal: AbortSignal): Promise<UploadItem[]> {
  let queue = items.map(item => ({ ...item }));
  const update = (index: number, patch: Partial<UploadItem>) => {
    queue = queue.map((item, i) => i === index ? { ...item, ...patch } : item); changed(queue);
  };
  for (let index = 0; index < queue.length; index++) {
    if (signal.aborted) break;
    const item = queue[index];
    if (item.status === "uploaded" || item.status === "unverified") continue;
    update(index, { status: "uploading", error: undefined });
    let document: DocumentResource;
    try {
      if (!item.file.size || item.file.type && item.file.type !== "application/pdf" || await item.file.slice(0, 5).text() !== "%PDF-") {
        throw new Error("Choose a nonempty PDF with a valid PDF signature.");
      }
      let request = item.request;
      if (!request) {
        const form = new FormData(); form.append("file", item.file); form.append("document_type", item.documentType ?? detectDocumentType(item.file.name));
        if (item.description.trim()) form.append("description", item.description.trim());
        request = client.prepare("POST", `/cases/${caseId}/documents`, decodeDocument, { multipart: form, status: 201 });
        update(index, { request });
      }
      document = await request.send(signal);
      if (document.case_id !== caseId) throw new ShapeError("Uploaded document belongs to another case.");
    } catch (error) {
      if (signal.aborted) break;
      const status = error instanceof TransportError ? "unknown" : error instanceof ShapeError ? "unverified" : "failed";
      update(index, { status, request: status === "unknown" ? queue[index].request : undefined,
        error: error instanceof Error ? error.message : "Upload failed" });
      // An unverifiable response may already have created a record. Reconcile
      // before allowing any new request for that file; never duplicate blindly.
      if (status === "unverified") break;
      continue;
    }
    update(index, { status: "uploaded", document, request: undefined });
    uploaded(document);
  }
  return queue;
}
