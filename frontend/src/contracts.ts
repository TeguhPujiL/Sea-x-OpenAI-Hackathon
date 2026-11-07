// Wire names follow API Contract v1.1, Sections 2, 6, 10 and Appendix A.
export const documentTypes = ["TOR", "TECHNICAL_SPECIFICATION", "OWNER_COST_ESTIMATE", "TECHNICAL_JUSTIFICATION", "SUPPLIER_QUOTATION", "WARRANTY_EVIDENCE", "EVALUATION_REPORT", "CONTRACT", "OTHER"] as const;
export const reviewDecisions = ["APPROVE_DRAFT", "REQUEST_REVISION", "REQUEST_EVIDENCE", "REJECT_DRAFT"] as const;
export const repairActions = ["REVISE_REQUIREMENT", "MAINTAIN_WITH_JUSTIFICATION", "REQUEST_MORE_EVIDENCE"] as const;
export type DocumentType = typeof documentTypes[number];
export type ReviewDecision = typeof reviewDecisions[number];
export type RepairAction = typeof repairActions[number];
export type JobStatus = "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED" | "NEEDS_REVIEW";
export type EvidenceStatus = "VERIFIED" | "UNVERIFIED" | "CONFLICTING" | "INSUFFICIENT";
export interface ApiErrorBody { code: string; message: string; details: { field: string; reason: string }[]; retryable: boolean }
export interface ApiMeta { request_id: string; timestamp: string; api_version: "v1" }
export type ApiEnvelope<T> = { success: true; data: T; error: null; meta: ApiMeta } | { success: false; data: null; error: ApiErrorBody; meta: ApiMeta };
export interface CaseResource {
  case_id: string; case_number: string; title: string; category: string; description: string | null;
  quantity: number; budget_ceiling_idr: number; currency: "IDR"; version: number;
  case_status: "DRAFT" | "UNDER_ASSESSMENT" | "UNDER_REVIEW" | "REVIEW_COMPLETED" | "ARCHIVED";
  assurance_status: "ACTION_REQUIRED" | "READY_FOR_REVIEW" | "REVIEW_COMPLETED";
  created_at: string; updated_at: string; deleted_at: string | null;
}
export interface DocumentResource {
  document_id: string; case_id: string; filename: string; document_type: DocumentType; description: string | null;
  mime_type: string; size_bytes: number; sha256: string; page_count: number; processing_status: JobStatus;
  version: number; uploaded_at: string; deleted_at: string | null;
}
export interface AiExecution {
  execution_id: string; provider: string; model: string; operation: string; prompt_version: string;
  input_document_ids: string[]; schema_valid: boolean; evidence_validation_passed: boolean;
  evidence_checks: { checked: number; passed: number; failed: number }; latency_ms: number;
  usage: { input_tokens: number; output_tokens: number } | null;
}
export interface JobResource {
  job_id: string; case_id: string; job_type: string; status: JobStatus; progress_percent: number;
  ai_execution: AiExecution | null; result: { finding_ids: string[]; requirement_count?: number } | null;
  warnings: { code: string; message: string; document_id?: string; page_number?: number }[];
  error: { code: string; message: string; retryable: boolean; details?: ApiErrorBody["details"] } | null;
  created_at: string; started_at: string | null; completed_at: string | null; retry_of_job_id?: string;
}
export interface EvidenceRef { document_id: string; page_number: number; excerpt: string; verification_status: EvidenceStatus }
export interface FindingResource {
  finding_id: string; case_id: string; analysis_job_id: string; ai_execution_id: string; type: string;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"; status: "OPEN" | "UNDER_REVIEW" | "RESOLVED" | "DISMISSED";
  title: string; summary: string; confidence: number; evidence_status: EvidenceStatus; evidence: EvidenceRef[];
  assignee_id: string | null; resolution_note: string | null; version: number; created_at: string; updated_at: string;
}
export interface ChallengeResource {
  challenge_id: string; case_id: string; finding_id: string; status: "DRAFT" | "READY" | "CLOSED";
  question: string; risk_rationale: string; requested_evidence: string[]; ai_execution_id: string;
  human_edits: boolean; version: number; created_at: string; updated_at: string;
}
export interface Metrics { eligible_supplier_count: number; lowest_total_offer_idr: number }
export interface SimulationResource {
  simulation_id: string; case_id: string; finding_id: string; engine_version: string;
  // G07: display this only when returned; never reconstruct response provenance from browser input.
  supplier_data_version?: string;
  input_snapshot: { quantity: number; baseline: { minimum_ram_gb: number }; alternative: { minimum_ram_gb: number }; suppliers: { supplier_ref: string; ram_gb: number; unit_price_idr: number }[] };
  result: { baseline: Metrics; alternative: Metrics; delta: Metrics }; interpretation: string; created_at: string;
}
export interface RepairResource {
  repair_proposal_id: string; case_id: string; finding_id: string; status: "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED" | "WITHDRAWN";
  action_type: RepairAction; before_text: string; proposed_text: string; justification: string;
  simulation_id: string; ai_execution_id: string; human_edits: boolean; version: number; created_at: string; updated_at: string;
}
export interface Actor { actor_id: string; display_name: string; role: string }
export interface ReviewResource {
  review_id: string; case_id: string; repair_proposal_id: string; decision: ReviewDecision; decision_reason: string;
  review_status: "COMPLETED"; reviewer: Actor; assurance_status_after: CaseResource["assurance_status"]; created_at: string;
}
export interface AuditActor { actor_id: string; display_name: string | null; role: string | null }
export interface AuditResource {
  event_id: string; case_id: string; event_type: string; actor: AuditActor; resource: { type: string; id: string; version: number };
  occurred_at: string; request_id: string; details: Record<string, unknown>; previous_hash: string | null; event_hash: string | null;
}
export interface Page<T> { items: T[]; pagination: { limit: number; offset: number; total: number } }
export interface CaseInput { title: string; category: string; description: string; quantity: number; budget_ceiling_idr: number; currency: "IDR" }
export interface SimulationInput { finding_id: string; baseline: { minimum_ram_gb: number }; alternative: { minimum_ram_gb: number }; supplier_data_version: string }

