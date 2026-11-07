import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createClient, RequestError, TransportError, readConfig, normalize, requiresIdempotency } from "../src/api.ts";
import { decodeCase, decodeDocument, decodeJob, decodeFinding, decodeChallenge, decodeSimulation, decodeRepair, decodeReview, decodeAudit, decodeEnvelope, ShapeError, uuid } from "../src/contracts.ts";
import { emptyIds, emptyResources, saveIds, readIds, storageKey, hasRequiredDocuments, pollJob, cleanCase, canReview, recoveredStep } from "../src/workflow.ts";
import { loadWorkspace, listAll } from "../src/resources.ts";
import { WorkspaceView, ErrorPanel } from "../src/WorkspaceView.tsx";
import { IDs, envelope, errorEnvelope, meta, caseResource, documentResource, jobResource, findingResource, challengeResource, simulationResource, repairResource, reviewResource, auditResource, fixtureBackend, page } from "./fixtures.mjs";

const config = { baseUrl: "/api/v1", development: true };
const noop = () => {};
const view = (overrides = {}) => {
  const props = { resources: emptyResources(), ids: emptyIds(), step: 0, busy: null, restoring: false, pollState: null, error: null, conflict: null, storageWarning: false, demoMode: null, healthMessage: "TEST ONLY", meta: null, proposedText: "", dirtyDraft: false,
    ...Object.fromEntries(["setProposedText", "onStep", "onRefresh", "onReset", "onResume", "onCreate", "onUpload", "onAnalyze", "onRetryAnalysis", "onResumePolling", "onSelectFinding", "onChallenge", "onSimulate", "onGenerateRepair", "onSaveRepair", "onReview", "onDismissError", "onReconcile"].map(k => [k, noop])), ...overrides };
  return renderToStaticMarkup(React.createElement(WorkspaceView, props));
};
function memoryStorage() { const map = new Map(); return { getItem: key => map.get(key) ?? null, setItem: (key, value) => map.set(key, value), removeItem: key => map.delete(key) }; }
function fullResources() { return { ...emptyResources(), caseResource: caseResource(), documents: [documentResource(), documentResource("TECHNICAL_SPECIFICATION")], job: jobResource(), findings: [findingResource()], challenge: challengeResource(), simulation: simulationResource(), repair: repairResource() }; }
const fullIds = () => ({ case_id: IDs.case, document_ids: [IDs.tor, IDs.spec], analysis_job_id: IDs.job, selected_finding_id: IDs.finding, challenge_id: IDs.challenge, simulation_id: IDs.simulation, repair_proposal_id: IDs.repair });

