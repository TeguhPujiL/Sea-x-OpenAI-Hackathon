import { uuid, type CaseResource, type DocumentResource, type JobResource, type FindingResource, type ChallengeResource, type SimulationResource, type RepairResource, type ReviewResource, type AuditResource } from "./contracts";
import type { FindingScenario } from "./findingScenarios";
export const steps = ["Upload", "Assess", "Challenge", "Simulate", "Repair", "Assure"] as const;
export interface Identifiers {
  case_id: string | null; document_ids: string[]; analysis_job_id: string | null; selected_finding_id: string | null;
  challenge_id: string | null; simulation_id: string | null; repair_proposal_id: string | null;
}
export const emptyIds = (): Identifiers => ({ case_id: null, document_ids: [], analysis_job_id: null, selected_finding_id: null, challenge_id: null, simulation_id: null, repair_proposal_id: null });
export interface Resources {
  caseResource: CaseResource | null; documents: DocumentResource[]; job: JobResource | null;
  findings: FindingResource[]; challenge: ChallengeResource | null; simulation: SimulationResource | null;
  repair: RepairResource | null; reviews: ReviewResource[]; audit: AuditResource[];
  challengeHistory?: ChallengeResource[]; simulationHistory?: SimulationResource[];
  findingScenarioHistory?: FindingScenario[];
}
export const emptyResources = (): Resources => ({ caseResource: null, documents: [], job: null, findings: [], challenge: null, simulation: null, repair: null, reviews: [], audit: [] });
export const storageKey = "procuremind.workspace.ids.v1";
type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export function readIds(storage: StorageLike): Identifiers {
  try {
    const value = JSON.parse(storage.getItem(storageKey) ?? "null");
    if (!value || typeof value !== "object" || !uuid(value.case_id)) return emptyIds();
    const result = emptyIds(); result.case_id = value.case_id;
    for (const key of ["analysis_job_id", "selected_finding_id", "challenge_id", "simulation_id", "repair_proposal_id"] as const) result[key] = uuid(value[key]) ? value[key] : null;
    result.document_ids = Array.isArray(value.document_ids) ? value.document_ids.filter(uuid) : [];
    return result;
  } catch { return emptyIds(); }
}
export function saveIds(storage: StorageLike, ids: Identifiers): boolean {
  try {
    // Explicit allowlist: never persist resource contents, status, versions, reviewer identity or current step.
    const clean = emptyIds();
    for (const key of ["case_id", "analysis_job_id", "selected_finding_id", "challenge_id", "simulation_id", "repair_proposal_id"] as const) clean[key] = uuid(ids[key]) ? ids[key] : null;
    clean.document_ids = ids.document_ids.filter(uuid);
    storage.setItem(storageKey, JSON.stringify(clean)); return true;
  } catch { return false; }
}
export const terminal = (status: string) => ["COMPLETED", "FAILED", "NEEDS_REVIEW"].includes(status);
export const cleanCase = (job: JobResource | null) => !!job && terminal(job.status) && job.result !== null && job.result.finding_ids.length === 0;
export function hasRequiredDocuments(documents: DocumentResource[]): boolean {
  // P0 comparison uses a TOR and technical specification. This is a UI prerequisite, not a new backend rule.
  return ["TOR", "TECHNICAL_SPECIFICATION"].every(type => documents.some(d => d.document_type === type && !d.deleted_at && d.processing_status !== "FAILED" && d.page_count > 0));
}
export function canReview(resources: Resources): boolean {
  return !cleanCase(resources.job) && resources.repair?.status === "SUBMITTED"
    && !resources.reviews.some(review => review.repair_proposal_id === resources.repair?.repair_proposal_id) && !!resources.caseResource;
}
export function recoveredStep(r: Resources): number {
  if (r.reviews.length || r.repair?.status === "SUBMITTED") return 5;
  if (!r.repair && r.job && ["FAILED", "NEEDS_REVIEW"].includes(r.job.status)) return 1;
  if (cleanCase(r.job)) return 5;
  if (r.repair) return 4;
  if (r.simulation || r.challenge) return 3;
  if (r.findings.length) return 2;
  if (r.job || hasRequiredDocuments(r.documents)) return 1;
  return 0;
}
export function nextAction(r: Resources): string {
  if (!r.caseResource) return "Create a case to establish the evidence workspace.";
  if (cleanCase(r.job)) return r.job?.status === "NEEDS_REVIEW" ? "Read the processing warnings. No findings were returned; completion still awaits a contract decision." : "No findings were returned. Clean-case completion awaits a contract decision.";
  if (r.reviews.length) return "Inspect the recorded decision and refresh the audit timeline.";
  if (r.repair?.status === "SUBMITTED") return "Record an authorized internal review with a decision reason.";
  if (r.repair) return "Review the proposed text, save your changes, then submit the draft.";
  if (r.simulation) return "Generate a repair draft grounded in the recorded simulation.";
  if (r.challenge) return "Compare a counterfactual using the versioned synthetic supplier dataset.";
  if (r.findings.length) return "Select a finding and request a neutral, evidence-grounded challenge.";
  if (r.job && !terminal(r.job.status)) return "Wait for the analysis to reach an authoritative terminal status.";
  if (r.job?.status === "FAILED") return "Read the processing error and retry only when the cause is resolved.";
  if (hasRequiredDocuments(r.documents)) return "Start the requirement extraction and contradiction analysis.";
  return "Upload a TOR and technical specification for the P0 comparison.";
}
export function abortableDelay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(signal.reason); return; }
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, ms);
    signal.addEventListener("abort", abort, { once: true });
  });
}
export async function pollJob(get: (signal: AbortSignal) => Promise<JobResource>, onJob: (job: JobResource) => void, signal: AbortSignal, wait = abortableDelay): Promise<JobResource> {
  let delay = 1000;
  while (!signal.aborted) {
    await wait(delay, signal);
    const job = await get(signal);
    if (signal.aborted) throw signal.reason;
    onJob(job);
    if (terminal(job.status)) return job;
    delay = Math.min(delay * 2, 5000);
  }
  throw signal.reason;
}
