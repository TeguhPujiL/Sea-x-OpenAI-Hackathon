import type { ApiClient } from "./api";
import { decodeAudit, ShapeError, type AuditResource, type CaseResource } from "./contracts";
import { listAll } from "./resources";
import { steps } from "./workflow";

export interface CaseActivity { events: AuditResource[]; error?: string }
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
  if (type.startsWith("REVIEW_") || type === "CASE_ASSURANCE_CHANGED") return 5;
  return null;
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
        result[value.case_id] = { events };
      } catch (error) {
        result[value.case_id] = { events: [], error: error instanceof Error ? error.message : "Could not load activity" };
      }
    }
  }));
  return result;
}
