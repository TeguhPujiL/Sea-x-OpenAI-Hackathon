import type { ApiClient, PreparedRequest } from "./api";
import { decodeSimulation, ShapeError, type FindingResource, type SimulationResource } from "./contracts";
import type { Resources } from "./workflow";
import { vendorAssessment, documentationRisk, activeConcern } from "./vendorAssessmentData";

export function simulationSupport(finding: FindingResource) {
  const other = /\b(?:warranty|arithmetic|delivery|order|hps|estimate|tax|vat)\b/i.test(finding.title);
  const memory = /\b(?:ram|memory)\b/i.test(finding.title + " " + finding.summary);
  return memory && !other
    ? { supported: true, reason: "RAM-based supplier eligibility using the selected versioned dataset." }
    : { supported: false, reason: "The RAM calculation does not apply to this point. Use its finding-based what-if draft and the available evidence checks instead." };
}

export function vendorWorkflow(resources: Resources) {
  const assessment = vendorAssessment(resources);
  const challenges = [...new Map([...(resources.challengeHistory ?? []), ...(resources.challenge ? [resources.challenge] : [])]
    .filter(c => c.case_id === resources.caseResource?.case_id).map(c => [c.challenge_id, c])).values()];
  const simulations = [...new Map([...(resources.simulationHistory ?? []), ...(resources.simulation ? [resources.simulation] : [])]
    .filter(s => s.case_id === resources.caseResource?.case_id).map(s => [s.simulation_id, s])).values()];
  const latest = <T extends { created_at: string }>(values: T[]) => [...values].sort((a,b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const point = (finding: FindingResource, shared: boolean) => ({ finding, shared, support: simulationSupport(finding),
    canChallenge: assessment.canChallenge(finding),
    challenges: latest(challenges.filter(c => c.finding_id === finding.finding_id)),
    simulations: latest(simulations.filter(s => s.finding_id === finding.finding_id)) });
  const vendors = assessment.vendors.map(vendor => ({ ...vendor, packages: vendor.packages.map(pack => ({ ...pack,
    points: pack.challengePoints.map(f => point(f, pack.sharedFindings.some(s => s.finding_id === f.finding_id))) })) }));
  const assigned = new Set(vendors.flatMap(v => v.packages.flatMap(p => p.points.map(point => point.finding.finding_id))));
  const unassigned = assessment.summary.findings.filter(f => activeConcern(f) && !assigned.has(f.finding_id));
  const groups = [...vendors, ...(unassigned.length ? [{ id: "case-points", label: "Other case points",
    risk: documentationRisk(false, !!resources.job?.result, [], unassigned),
    packages: [{ source: "unassigned", points: unassigned.map(finding => point(finding, true)) }] }] : [])];
  return { assessment, vendors, groups, challenges, simulations };
}

export interface SimulationParameters { baseline: number; alternative: number; version: string }
export function prepareVendorSimulationBatch(client: ApiClient, resources: Resources, findingIds: string[], parameters: SimulationParameters,
  onResult: (value: SimulationResource, completed: number, total: number) => void): PreparedRequest<SimulationResource[]> {
  const { baseline, alternative, version } = parameters;
  if (!Number.isSafeInteger(baseline) || baseline < 1 || !Number.isSafeInteger(alternative) || alternative < 1 || !version.trim()) {
    throw new Error("Provide positive integer RAM thresholds and a supplier data version.");
  }
  const workflow = vendorWorkflow(resources);
  const allowedIds = new Set(workflow.groups.flatMap(v => v.packages.flatMap(p => p.points.map(point => point.finding.finding_id))));
  const ids = [...new Set(findingIds)];
  if (!ids.length) throw new Error("Select at least one supported challenged point.");
  const requests = ids.map(id => {
    const finding = resources.findings.find(f => f.finding_id === id);
    if (!allowedIds.has(id) || !finding || !workflow.assessment.canChallenge(finding) || !simulationSupport(finding).supported
      || !workflow.challenges.some(c => c.finding_id === id && c.status !== "CLOSED")) {
      throw new ShapeError("Each simulation needs a current verified RAM finding and a recorded active challenge in this case.");
    }
    return { id, request: client.prepare("POST", `/cases/${resources.caseResource!.case_id}/simulations`, decodeSimulation,
      { status: 201, body: { finding_id: id, baseline: { minimum_ram_gb: baseline }, alternative: { minimum_ram_gb: alternative }, supplier_data_version: version.trim() } }) };
  });
  const completed: SimulationResource[] = [];
  // execute() retains this prepared object on an interrupted response. Earlier
  // successes are skipped; the uncertain request keeps its original key/body.
  return { method: "POST", path: `/cases/${resources.caseResource!.case_id}/simulations`, async send(signal) {
    for (let index = completed.length; index < requests.length; index++) {
      const { id, request } = requests[index];
      const value = await request.send(signal);
      if (value.case_id !== resources.caseResource!.case_id || value.finding_id !== id) throw new ShapeError("Cross-case or mismatched batch simulation rejected.");
      completed.push(value); onResult(value, completed.length, requests.length);
    }
    return completed;
  } };
}
