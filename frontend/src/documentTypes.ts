import type { ApiClient } from "./api";
import { decodeDocument, ShapeError, type DocumentResource, type DocumentType } from "./contracts";
export async function saveDocumentTypes(client: ApiClient, documents: DocumentResource[], drafts: Record<string, DocumentType>, saved: (doc: DocumentResource) => void, signal: AbortSignal) {
  for (const document of documents) {
    const type = drafts[document.document_id];
    if (!type || type === document.document_type) continue;
    const value = await client.prepare("PATCH", `/documents/${document.document_id}`, decodeDocument, {
      body: { document_type: type, expected_version: document.version },
    }).send(signal);
    if (value.document_id !== document.document_id || value.case_id !== document.case_id) throw new ShapeError("Document update identity does not match");
    saved(value);
  }
}
