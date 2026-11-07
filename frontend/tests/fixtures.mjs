// SYNTHETIC TEST FIXTURES ONLY. Never imported by frontend/src or production builds.
export const IDs = { case: "11111111-1111-4111-8111-111111111111", tor: "33333333-3333-4333-8333-333333333333", spec: "22222222-2222-4222-8222-222222222222", job: "44444444-4444-4444-8444-444444444444", retry: "44444444-4444-4444-8444-555555555555", finding: "77777777-7777-4777-8777-777777777777", challenge: "88888888-8888-4888-8888-888888888888", simulation: "99999999-9999-4999-8999-999999999999", repair: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", review: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", audit: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", actor: "dddddddd-dddd-4ddd-8ddd-dddddddddddd", ai: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee" };
export const timestamp = "2026-11-07T03:00:00Z";
export const meta = { request_id: "req_frontend_test", timestamp, api_version: "v1" };
export const envelope = data => ({ success: true, data, error: null, meta });
export const errorEnvelope = (code, message, retryable = false, details = []) => ({ success: false, data: null, error: { code, message, details, retryable }, meta });
export const caseResource = () => ({ case_id: IDs.case, case_number: "TEST-2026-001", title: "Synthetic frontend integration test", category: "IT_EQUIPMENT", description: "TEST FIXTURE ONLY", quantity: 50, budget_ceiling_idr: 900000000, currency: "IDR", case_status: "DRAFT", assurance_status: "ACTION_REQUIRED", version: 1, created_at: timestamp, updated_at: timestamp, deleted_at: null });
export const documentResource = (type = "TOR") => ({ document_id: type === "TOR" ? IDs.tor : IDs.spec, case_id: IDs.case, filename: type === "TOR" ? "test-tor.pdf" : "test-spec.pdf", document_type: type, description: null, mime_type: "application/pdf", size_bytes: 120, sha256: "a".repeat(64), page_count: 3, processing_status: "COMPLETED", version: 1, uploaded_at: timestamp, deleted_at: null });
export const jobResource = (status = "COMPLETED", clean = false) => ({ job_id: IDs.job, case_id: IDs.case, job_type: "DOCUMENT_ANALYSIS", status, progress_percent: 100, ai_execution: status === "COMPLETED" || status === "NEEDS_REVIEW" ? { execution_id: IDs.ai, provider: "TEST_FIXTURE", model: "synthetic-test-model", operation: "EXTRACT_AND_COMPARE", prompt_version: "frontend-test-v1", input_document_ids: [IDs.tor, IDs.spec], schema_valid: true, evidence_validation_passed: status === "COMPLETED", evidence_checks: { checked: 2, passed: status === "COMPLETED" ? 2 : 1, failed: status === "COMPLETED" ? 0 : 1 }, latency_ms: 10, usage: null } : null, result: ["COMPLETED", "NEEDS_REVIEW"].includes(status) ? { finding_ids: clean ? [] : [IDs.finding], requirement_count: 2 } : null, warnings: status === "NEEDS_REVIEW" ? [{ code: "EVIDENCE_EXCERPT_NOT_FOUND", message: "TEST: excerpt could not be verified", document_id: IDs.spec, page_number: 2 }] : [], error: status === "FAILED" ? { code: "AI_PROVIDER_TIMEOUT", message: "TEST: provider timeout", retryable: true } : null, created_at: timestamp, started_at: status === "QUEUED" ? null : timestamp, completed_at: ["COMPLETED", "FAILED", "NEEDS_REVIEW"].includes(status) ? timestamp : null });
export const findingResource = () => ({ finding_id: IDs.finding, case_id: IDs.case, analysis_job_id: IDs.job, ai_execution_id: IDs.ai, type: "REQUIREMENT_CONTRADICTION", severity: "HIGH", status: "OPEN", title: "Conflicting minimum RAM requirements", summary: "The TOR specifies 16 GB while the technical specification requires 32 GB.", confidence: .96, evidence_status: "VERIFIED", evidence: [{ document_id: IDs.tor, page_number: 2, excerpt: "Minimum RAM: 16 GB", verification_status: "VERIFIED" }, { document_id: IDs.spec, page_number: 2, excerpt: "Minimum RAM: 32 GB", verification_status: "VERIFIED" }], assignee_id: null, resolution_note: null, version: 1, created_at: timestamp, updated_at: timestamp });
export const challengeResource = () => ({ challenge_id: IDs.challenge, case_id: IDs.case, finding_id: IDs.finding, status: "DRAFT", question: "What documented workload supports the higher RAM threshold?", risk_rationale: "An unexplained requirement may reduce eligible competition.", requested_evidence: ["TECHNICAL_JUSTIFICATION", "MARKET_COMPARISON"], ai_execution_id: IDs.ai, human_edits: false, version: 1, created_at: timestamp, updated_at: timestamp });
export const simulationResource = () => ({ simulation_id: IDs.simulation, case_id: IDs.case, finding_id: IDs.finding, engine_version: "supplier-eligibility-v1", input_snapshot: { quantity: 50, baseline: { minimum_ram_gb: 32 }, alternative: { minimum_ram_gb: 16 }, suppliers: [{ supplier_ref: "SYN-A", ram_gb: 16, unit_price_idr: 13200000 }, { supplier_ref: "SYN-B", ram_gb: 16, unit_price_idr: 13800000 }, { supplier_ref: "SYN-C", ram_gb: 32, unit_price_idr: 16500000 }] }, result: { baseline: { eligible_supplier_count: 1, lowest_total_offer_idr: 825000000 }, alternative: { eligible_supplier_count: 3, lowest_total_offer_idr: 660000000 }, delta: { eligible_supplier_count: 2, lowest_total_offer_idr: -165000000 } }, interpretation: "TEST FIXTURE: synthetic eligibility expands. Not proof of actual savings or loss.", created_at: timestamp });
export const repairResource = () => ({ repair_proposal_id: IDs.repair, case_id: IDs.case, finding_id: IDs.finding, status: "DRAFT", action_type: "REVISE_REQUIREMENT", before_text: "Minimum RAM: 32 GB", proposed_text: "Minimum RAM: 16 GB, unless workload evidence supports a higher threshold.", justification: "Resolve the contradiction and document the operational need.", simulation_id: IDs.simulation, ai_execution_id: IDs.ai, human_edits: false, version: 1, created_at: timestamp, updated_at: timestamp });
export const reviewResource = () => ({ review_id: IDs.review, case_id: IDs.case, repair_proposal_id: IDs.repair, decision: "APPROVE_DRAFT", decision_reason: "The documented revision resolves the contradiction.", review_status: "COMPLETED", reviewer: { actor_id: IDs.actor, display_name: "Synthetic test reviewer", role: "REVIEWER" }, assurance_status_after: "REVIEW_COMPLETED", created_at: timestamp });
export const auditResource = () => ({ event_id: IDs.audit, case_id: IDs.case, event_type: "REVIEW_COMPLETED", actor: reviewResource().reviewer, resource: { type: "review", id: IDs.review, version: 1 }, occurred_at: timestamp, request_id: meta.request_id, details: { decision: "APPROVE_DRAFT", assurance_status_after: "REVIEW_COMPLETED" }, previous_hash: null, event_hash: "test-only-event-hash" });
export const page = items => ({ items, pagination: { limit: 50, offset: 0, total: items.length } });
export function fixtureBackend() {
  const state = { caseResource: null, documents: [], job: null, finding: null, challenge: null, simulation: null, repair: null, reviews: [], audit: [], polls: 0, mode: "findings", conflict: false, requests: [], idempotency: new Map() };
  const fetcher = async (input, init = {}) => {
    const url = new URL(String(input), "http://fixture.test"); const path = url.pathname.replace(/^\/api\/v1/, ""); const method = init.method ?? "GET";
    const headers = new Headers(init.headers); const key = headers.get("Idempotency-Key");
    const body = init.body instanceof FormData ? init.body : init.body ? JSON.parse(init.body) : null;
    state.requests.push({ method, path, body, key });
    const ok = (data, status = 200) => Response.json(envelope(data), { status });
    const fail = (status, code, message, retryable = false, details = []) => Response.json(errorEnvelope(code, message, retryable, details), { status });
    const required = method === "POST" && (path === "/cases" || /\/(documents|analyses|simulations|repair-proposals|reviews)$/.test(path));
    if (required && !key) return fail(400, "VALIDATION_ERROR", "Missing idempotency key");
    if (method === "GET" && path === "/health") return ok({ status: "ok", demo_mode: true });
    if (method === "POST" && path === "/cases") { state.caseResource = { ...caseResource(), ...body }; return ok(state.caseResource, 201); }
    if (method === "GET" && path === `/cases/${IDs.case}`) return state.caseResource ? ok(state.caseResource) : fail(404, "RESOURCE_NOT_FOUND", "No test case");
    if (method === "POST" && path.endsWith("/documents")) {
      if (!(body instanceof FormData) || !body.get("file") || !body.get("document_type")) return fail(400, "VALIDATION_ERROR", "Missing multipart fields");
      if (body.get("file").name.includes("reject")) return fail(422, "PDF_EXTRACTION_FAILED", "TEST: unusable PDF text", false, [{ field: "file", reason: "No usable text" }]);
      const doc = documentResource(body.get("document_type")); state.documents.push(doc); return ok(doc, 201);
    }
    if (method === "GET" && path.endsWith("/documents")) return ok(page(state.documents));
    if (method === "GET" && path.endsWith("/jobs")) return ok(page(state.job ? [state.job] : []));
    if (method === "POST" && (path.endsWith("/analyses") || path.endsWith("/retries"))) { state.job = jobResource("QUEUED"); state.polls = 0; state.caseResource.case_status = "UNDER_ASSESSMENT"; return ok(state.job, 202); }
    if (method === "GET" && path.startsWith("/jobs/")) {
      state.polls++;
      const status = state.polls < 2 ? "PROCESSING" : state.mode === "failed" ? "FAILED" : state.mode === "warning" ? "NEEDS_REVIEW" : "COMPLETED";
      state.job = jobResource(status, state.mode === "clean"); state.finding = state.job.result?.finding_ids.length ? findingResource() : null; return ok(state.job);
    }
    if (method === "GET" && path.endsWith("/findings")) return ok(page(state.finding ? [state.finding] : []));
    if (method === "POST" && path.endsWith("/challenges")) { state.challenge = challengeResource(); return ok(state.challenge, 201); }
    if (method === "GET" && path.startsWith("/challenges/")) return ok(state.challenge);
    if (method === "POST" && path.endsWith("/simulations")) { state.simulation = simulationResource(); return ok(state.simulation, 201); }
    if (method === "GET" && path.startsWith("/simulations/")) return ok(state.simulation);
    if (method === "POST" && path.endsWith("/repair-proposals")) { state.repair = repairResource(); return ok(state.repair, 201); }
    if (method === "PATCH" && path.startsWith("/repair-proposals/")) {
      if (state.conflict || body.expected_version !== state.repair.version) { state.conflict = false; state.repair.version++; state.repair.proposed_text = "Newer server text for reconciliation."; return fail(409, "VERSION_CONFLICT", "TEST: proposal version changed", false, [{ field: "expected_version", reason: "Refresh the proposal" }]); }
      state.repair = { ...state.repair, ...body, version: state.repair.version + 1, human_edits: true }; delete state.repair.expected_version;
      state.caseResource.version++; return ok(state.repair);
    }
    if (method === "GET" && path.startsWith("/repair-proposals/")) return ok(state.repair);
    if (method === "POST" && path.endsWith("/reviews")) {
      if (body.expected_case_version !== state.caseResource.version) return fail(409, "VERSION_CONFLICT", "TEST: case version changed");
      if (body.reviewer || body.reviewer_actor_id || body.assurance_status_after) return fail(400, "VALIDATION_ERROR", "Client identity rejected");
      if (state.repair?.status !== "SUBMITTED") return fail(409, "INVALID_STATE_TRANSITION", "Submit a real draft");
      const review = { ...reviewResource(), decision: body.decision, decision_reason: body.decision_reason }; state.reviews.push(review); state.audit.push(auditResource()); state.caseResource.version++; state.caseResource.case_status = "REVIEW_COMPLETED"; state.caseResource.assurance_status = review.assurance_status_after; return ok(review, 201);
    }
    if (method === "GET" && path.endsWith("/reviews")) return ok(page(state.reviews));
    if (method === "GET" && path.endsWith("/audit")) return ok(page(state.audit));
    return fail(404, "RESOURCE_NOT_FOUND", `No fixture route: ${method} ${path}`);
  };
  return { state, fetcher };
}
