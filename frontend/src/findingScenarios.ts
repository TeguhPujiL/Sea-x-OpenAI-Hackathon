import type { ApiClient, PreparedRequest } from "./api";
import { object, uuid, ShapeError, type AiExecution } from "./contracts";
import type { Resources } from "./workflow";
import { listAll } from "./resources";
import { vendorWorkflow } from "./vendorWorkflowData";

export interface ScenarioCitation { document_id: string; page_number: number; excerpt: string }
export interface FindingScenario {
  scenario_id: string; case_id: string; finding_id: string; analysis_job_id: string; status: "DRAFT" | "NEEDS_REVIEW";
  title: string; baseline: { description: string; assumptions: string[]; evidence: ScenarioCitation[] };
  alternatives: { title: string; change: string; expected_effect: string; limitations: string[]; evidence: ScenarioCitation[] }[];
  remaining_uncertainties: string[];
  deterministic_checks: { check_type: string; status: "PASS" | "CONCERN" | "UNKNOWN" | "NOT_APPLICABLE"; description: string; observations: Record<string, unknown> }[];
  ai_execution: AiExecution; created_at: string;
}
const texts = (value: unknown): value is string[] => Array.isArray(value) && value.every(v => typeof v === "string");
const text = (value: unknown) => typeof value === "string" && value.trim().length > 0;
const integer = (value: unknown) => Number.isSafeInteger(value) && (value as number) >= 0;
function citations(value: unknown) {
  return Array.isArray(value) && value.length > 0 && value.every(item => {
    const ref = object(item); return uuid(ref.document_id) && Number.isSafeInteger(ref.page_number) && (ref.page_number as number) >= 1 && text(ref.excerpt);
  });
}
export function decodeFindingScenario(value: unknown): FindingScenario {
  try {
    const v = object(value), baseline = object(v.baseline), execution = object(v.ai_execution), checks = object(execution.evidence_checks);
    if (![v.scenario_id, v.case_id, v.finding_id, v.analysis_job_id].every(uuid) || !["DRAFT", "NEEDS_REVIEW"].includes(String(v.status))
      || !text(v.title) || !text(baseline.description) || !texts(baseline.assumptions) || !citations(baseline.evidence)
      || !texts(v.remaining_uncertainties) || !Array.isArray(v.alternatives) || !v.alternatives.length || !v.alternatives.every(item => {
        const a = object(item); return text(a.title) && text(a.change) && text(a.expected_effect) && texts(a.limitations) && citations(a.evidence);
      }) || !Array.isArray(v.deterministic_checks) || !v.deterministic_checks.every(item => {
        const check = object(item); return text(check.check_type) && ["PASS", "CONCERN", "UNKNOWN", "NOT_APPLICABLE"].includes(String(check.status))
          && text(check.description) && object(check.observations);
      }) || !uuid(execution.execution_id) || !text(execution.provider) || !text(execution.model) || !text(execution.operation) || !text(execution.prompt_version)
      || !Array.isArray(execution.input_document_ids) || !execution.input_document_ids.every(uuid)
      || typeof execution.schema_valid !== "boolean" || typeof execution.evidence_validation_passed !== "boolean"
      || ![checks.checked, checks.passed, checks.failed, execution.latency_ms].every(integer)
      || (execution.usage !== null && (!integer(object(execution.usage).input_tokens) || !integer(object(execution.usage).output_tokens)))
      || typeof v.created_at !== "string" || !v.created_at.endsWith("Z") || !Number.isFinite(Date.parse(v.created_at))) {
      throw new ShapeError("Invalid experimental finding-scenario response.");
    }
    return value as FindingScenario;
  } catch { throw new ShapeError("The experimental finding-scenario response is incomplete or invalid. Refresh before continuing."); }
}

export async function loadFindingScenarios(client: ApiClient, caseId: string, signal?: AbortSignal) {
  const values = await listAll(client, `/experimental/cases/${caseId}/finding-simulations`, decodeFindingScenario, signal);
  if (values.some(value => value.case_id !== caseId)) throw new ShapeError("Cross-case finding scenario rejected.");
  return values;
}

export function prepareFindingScenarioBatch(client: ApiClient, resources: Resources, findingIds: string[], assumptions: string[],
  onResult: (value: FindingScenario, completed: number, total: number) => void): PreparedRequest<FindingScenario[]> {
  const workflow = vendorWorkflow(resources), caseResource = resources.caseResource;
  if (!caseResource || !resources.job?.result) throw new Error("Load a current case and usable assessment first.");
  const ids = [...new Set(findingIds)];
  if (!ids.length) throw new Error("Choose at least one challenged finding.");
  const requests = ids.map(id => {
    const finding = resources.findings.find(f => f.finding_id === id);
    if (!finding || !workflow.assessment.canChallenge(finding) || !workflow.challenges.some(c => c.finding_id === id && c.status !== "CLOSED")) {
      throw new ShapeError("Each scenario needs a current verified finding with a recorded active challenge.");
    }
    return { findingId: id, request: client.prepare("POST", `/experimental/cases/${caseResource.case_id}/finding-simulations`, decodeFindingScenario,
      { status: 201, body: { finding_id: id, expected_case_version: caseResource.version, expected_finding_version: finding.version, assumptions } }) };
  });
  const completed: FindingScenario[] = [];
  return { method: "POST", path: `/experimental/cases/${caseResource.case_id}/finding-simulations`, async send(signal) {
    for (let index = completed.length; index < requests.length; index++) {
      const task = requests[index], value = await task.request.send(signal);
      if (value.case_id !== caseResource.case_id || value.finding_id !== task.findingId || value.analysis_job_id !== resources.job!.job_id) {
        throw new ShapeError("A generated scenario references another case, finding or analysis.");
      }
      completed.push(value); onResult(value, completed.length, requests.length);
    }
    return completed;
  } };
}