test("API URL fallback is development-only; production needs explicit configuration", () => {
  assert.equal(readConfig({ DEV: true }).baseUrl, "/api/v1");
  assert.throws(() => readConfig({ DEV: false }), /required/);
  assert.equal(readConfig({ DEV: false, VITE_API_BASE_URL: "/api/v1/" }).baseUrl, "/api/v1");
  for (const url of ["//untrusted.test", "https://user:secret@example.test/api/v1", "/api/v1?key=secret"]) assert.throws(() => readConfig({ VITE_API_BASE_URL: url }));
});
test("request normalization is stable without changing array semantics", () => {
  assert.equal(normalize({ z: 1, a: { c: 2, b: 1 } }), normalize({ a: { b: 1, c: 2 }, z: 1 }));
  assert.notEqual(normalize([1, 2]), normalize([2, 1])); assert.throws(() => normalize({ value: undefined }));
});
test("idempotency applies only to the six contracted POST families", () => {
  for (const path of ["/cases", `/cases/${IDs.case}/documents`, `/cases/${IDs.case}/analyses`, `/cases/${IDs.case}/simulations`, `/findings/${IDs.finding}/repair-proposals`, `/cases/${IDs.case}/reviews`]) assert.equal(requiresIdempotency("POST", path), true);
  for (const path of [`/cases/${IDs.case}/challenges`, `/jobs/${IDs.job}/retries`, `/findings/${IDs.finding}/dismissals`]) assert.equal(requiresIdempotency("POST", path), false);
  assert.equal(requiresIdempotency("PATCH", `/repair-proposals/${IDs.repair}`), false);
});
test("transport retry reuses the captured UUID and normalized payload; new operation gets a new key", async () => {
  const calls = []; let attempts = 0;
  const client = createClient(config, async (url, init) => { calls.push(init); if (++attempts === 1) throw new TypeError("network"); return Response.json(envelope(caseResource()), { status: 201 }); });
  const body = { title: "Original title" }; const request = client.prepare("POST", "/cases", decodeCase, { body, status: 201 });
  assert.ok(uuid(request.idempotencyKey)); body.title = "Changed after preparation";
  await assert.rejects(request.send(), TransportError); await request.send();
  assert.equal(calls[0].headers["Idempotency-Key"], calls[1].headers["Idempotency-Key"]);
  assert.equal(calls[0].body, calls[1].body); assert.equal(JSON.parse(calls[1].body).title, "Original title");
  await assert.rejects(request.send(), /Create a new request/);
  assert.notEqual(client.prepare("POST", "/cases", decodeCase).idempotencyKey, request.idempotencyKey);
});
test("received HTTP errors retain exact details and cannot reuse their request key", async () => {
  const client = createClient(config, async () => Response.json(errorEnvelope("PDF_EXTRACTION_FAILED", "No usable text", false, [{ field: "file", reason: "Textless PDF" }]), { status: 422 }));
  const req = client.prepare("POST", `/cases/${IDs.case}/documents`, decodeDocument);
  await assert.rejects(req.send(), error => error instanceof RequestError && error.status === 422 && error.body.retryable === false && error.body.details[0].reason === "Textless PDF");
  await assert.rejects(req.send(), /Create a new request/);
});
test("interrupted response body is a transport retry with the same key", async () => {
  let attempts = 0; const keys = [];
  const client = createClient(config, async (url, init) => {
    keys.push(init.headers["Idempotency-Key"]);
    if (!attempts++) return { status: 201, json: async () => { throw new TypeError("stream interrupted"); } };
    return Response.json(envelope(caseResource()), { status: 201 });
  });
  const req = client.prepare("POST", "/cases", decodeCase, { status: 201 });
  await assert.rejects(req.send(), TransportError); await req.send(); assert.equal(keys[0], keys[1]);
});
test("rejected PDF upload keeps the server validation code and creates no document", async () => {
  const backend = fixtureBackend(); const client = createClient(config, backend.fetcher);
  const form = new FormData(); form.append("file", new File(["%PDF-test"], "reject.pdf", { type: "application/pdf" })); form.append("document_type", "TOR");
  await assert.rejects(client.prepare("POST", `/cases/${IDs.case}/documents`, decodeDocument, { status: 201, multipart: form }).send(), error => error instanceof RequestError && error.body.code === "PDF_EXTRACTION_FAILED" && error.body.details[0].field === "file");
  assert.equal(backend.state.documents.length, 0); assert.equal(backend.state.finding, null);
});
test("rejects unexpected success shape, envelope, HTTP status, and non-JSON responses", async () => {
  assert.throws(() => decodeEnvelope(envelope({ case_id: IDs.case }), decodeCase), ShapeError);
  assert.throws(() => decodeEnvelope({ ...envelope(caseResource()), meta: {} }, decodeCase), ShapeError);
  assert.throws(() => decodeEnvelope({ ...envelope(caseResource()), error: { message: "wrong" } }, decodeCase), ShapeError);
  const wrongStatus = createClient(config, async () => Response.json(envelope(caseResource()), { status: 200 }));
  await assert.rejects(wrongStatus.prepare("POST", "/cases", decodeCase, { status: 201 }).send(), /Expected HTTP 201/);
  await assert.rejects(createClient(config, async () => new Response("<html>fallback</html>")).get("/cases", decodeCase), /non-JSON/);
});
test("multipart metadata and bytes are captured for upload transport retry", async () => {
  const backend = fixtureBackend(); let tries = 0; const calls = [];
  const client = createClient(config, async (url, init) => { calls.push(init); if (!tries++) throw new TypeError("lost connection"); return backend.fetcher(url, init); });
  const form = new FormData(); form.append("file", new File(["%PDF-1.7 test"], "source.pdf", { type: "application/pdf" })); form.append("document_type", "TOR");
  const req = client.prepare("POST", `/cases/${IDs.case}/documents`, decodeDocument, { multipart: form, status: 201 }); form.set("document_type", "OTHER");
  await assert.rejects(req.send(), TransportError); const doc = await req.send();
  assert.equal(doc.document_type, "TOR"); assert.equal(calls[0].body.get("document_type"), "TOR"); assert.equal(await calls[1].body.get("file").text(), "%PDF-1.7 test");
  assert.equal(calls[0].headers["Content-Type"], undefined); assert.equal(calls[0].headers["Idempotency-Key"], calls[1].headers["Idempotency-Key"]);
});
for (const ending of ["COMPLETED", "FAILED", "NEEDS_REVIEW"]) {
  test(`polling stops on ${ending}, never on 100 percent progress, and caps backoff at 5 seconds`, async () => {
    const delays = []; const states = ["QUEUED", "PROCESSING", "PROCESSING", "PROCESSING", "PROCESSING", ending]; const seen = [];
    const result = await pollJob(async () => jobResource(states.shift()), job => seen.push(job.status), new AbortController().signal, async ms => { delays.push(ms); });
    assert.deepEqual(delays, [1000, 2000, 4000, 5000, 5000, 5000]); assert.equal(result.status, ending); assert.equal(seen.length, 6);
  });
}
test("aborting polling stops further network reads", async () => {
  const controller = new AbortController(); let reads = 0;
  await assert.rejects(pollJob(async () => { reads++; return jobResource("PROCESSING"); }, noop, controller.signal, async () => { controller.abort(new Error("stopped")); throw controller.signal.reason; }), /stopped/);
  assert.equal(reads, 0);
});
test("Analyze stays disabled until both nondeleted usable comparison documents exist", () => {
  assert.equal(hasRequiredDocuments([]), false); assert.equal(hasRequiredDocuments([documentResource()]), false);
  assert.equal(hasRequiredDocuments([documentResource(), documentResource("TECHNICAL_SPECIFICATION")]), true);
  assert.equal(hasRequiredDocuments([documentResource(), { ...documentResource("TECHNICAL_SPECIFICATION"), processing_status: "FAILED" }]), false);
  const html = view({ step: 1 }); assert.match(html, /disabled="">Analyze documents/);
});
test("processing job refresh never fetches findings; explicit user refresh may do so", async () => {
  const paths = []; const client = createClient(config, async input => { const path = new URL(input, "http://test").pathname; paths.push(path); return Response.json(envelope(path.includes("/jobs/") ? jobResource("PROCESSING") : path.endsWith("/documents") || path.endsWith("/findings") ? page([]) : caseResource())); });
  const ids = { ...emptyIds(), case_id: IDs.case, analysis_job_id: IDs.job };
  await loadWorkspace(client, ids); assert.equal(paths.some(p => p.endsWith("/findings")), false);
  await loadWorkspace(client, ids, undefined, true); assert.equal(paths.some(p => p.endsWith("/findings")), true);
});
test("empty finding_ids renders the clean state and blocks fabricated repair/review paths", () => {
  const resources = { ...emptyResources(), caseResource: caseResource(), job: jobResource("COMPLETED", true) };
  assert.equal(cleanCase(resources.job), true); assert.equal(canReview(resources), false); assert.equal(recoveredStep(resources), 5);
  const html = view({ resources, step: 5 }); assert.match(html, /No integrity findings detected/); assert.match(html, /Clean-case completion pending contract decision/);
  assert.doesNotMatch(html, /<option value="APPROVE_CASE"/); assert.doesNotMatch(html, /Record internal review<\/button>/); assert.doesNotMatch(html, /Generate draft/);
});
test("finding evidence displays the excerpt, UUID, one-based page and verification state", () => {
  const resources = fullResources(); const html = view({ resources, ids: fullIds(), step: 2 });
  assert.match(html, /Minimum RAM: 16 GB/); assert.match(html, new RegExp(IDs.tor)); assert.match(html, /Page 2/); assert.match(html, /VERIFIED|verified/);
  assert.throws(() => decodeFinding({ ...findingResource(), evidence: [{ ...findingResource().evidence[0], page_number: 0 }] }), ShapeError);
});
test("empty findings never hide real NEEDS_REVIEW processing warnings after recovery", () => {
  const resources = { ...emptyResources(), caseResource: caseResource(), job: jobResource("NEEDS_REVIEW", true) };
  assert.equal(recoveredStep(resources), 1);
  const html = view({ resources, step: 5 });
  assert.match(html, /No integrity findings detected/); assert.match(html, /EVIDENCE_EXCERPT_NOT_FOUND/); assert.match(html, /Analysis processing needs review/);
});
test("out-of-range evidence reference gets a visible warning", () => {
  const resources = fullResources(); resources.findings[0].evidence[0].page_number = 99;
  assert.match(view({ resources, ids: fullIds(), step: 2 }), /page reference could not be checked/);
});
test("golden simulation shows backend numbers, signed IDR delta, provenance gap and disclaimer", () => {
  const value = decodeSimulation(simulationResource()); assert.equal(value.result.delta.lowest_total_offer_idr, -165000000);
  const html = view({ resources: fullResources(), ids: fullIds(), step: 3 });
  for (const text of ["825,000,000", "660,000,000", "165,000,000", "supplier-eligibility-v1", "Frozen input snapshot", "not proof of actual savings", "contract gap G07"]) assert.ok(html.includes(text), text);
  const invalid = simulationResource(); invalid.result.baseline.lowest_total_offer_idr = -1; assert.throws(() => decodeSimulation(invalid), ShapeError);
});
test("submitted repair is read-only and cannot be saved again", () => {
  const resources = fullResources(); resources.repair.status = "SUBMITTED";
  const html = view({ resources, ids: fullIds(), step: 4, proposedText: resources.repair.proposed_text });
  assert.match(html, /<textarea[^>]*disabled=""/); assert.doesNotMatch(html, />Save draft<\/button>/); assert.doesNotMatch(html, />Submit draft for review/);
});
test("version conflict keeps original error precision and offers explicit reconciliation with enabled refresh", () => {
  const resources = fullResources(); resources.repair.version = 2;
  const error = new RequestError(409, { code: "VERSION_CONFLICT", message: "Proposal changed", retryable: false, details: [{ field: "expected_version", reason: "Stale" }] }, "req_conflict");
  const html = view({ resources, ids: fullIds(), step: 4, error, conflict: { localText: "Unsaved local text", expectedVersion: 1, refreshed: false } });
  for (const text of ["VERSION_CONFLICT", "Proposal changed", "expected_version", "Stale", "false", "Unsaved local text", "No write was replayed"]) assert.ok(html.includes(text));
  assert.match(html, /<button class="secondary">Refresh resources/); assert.match(html, /disabled="">Use server version/);
});
test("NEEDS_REVIEW warnings and FAILED retryable are displayed separately from severity", () => {
  const resources = fullResources(); resources.job = jobResource("NEEDS_REVIEW");
  assert.match(view({ resources, ids: fullIds(), step: 1 }), /EVIDENCE_EXCERPT_NOT_FOUND/);
  resources.job = jobResource("FAILED"); const html = view({ resources, ids: fullIds(), step: 1 }); assert.match(html, /AI_PROVIDER_TIMEOUT/); assert.match(html, /Retryable: true/);
});
test("storage allowlist excludes case versions, step, contents, and reviewer identity", () => {
  const storage = memoryStorage(); saveIds(storage, { ...fullIds(), current_step: 5, case_version: 99, api_key: "sensitive", reviewer: reviewResource().reviewer, proposed_text: "confidential" });
  const raw = storage.getItem(storageKey); assert.deepEqual(Object.keys(JSON.parse(raw)).sort(), Object.keys(emptyIds()).sort());
  for (const text of ["sensitive", "confidential", "reviewer", "case_version", "current_step"]) assert.equal(raw.includes(text), false);
  assert.deepEqual(readIds(storage), fullIds()); storage.setItem(storageKey, "broken json"); assert.deepEqual(readIds(storage), emptyIds());
});
test("storage failures are contained and invalid saved identifiers are ignored", () => {
  assert.equal(saveIds({ setItem() { throw new Error("denied"); } }, fullIds()), false);
  const storage = memoryStorage(); storage.setItem(storageKey, JSON.stringify({ ...fullIds(), simulation_id: "invalid" })); assert.equal(readIds(storage).simulation_id, null);
});
test("pagination reads every page and rejects truncated pages", async () => {
  let calls = 0; const client = createClient(config, async () => Response.json(envelope({ items: calls++ ? [documentResource("TECHNICAL_SPECIFICATION")] : [documentResource()], pagination: { limit: 1, offset: calls - 1, total: 2 } })));
  assert.equal((await listAll(client, `/cases/${IDs.case}/documents`, decodeDocument)).length, 2);
  const truncated = createClient(config, async () => Response.json(envelope({ items: [], pagination: { limit: 50, offset: 0, total: 2 } })));
  await assert.rejects(listAll(truncated, "/documents", decodeDocument), /incomplete page/);
});
test("authoritative recovery rejects cross-case resources", async () => {
  const client = createClient(config, async () => Response.json(envelope({ ...caseResource(), case_id: IDs.actor })));
  await assert.rejects(loadWorkspace(client, fullIds()), /does not belong/);
});
test("all six steps, labelled controls, skip link and current-step semantics are rendered", () => {
  const html = view();
  for (const step of ["Upload", "Assess", "Challenge", "Simulate", "Repair", "Assure"]) assert.ok(html.includes(step));
  assert.match(html, /aria-current="step"/); assert.match(html, /Skip to workspace/); assert.match(html, /<label class="field"><span>Case title/);
  assert.match(html, /aria-live="polite"/); assert.match(html, /Synthetic data/); assert.match(html, /statutory procurement approval/);
});
test("recorded review is immutable UI and preserves server reviewer/audit provenance", () => {
  const resources = fullResources(); resources.repair.status = "APPROVED"; resources.reviews = [reviewResource()]; resources.audit = [auditResource()];
  const html = view({ resources, ids: fullIds(), step: 5 }); assert.match(html, /Synthetic test reviewer/); assert.match(html, new RegExp(IDs.actor)); assert.match(html, /Audit timeline/); assert.match(html, /test-only-event-hash/);
  assert.doesNotMatch(html, /<select name="decision"/); assert.doesNotMatch(html, /Record internal review<\/button>/); assert.equal(canReview(resources), false);
});
test("complete synthetic contract journey, stale repair, and authoritative refresh recovery", async () => {
  const backend = fixtureBackend(); const client = createClient(config, backend.fetcher);
  const c = await client.prepare("POST", "/cases", decodeCase, { status: 201, body: { title: "Synthetic frontend integration test", category: "IT_EQUIPMENT", description: "TEST ONLY", quantity: 50, budget_ceiling_idr: 900000000, currency: "IDR" } }).send();
  for (const type of ["TOR", "TECHNICAL_SPECIFICATION"]) {
    const form = new FormData(); form.append("file", new File(["%PDF-test"], "fixture.pdf", { type: "application/pdf" })); form.append("document_type", type);
    await client.prepare("POST", `/cases/${c.case_id}/documents`, decodeDocument, { status: 201, multipart: form }).send();
  }
  const job = await client.prepare("POST", `/cases/${IDs.case}/analyses`, decodeJob, { status: 202, body: { document_ids: [IDs.tor, IDs.spec], analysis_types: ["REQUIREMENT_EXTRACTION", "CONTRADICTION_DETECTION"], force_reanalysis: false } }).send();
  assert.equal(job.status, "QUEUED"); await pollJob(() => client.get(`/jobs/${job.job_id}`, decodeJob), noop, new AbortController().signal, async () => {});
  const ids = { ...emptyIds(), case_id: c.case_id, analysis_job_id: job.job_id };
  const assessment = await loadWorkspace(client, ids); assert.equal(assessment.findings.length, 1); ids.selected_finding_id = assessment.findings[0].finding_id;
  const challenge = await client.prepare("POST", `/cases/${IDs.case}/challenges`, decodeChallenge, { status: 201, body: { finding_id: IDs.finding, generation_mode: "AI_ASSISTED", requested_evidence: ["TECHNICAL_JUSTIFICATION"] } }).send(); ids.challenge_id = challenge.challenge_id;
  const simulation = await client.prepare("POST", `/cases/${IDs.case}/simulations`, decodeSimulation, { status: 201, body: { finding_id: IDs.finding, baseline: { minimum_ram_gb: 32 }, alternative: { minimum_ram_gb: 16 }, supplier_data_version: "synthetic-suppliers-v1" } }).send(); ids.simulation_id = simulation.simulation_id;
  const repair = await client.prepare("POST", `/findings/${IDs.finding}/repair-proposals`, decodeRepair, { status: 201, body: { action_type: "REVISE_REQUIREMENT", simulation_id: simulation.simulation_id, generation_mode: "AI_ASSISTED" } }).send(); ids.repair_proposal_id = repair.repair_proposal_id;
  backend.state.conflict = true;
  await assert.rejects(client.prepare("PATCH", `/repair-proposals/${repair.repair_proposal_id}`, decodeRepair, { body: { proposed_text: "Local text", expected_version: 1 } }).send(), e => e instanceof RequestError && e.body.code === "VERSION_CONFLICT");
  const reconciled = await loadWorkspace(client, ids); assert.equal(reconciled.repair.version, 2); assert.equal(reconciled.repair.proposed_text, "Newer server text for reconciliation.");
  const saved = await client.prepare("PATCH", `/repair-proposals/${repair.repair_proposal_id}`, decodeRepair, { body: { proposed_text: "Human-reviewed text", expected_version: 2 } }).send(); assert.equal(saved.version, 3);
  await client.prepare("PATCH", `/repair-proposals/${repair.repair_proposal_id}`, decodeRepair, { body: { proposed_text: saved.proposed_text, status: "SUBMITTED", expected_version: 3 } }).send();
  const beforeReview = await loadWorkspace(client, ids); assert.equal(canReview(beforeReview), true);
  await client.prepare("POST", `/cases/${IDs.case}/reviews`, decodeReview, { status: 201, body: { repair_proposal_id: IDs.repair, decision: "APPROVE_DRAFT", decision_reason: "The documented revision resolves the contradiction.", expected_case_version: beforeReview.caseResource.version } }).send();
  const storage = memoryStorage(); saveIds(storage, ids); const recovered = await loadWorkspace(client, readIds(storage));
  assert.equal(recovered.reviews.length, 1); assert.equal(recovered.audit.length, 1); assert.equal(recovered.reviews[0].reviewer.actor_id, IDs.actor); assert.equal(recoveredStep(recovered), 5); assert.equal(canReview(recovered), false);
  const requests = backend.state.requests;
  assert.ok(requests.every(v => !v.body || v.body instanceof FormData || !Object.hasOwn(v.body, "reviewer_actor_id")));
  const simulationRequest = requests.find(v => v.method === "POST" && v.path.endsWith("/simulations")); assert.deepEqual(Object.keys(simulationRequest.body).sort(), ["alternative", "baseline", "finding_id", "supplier_data_version"]);
  assert.equal(requests.find(v => v.method === "POST" && v.path.endsWith("/challenges")).key, null);
});