export type Decoder<T> = (value: unknown) => T;
export class ShapeError extends Error { constructor(message: string) { super(message); this.name = "ShapeError"; } }
export function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new ShapeError("Expected a JSON object.");
  return value as Record<string, unknown>;
}
export const uuid = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
const utc = (v: unknown) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}T.*Z$/.test(v) && Number.isFinite(Date.parse(v));
const integer = (v: unknown, min = 0) => Number.isSafeInteger(v) && (v as number) >= min;
const text = (v: unknown) => typeof v === "string";
const bool = (v: unknown) => typeof v === "boolean";
type Check = (value: unknown) => boolean;
const oneOf = (values: readonly string[]): Check => v => typeof v === "string" && values.includes(v);
const nullable = (check: Check): Check => v => v === null || check(v);
const array = (check: Check): Check => v => Array.isArray(v) && v.every(check);
const recordCheck = (checks: Record<string, Check>): Check => value => {
  try { const v = object(value); return Object.entries(checks).every(([key, check]) => check(v[key])); } catch { return false; }
};
const version: Check = v => integer(v, 1);
const statuses = ["QUEUED", "PROCESSING", "COMPLETED", "FAILED", "NEEDS_REVIEW"];
const evidenceStatuses = ["VERIFIED", "UNVERIFIED", "CONFLICTING", "INSUFFICIENT"];
const assurance = oneOf(["ACTION_REQUIRED", "READY_FOR_REVIEW", "REVIEW_COMPLETED"]);
const actor = recordCheck({ actor_id: uuid, display_name: text, role: text });
// Historical audit snapshots may omit names/roles; review identities remain strict.
const auditActor = recordCheck({ actor_id: uuid, display_name: nullable(text), role: nullable(text) });
const metric = (signed: boolean): Check => recordCheck({ eligible_supplier_count: v => Number.isSafeInteger(v) && (signed || (v as number) >= 0), lowest_total_offer_idr: v => Number.isSafeInteger(v) && (signed || (v as number) >= 0) });
function decode<T>(name: string, checks: Record<string, Check>, extra?: (v: Record<string, unknown>) => boolean): Decoder<T> {
  return value => {
    const v = object(value);
    for (const [key, check] of Object.entries(checks)) if (!check(v[key])) throw new ShapeError(`${name}.${key} does not match API Contract v1.1.`);
    if (extra && !extra(v)) throw new ShapeError(`${name} contains an inconsistent status/result combination.`);
    return value as T;
  };
}
const resource = { case_id: uuid, created_at: utc };
const versioned = { ...resource, version, updated_at: utc };
export const decodeCase = decode<CaseResource>("case", { ...versioned, case_number: text, title: text, category: text, description: nullable(text), quantity: v => integer(v, 1), budget_ceiling_idr: v => integer(v), currency: oneOf(["IDR"]), case_status: oneOf(["DRAFT", "UNDER_ASSESSMENT", "UNDER_REVIEW", "REVIEW_COMPLETED", "ARCHIVED"]), assurance_status: assurance, deleted_at: nullable(utc) });
export const decodeDocument = decode<DocumentResource>("document", { document_id: uuid, case_id: uuid, filename: text, document_type: oneOf(documentTypes), description: nullable(text), mime_type: oneOf(["application/pdf"]), size_bytes: v => integer(v, 1), sha256: v => typeof v === "string" && /^[a-f0-9]{64}$/i.test(v), page_count: v => integer(v, 1), processing_status: oneOf(statuses), version, uploaded_at: utc, deleted_at: nullable(utc) });
const nestedError = recordCheck({ code: text, message: text, retryable: bool });
export const decodeJob = decode<JobResource>("job", { ...resource, job_id: uuid, job_type: text, status: oneOf(statuses), progress_percent: v => typeof v === "number" && v >= 0 && v <= 100,
  ai_execution: nullable(recordCheck({ execution_id: uuid, provider: text, model: text, operation: text, prompt_version: text, input_document_ids: array(uuid), schema_valid: bool, evidence_validation_passed: bool, evidence_checks: recordCheck({ checked: v => integer(v), passed: v => integer(v), failed: v => integer(v) }), latency_ms: v => integer(v), usage: nullable(recordCheck({ input_tokens: v => integer(v), output_tokens: v => integer(v) })) })),
  result: nullable(recordCheck({ finding_ids: array(uuid) })), warnings: array(recordCheck({ code: text, message: text })), error: nullable(nestedError), started_at: nullable(utc), completed_at: nullable(utc)
}, v => v.status === "COMPLETED" || v.status === "NEEDS_REVIEW" ? v.result !== null : v.result === null);
export const decodeFinding = decode<FindingResource>("finding", { ...versioned, finding_id: uuid, analysis_job_id: uuid, ai_execution_id: uuid, type: text, severity: oneOf(["LOW", "MEDIUM", "HIGH", "CRITICAL"]), status: oneOf(["OPEN", "UNDER_REVIEW", "RESOLVED", "DISMISSED"]), title: text, summary: text, confidence: v => typeof v === "number" && v >= 0 && v <= 1, evidence_status: oneOf(evidenceStatuses), evidence: array(recordCheck({ document_id: uuid, page_number: v => integer(v, 1), excerpt: text, verification_status: oneOf(evidenceStatuses) })), assignee_id: nullable(uuid), resolution_note: nullable(text) });
export const decodeChallenge = decode<ChallengeResource>("challenge", { ...versioned, challenge_id: uuid, finding_id: uuid, status: oneOf(["DRAFT", "READY", "CLOSED"]), question: text, risk_rationale: text, requested_evidence: array(text), ai_execution_id: uuid, human_edits: bool });
export const decodeSimulation = decode<SimulationResource>("simulation", { ...resource, simulation_id: uuid, finding_id: uuid, engine_version: text, input_snapshot: recordCheck({ quantity: v => integer(v, 1), baseline: recordCheck({ minimum_ram_gb: v => integer(v, 1) }), alternative: recordCheck({ minimum_ram_gb: v => integer(v, 1) }), suppliers: array(recordCheck({ supplier_ref: text, ram_gb: v => integer(v, 1), unit_price_idr: v => integer(v) })) }), result: recordCheck({ baseline: metric(false), alternative: metric(false), delta: metric(true) }), interpretation: text }, v => v.supplier_data_version === undefined || typeof v.supplier_data_version === "string");
export const decodeRepair = decode<RepairResource>("repair", { ...versioned, repair_proposal_id: uuid, finding_id: uuid, status: oneOf(["DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "WITHDRAWN"]), action_type: oneOf(repairActions), before_text: text, proposed_text: text, justification: text, simulation_id: uuid, ai_execution_id: uuid, human_edits: bool });
export const decodeReview = decode<ReviewResource>("review", { ...resource, review_id: uuid, repair_proposal_id: uuid, decision: oneOf(reviewDecisions), decision_reason: text, review_status: oneOf(["COMPLETED"]), reviewer: actor, assurance_status_after: assurance });
export const decodeAudit = decode<AuditResource>("audit", { ...{ case_id: uuid }, event_id: uuid, event_type: text, actor: auditActor, resource: recordCheck({ type: text, id: uuid, version }), occurred_at: utc, request_id: text, details: v => typeof v === "object" && v !== null && !Array.isArray(v), previous_hash: nullable(text), event_hash: nullable(text) });
export function pageDecoder<T>(item: Decoder<T>): Decoder<Page<T>> {
  return value => { const v = object(value); if (!Array.isArray(v.items) || !recordCheck({ limit: version, offset: v => integer(v), total: v => integer(v) })(v.pagination)) throw new ShapeError("Invalid paginated response."); return { items: v.items.map(item), pagination: v.pagination as Page<T>["pagination"] }; };
}
export function decodeEnvelope<T>(value: unknown, dataDecoder: Decoder<T>): ApiEnvelope<T> {
  const v = object(value); const meta = object(v.meta);
  if (typeof v.success !== "boolean" || !text(meta.request_id) || !utc(meta.timestamp) || meta.api_version !== "v1") throw new ShapeError("Invalid canonical API envelope or metadata.");
  if (v.success) { if (v.error !== null || v.data === null || v.data === undefined) throw new ShapeError("Success requires data and a null error."); return { success: true, data: dataDecoder(v.data), error: null, meta: meta as unknown as ApiMeta }; }
  if (v.data !== null || !recordCheck({ code: text, message: text, details: array(recordCheck({ field: text, reason: text })), retryable: bool })(v.error)) throw new ShapeError("Invalid canonical API error.");
  return value as ApiEnvelope<T>;
}

export const decodeDocumentDeleted = decode<{ document_id: string; deleted_at: string }>("deleted_document", { document_id: uuid, deleted_at: utc });
