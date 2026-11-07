import type { ApiClient } from "./api";
import { decodeAudit, decodeJob, uuid, ShapeError, type AuditResource, type CaseResource } from "./contracts";
import { listAll } from "./resources";
import { steps } from "./workflow";
import type { ProcurementStatusInfo } from "./ProcurementDecisionStatus";

export interface CaseActivity { events: AuditResource[]; error?: string; procurementStatus?: ProcurementStatusInfo }
export type HistoryActivity = Record<string, CaseActivity>;

export function latestActivity(value: CaseResource, activity?: CaseActivity): string {
  return [value.created_at, value.updated_at, ...(activity?.events.map(e => e.occurred_at) ?? [])]
    .reduce((latest, timestamp) => Date.parse(timestamp) > Date.parse(latest) ? timestamp : latest);
}

function eventStep(event: AuditResource): number | null {
  const type = event.event_type;
  if (type === "CASE_CREATED" || type.startsWith("DOCUMENT_")) return 0;
  if (type.startsWith("ANALYSIS_") || type.startsWith("FINDING_")) return 1;
  if (type.startsWith("CHALLENGE_")) return 2;
  if (type.startsWith("SIMULATION_")) return 3;
  if (type.startsWith("REPAIR_")) return 4;
  if (type.startsWith("REVIEW_") || type === "CASE_ASSURANCE_CHANGED" || type === "PROCUREMENT_CONCLUSION_RECORDED") return 5;
  return null;
}

async function loadProcurementStatus(client: ApiClient, caseId: string, events: AuditResource[]): Promise<ProcurementStatusInfo> {
  const recorded = events.filter(event => event.event_type === "PROCUREMENT_CONCLUSION_RECORDED")
    .sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at) || b.event_id.localeCompare(a.event_id));
  if (!recorded.length) return { state: "PENDING", detail: "No GO or NO-GO decision has been recorded." };
  // These are backend-redacted audit fields, not an inferred workflow status.
  // Fail visibly if an older server does not expose the required projection.
  if (recorded.some(event => !uuid(event.details.analysis_job_id)
    || !(event.details.decision === "GO" && typeof event.details.selected_vendor_id === "string" && /^[A-Z0-9]{1,40}$/.test(event.details.selected_vendor_id)
      || event.details.decision === "NO_GO" && event.details.selected_vendor_id === null))) {
    return { state: "UNAVAILABLE", detail: "The saved decision details are unavailable. Open the case and refresh resources." };
  }
  try {
    const jobs = await listAll(client, `/cases/${caseId}/jobs`, decodeJob);
    if (jobs.some(job => job.case_id !== caseId)) throw new ShapeError("Cross-case assessment history rejected.");
    const latest = jobs.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.job_id.localeCompare(a.job_id))[0];
    if (!latest) return { state: "UNAVAILABLE", detail: "The saved decision's assessment could not be found." };
    const current = recorded.find(event => event.details.analysis_job_id === latest.job_id);
    if (!current) {
      const previous = recorded[0];
      const label = previous.details.decision === "GO" ? `GO - Vendor ${previous.details.selected_vendor_id}` : "NO-GO - no vendor selected";
      return { state: "PENDING", detail: `A newer assessment needs a decision. Previous assessment: ${label}.` };
    }
    return { state: current.details.decision as "GO" | "NO_GO", vendorId: typeof current.details.selected_vendor_id === "string" ? current.details.selected_vendor_id : undefined,
      recordedAt: current.occurred_at, detail: "Saved internal procurement decision for the latest assessment." };
  } catch (error) {
    return { state: "UNAVAILABLE", detail: error instanceof Error ? error.message : "Could not verify the latest assessment." };
  }
}

export function stepActivity(activity?: CaseActivity) {
  return steps.map((name, index) => {
    const events = (activity?.events ?? []).filter(e => eventStep(e) === index)
      .sort((a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at) || a.event_id.localeCompare(b.event_id));
    return { name, events, latest: events.at(-1)?.occurred_at ?? null };
  });
}

// Audit reads retain the backend's authorization/redaction. Limit concurrency
// when history contains many cases, and keep cases visible if a read is denied.
export async function loadHistoryActivity(client: ApiClient, cases: CaseResource[]): Promise<HistoryActivity> {
  const result: HistoryActivity = {};
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(4, cases.length) }, async () => {
    while (next < cases.length) {
      const value = cases[next++];
      try {
        const events = await listAll(client, `/cases/${value.case_id}/audit`, decodeAudit);
        if (events.some(e => e.case_id !== value.case_id)) throw new ShapeError("Cross-case activity response rejected.");
        result[value.case_id] = { events, procurementStatus: await loadProcurementStatus(client, value.case_id, events) };
      } catch (error) {
        result[value.case_id] = { events: [], error: error instanceof Error ? error.message : "Could not load activity" };
      }
    }
  }));
  return result;
}