test("audit refresh accepts null hashes returned by the backend after clean analysis", async () => {
  const event = { ...auditResource(), event_type: "ANALYSIS_COMPLETED", resource: { type: "job", id: IDs.job, version: 1 }, details: { finding_count: 0 }, event_hash: null, previous_hash: null };
  const client = createClient(config, async () => Response.json(envelope(page([event]))));
  const events = await listAll(client, `/cases/${IDs.case}/audit`, decodeAudit);
  assert.equal(events.length, 1);
  assert.equal(events[0].event_hash, null);
  const resources = { ...emptyResources(), caseResource: caseResource(), job: jobResource("COMPLETED", true), audit: events };
  const html = view({ resources, step: 5 });
  assert.match(html, /Clean-case completion pending contract decision/);
  assert.match(html, /analysis completed/i);
  assert.match(html, /Not recorded/);
  assert.doesNotMatch(html, /Unable to continue/);
});
test("audit accepts unknown legacy actor names without weakening reviewer validation", () => {
  const event = { ...auditResource(), actor: { actor_id: IDs.actor, display_name: null, role: null }, event_hash: null };
  assert.equal(decodeAudit(event).actor.actor_id, IDs.actor);
  const resources = { ...fullResources(), audit: [event] };
  assert.match(view({ resources, step: 5 }), /Actor name not recorded/);
  assert.throws(() => decodeReview({ ...reviewResource(), reviewer: event.actor }), ShapeError);
});
test("audit rejects invalid hash values and missing fields", () => {
  for (const field of ["event_hash", "previous_hash"]) {
    for (const value of [42, true, {}, [], undefined]) {
      assert.throws(() => decodeAudit({ ...auditResource(), [field]: value }), ShapeError);
    }
  }
  assert.equal(decodeAudit(auditResource()).event_hash, "test-only-event-hash");
});


test("uploaded documents expose removal while active analysis disables it", () => {
  const resources = fullResources();
  const html = view({ resources, ids: fullIds(), step: 0 });
  assert.match(html, /Remove document/);
  assert.match(html, /aria-label="Remove test-tor.pdf"/);
  resources.job = jobResource("PROCESSING");
  const busy = view({ resources, ids: fullIds(), step: 0 });
  assert.match(busy, /disabled=""[^>]*aria-label="Remove test-tor.pdf"/);
});
