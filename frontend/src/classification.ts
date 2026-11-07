import { TransportError, RequestError, type ApiClient } from "./api";
import { documentTypes, object, uuid, decodeDocument, ShapeError, type DocumentType, type EvidenceRef } from "./contracts";
import type { UploadItem } from "./uploads";

export interface Classification {
  document_id: string; case_id: string; expected_version: number; suggested_type: DocumentType;
  confidence: number; status: "AUTO_READY" | "NEEDS_REVIEW"; rationale: string; evidence: EvidenceRef[]; ai_execution_id: string;
}
export function decodeClassification(raw: unknown): Classification {
  const v = object(raw);
  if (!uuid(v.document_id) || !uuid(v.case_id) || !uuid(v.ai_execution_id) || !Number.isSafeInteger(v.expected_version) || (v.expected_version as number) < 1 ||
      !documentTypes.includes(v.suggested_type as DocumentType) || !["AUTO_READY", "NEEDS_REVIEW"].includes(v.status as string) ||
      typeof v.confidence !== "number" || v.confidence < 0 || v.confidence > 1 || typeof v.rationale !== "string" || !Array.isArray(v.evidence)) {
    throw new ShapeError("Invalid document classification response.");
  }
  for (const rawRef of v.evidence) {
    const ref = object(rawRef);
    if (!uuid(ref.document_id) || !Number.isSafeInteger(ref.page_number) || (ref.page_number as number) < 1 || typeof ref.excerpt !== "string" ||
        !["VERIFIED", "UNVERIFIED"].includes(ref.verification_status as string)) throw new ShapeError("Invalid classification evidence.");
  }
  if (v.status === "AUTO_READY" && (v.suggested_type === "OTHER" || v.confidence < .9 || !v.evidence.length || v.evidence.some(ref => ref.document_id !== v.document_id || ref.verification_status !== "VERIFIED"))) throw new ShapeError("Automatic classification lacks verified supporting evidence.");
  return v as unknown as Classification;
}

export async function classifyBatch(client: ApiClient, caseId: string, items: UploadItem[], changed: (items: UploadItem[]) => void,
  saved: (document: NonNullable<UploadItem["document"]>) => void, signal: AbortSignal): Promise<UploadItem[]> {
  let queue = items.map(item => ({ ...item })); let cursor = 0;
  const update = (i: number, patch: Partial<UploadItem>) => { queue = queue.map((q, n) => n === i ? { ...q, ...patch } : q); changed(queue); };
  async function worker() {
    while (!signal.aborted) {
      const i = cursor++; if (i >= queue.length) return;
      const item = queue[i];
      if (item.status !== "uploaded" || !item.document || ["ready", "needs_review"].includes(item.classificationStatus ?? "")) continue;
      update(i, { classificationStatus: "classifying", classificationError: undefined });
      try {
        let proposal = item.classification;
        if (!proposal) {
          const request = item.classificationRequest ?? client.prepare("POST", `/documents/${item.document.document_id}/classifications`, decodeClassification,
            { status: 201, body: { expected_version: item.document.version } });
          update(i, { classificationRequest: request });
          proposal = await request.send(signal);
          if (proposal.document_id !== item.document.document_id || proposal.case_id !== caseId || proposal.expected_version !== item.document.version) throw new ShapeError("Classification belongs to another document, case or version.");
          update(i, { classification: proposal, classificationRequest: undefined });
        }
        if (proposal.status !== "AUTO_READY") { update(i, { classificationStatus: "needs_review" }); continue; }
        const request = item.typeRequest ?? client.prepare("PATCH", `/documents/${proposal.document_id}`, decodeDocument,
          { body: { document_type: proposal.suggested_type, expected_version: proposal.expected_version } });
        update(i, { typeRequest: request });
        let document;
        try { document = await request.send(signal); }
        catch (error) {
          // A version conflict/transport interruption may follow an already applied
          // PATCH. Reconcile the authoritative record rather than upload again.
          document = await client.get(`/documents/${proposal.document_id}`, decodeDocument, signal);
          if (document.case_id !== caseId || document.document_id !== proposal.document_id) throw new ShapeError("Reconciled document identity does not match.");
          update(i, { document }); saved(document);
          if (document.document_type !== proposal.suggested_type || document.version < proposal.expected_version + 1) throw error;
        }
        if (document.case_id !== caseId || document.document_id !== proposal.document_id || document.document_type !== proposal.suggested_type) throw new ShapeError("Classified document identity/type does not match.");
        update(i, { document, classificationStatus: "ready", typeRequest: undefined }); saved(document);
      } catch (error) {
        if (signal.aborted) return;
        update(i, { classificationStatus: error instanceof RequestError && error.status === 409 ? "needs_review" : error instanceof TransportError ? "unknown" : "failed", classificationError: error instanceof Error ? error.message : "Classification failed",
          classificationRequest: error instanceof TransportError ? queue[i].classificationRequest : undefined, typeRequest: undefined });
      }
    }
  }
  await Promise.all([worker(), worker()]);
  return queue;
}
