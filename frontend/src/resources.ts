import { type ApiClient } from "./api";
import { decodeCase, decodeDocument, decodeJob, decodeFinding, decodeChallenge, decodeSimulation, decodeRepair, decodeReview, decodeAudit, pageDecoder, ShapeError, type Decoder, type Page } from "./contracts";
import { emptyResources, terminal, type Identifiers, type Resources } from "./workflow";

export async function listAll<T>(client: ApiClient, path: string, decoder: Decoder<T>, signal?: AbortSignal): Promise<T[]> {
  const items: T[] = []; let offset = 0;
  for (;;) {
    const page: Page<T> = await client.get(`${path}${path.includes("?") ? "&" : "?"}limit=50&offset=${offset}`, pageDecoder(decoder), signal);
    if (page.pagination.offset !== offset) throw new ShapeError("The API returned an unexpected pagination offset.");
    items.push(...page.items);
    if (items.length >= page.pagination.total) return items;
    if (!page.items.length) throw new ShapeError("The API returned an incomplete page. Refresh before proceeding.");
    offset += page.items.length;
  }
}
function belongs<T extends { case_id: string }>(value: T, caseId: string): T {
  if (value.case_id !== caseId) throw new ShapeError("Resource does not belong to the active case. No cross-case action was performed.");
  return value;
}
export async function loadWorkspace(client: ApiClient, ids: Identifiers, signal?: AbortSignal, explicitFindings = false): Promise<Resources> {
  if (!ids.case_id) return emptyResources();
  const caseId = ids.case_id;
  const caseResource = belongs(await client.get(`/cases/${caseId}`, decodeCase, signal), caseId);
  if (caseResource.deleted_at) throw new ShapeError("The saved case has been deleted. Start a new workspace.");
  const documents = (await listAll(client, `/cases/${caseId}/documents`, decodeDocument, signal)).map(v => belongs(v, caseId)).filter(v => !v.deleted_at);
  const job = ids.analysis_job_id ? belongs(await client.get(`/jobs/${ids.analysis_job_id}`, decodeJob, signal), caseId) : null;
  const findings = job && terminal(job.status) || explicitFindings
    ? (await listAll(client, `/cases/${caseId}/findings`, decodeFinding, signal)).map(v => belongs(v, caseId)).filter(v => !job || v.analysis_job_id === job.job_id && (job.result?.finding_ids.includes(v.finding_id) ?? true)) : [];
  if (job?.result && terminal(job.status) && job.result.finding_ids.some(id => !findings.some(f => f.finding_id === id))) throw new ShapeError("The completed analysis references findings that were not returned. Refresh or ask the backend owner to reconcile the result.");
  const selectedId = ids.selected_finding_id ?? findings[0]?.finding_id;
  if (ids.selected_finding_id && !findings.some(f => f.finding_id === selectedId)) throw new ShapeError("The saved finding is absent from the authoritative analysis. Clear the workspace identifiers and reopen the case.");
  const challenge = ids.challenge_id ? belongs(await client.get(`/challenges/${ids.challenge_id}`, decodeChallenge, signal), caseId) : null;
  const simulation = ids.simulation_id ? belongs(await client.get(`/simulations/${ids.simulation_id}`, decodeSimulation, signal), caseId) : null;
  const repair = ids.repair_proposal_id ? belongs(await client.get(`/repair-proposals/${ids.repair_proposal_id}`, decodeRepair, signal), caseId) : null;
  for (const value of [challenge, simulation, repair]) if (value && value.finding_id !== selectedId) throw new ShapeError("A saved downstream resource refers to a different finding. Reconcile the selection before continuing.");
  if (repair && simulation && repair.simulation_id !== simulation.simulation_id) throw new ShapeError("The repair references a different simulation. Reconcile before reviewing.");
  const reviews = repair ? (await listAll(client, `/cases/${caseId}/reviews`, decodeReview, signal)).map(v => belongs(v, caseId)) : [];
  const audit = repair ? (await listAll(client, `/cases/${caseId}/audit`, decodeAudit, signal)).map(v => belongs(v, caseId)) : [];
  const [challengeHistory, simulationHistory] = findings.length ? await Promise.all([
    listAll(client, `/cases/${caseId}/challenges`, decodeChallenge, signal),
    listAll(client, `/cases/${caseId}/simulations`, decodeSimulation, signal),
  ]) : [[], []];
  for (const item of [...challengeHistory, ...simulationHistory]) belongs(item, caseId);
  return { caseResource, documents, job, findings, challenge, simulation, repair, reviews, audit, challengeHistory, simulationHistory };
}

// Recover downstream identifiers from authorized server lists when a case is
// reopened from history, rather than relying on a prior tab's saved IDs.
export async function restoreCaseResources(client: ApiClient, ids: Identifiers, signal?: AbortSignal): Promise<{ ids: Identifiers; resources: Resources }> {
  const base = await loadWorkspace(client, ids, signal);
  const finding = base.findings[0];
  if (!ids.case_id || !finding) return { ids, resources: base };
  const caseId = ids.case_id;
  const newest = <T extends { created_at: string }>(items: T[]): T | undefined => [...items].sort((a,b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
  const [challenges, simulations, repairs] = await Promise.all([
    Promise.resolve(base.challengeHistory ?? []),
    Promise.resolve(base.simulationHistory ?? []),
    listAll(client, `/findings/${finding.finding_id}/repair-proposals`, decodeRepair, signal),
  ]);
  for (const item of [...challenges, ...simulations, ...repairs]) belongs(item, caseId);
  if (repairs.some(item => item.finding_id !== finding.finding_id)) throw new ShapeError("Repair history refers to a different finding.");
  const repair = newest(repairs);
  const simulation = repair ? simulations.find(item => item.simulation_id === repair.simulation_id) : newest(simulations.filter(item => item.finding_id === finding.finding_id));
  const challenge = newest(challenges.filter(item => item.finding_id === finding.finding_id));
  const recovered = { ...ids, selected_finding_id: finding.finding_id, challenge_id: challenge?.challenge_id ?? null,
    simulation_id: repair?.simulation_id ?? simulation?.simulation_id ?? null, repair_proposal_id: repair?.repair_proposal_id ?? null };
  return { ids: recovered, resources: await loadWorkspace(client, recovered, signal) };
}
