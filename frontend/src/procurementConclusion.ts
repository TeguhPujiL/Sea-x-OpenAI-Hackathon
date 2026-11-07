import type { ApiClient } from "./api";
import { object, uuid, ShapeError } from "./contracts";

export type ProcurementDecision = "GO" | "NO_GO";
export interface ProcurementConclusion {
  conclusion_id: string; case_id: string; analysis_job_id: string;
  decision: ProcurementDecision; selected_vendor_id: string | null; selected_vendor_label: string | null;
  decision_reason: string; source_case_version: number; created_at: string;
  reviewer: { actor_id: string; display_name: string; role: string };
  scope: "INTERNAL_PROCUREMENT_CONCLUSION"; snapshot: Record<string, unknown>;
}
export function decodeConclusion(value: unknown): { conclusion: ProcurementConclusion | null } {
  const data = object(value);
  if (data.conclusion === null) return { conclusion: null };
  const v = object(data.conclusion), reviewer = object(v.reviewer);
  if (![v.conclusion_id, v.case_id, v.analysis_job_id, reviewer.actor_id].every(uuid)
    || !["GO", "NO_GO"].includes(String(v.decision)) || v.scope !== "INTERNAL_PROCUREMENT_CONCLUSION"
    || typeof v.decision_reason !== "string" || v.decision_reason.trim().length < 20
    || typeof v.created_at !== "string" || !v.created_at.endsWith("Z") || !Number.isFinite(Date.parse(v.created_at))
    || !Number.isSafeInteger(v.source_case_version) || Number(v.source_case_version) < 1
    || typeof reviewer.display_name !== "string" || typeof reviewer.role !== "string"
    || !(v.decision === "NO_GO" ? v.selected_vendor_id === null && v.selected_vendor_label === null
      : typeof v.selected_vendor_id === "string" && /^[A-Z0-9]{1,40}$/.test(v.selected_vendor_id) && v.selected_vendor_label === `Vendor ${v.selected_vendor_id}`)) {
    throw new ShapeError("Invalid saved procurement conclusion.");
  }
  object(v.snapshot);
  return data as unknown as { conclusion: ProcurementConclusion };
}
export async function loadConclusion(client: ApiClient, caseId: string, analysisId: string, signal?: AbortSignal) {
  const value = await client.get(`/experimental/cases/${caseId}/procurement-conclusions?analysis_job_id=${analysisId}`, decodeConclusion, signal);
  if (value.conclusion && (value.conclusion.case_id !== caseId || value.conclusion.analysis_job_id !== analysisId)) throw new ShapeError("Cross-case procurement conclusion rejected.");
  return value.conclusion;
}
