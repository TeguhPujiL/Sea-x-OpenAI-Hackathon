import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readCaseHistory, rememberCase, orderCases, caseHistoryPage, caseHistoryKey } from "../src/history.ts";
import { newUploadItems, uploadBatch } from "../src/uploads.ts";
import { CaseHistory } from "../src/CaseHistory.tsx";
import { DocumentUploads, DocumentTypeEditor } from "../src/DocumentUploads.tsx";
import { LoginForm } from "../src/AuthGate.tsx";
import { createClient } from "../src/api.ts";
import { restoreCaseResources } from "../src/resources.ts";
import { emptyIds, recoveredStep } from "../src/workflow.ts";
import { caseResource, documentResource, jobResource, challengeResource, simulationResource, repairResource, reviewResource, auditResource, fixtureBackend, envelope, errorEnvelope, IDs } from "./fixtures.mjs";
const config = { baseUrl: "/api/v1", development: true };
const noop = () => {};
function storage() { const map = new Map(); return { getItem: k => map.get(k) ?? null, setItem: (k,v) => map.set(k,v) }; }
const pdf = name => new File(["%PDF-test-only"], name, { type: "application/pdf" });
const accepted = (form, overrides = {}) => Response.json(envelope({ ...documentResource("OTHER"), document_id: crypto.randomUUID(), filename: form.get("file").name, ...overrides }), { status: 201 });

test("recent case history stores only valid identifiers and stays ordered across reloads", () => {
  const store = storage();
  store.setItem(caseHistoryKey, JSON.stringify([IDs.actor, IDs.actor, "invalid", { title: "private" }]));
  assert.deepEqual(readCaseHistory(store), [IDs.actor]);
  assert.deepEqual(rememberCase(store, IDs.case).ids, [IDs.case, IDs.actor]);
  rememberCase(store, IDs.actor);
  assert.deepEqual(readCaseHistory(store), [IDs.actor, IDs.case]);
  const values = [caseResource(), { ...caseResource(), case_id: IDs.actor, title: "Another case" }];
  assert.equal(orderCases(values, readCaseHistory(store))[0].title, "Another case");
  assert.equal(store.getItem(caseHistoryKey).includes("private"), false);
  assert.equal(orderCases([{ ...caseResource(), deleted_at: "2026-11-07T00:00:00Z" }], []).length, 0);
  assert.equal(rememberCase({ getItem() { throw Error(); }, setItem() { throw Error(); } }, IDs.case).saved, false);
});
test("case history renders current backend metadata and an accessible reopen control", () => {
  const html = renderToStaticMarkup(React.createElement(CaseHistory, { cases: [caseResource()], recentIds: [IDs.case], activeId: null, loading: false, error: null, disabled: false, onOpen: noop, onRefresh: noop, onClose: noop }));
  assert.match(html, /Case history/); assert.match(html, /Synthetic frontend integration test/); assert.match(html, /Open case/); assert.match(html, /Recently opened/);
});
test("multiple uploads use one contracted multipart request and unique key per PDF", async () => {
  const requests = [];
  const client = createClient(config, async (_, init) => { requests.push(init); return accepted(init.body); });
  const docs = [];
  const queue = await uploadBatch(client, IDs.case, newUploadItems([pdf("a.pdf"), pdf("b.pdf")], "Batch note"), noop, d => docs.push(d), new AbortController().signal);
  assert.deepEqual(queue.map(q => q.status), ["uploaded", "uploaded"]);
  assert.equal(docs.length, 2); assert.notEqual(requests[0].headers["Idempotency-Key"], requests[1].headers["Idempotency-Key"]);
  for (const request of requests) {
    assert.equal(request.body.getAll("file").length, 1);
    assert.equal(request.body.get("document_type"), "OTHER");
    assert.equal(request.body.get("description"), "Batch note");
  }
});
test("partial upload failure preserves successes and retry does not upload them twice", async () => {
  const requests = []; let reject = true;
  const client = createClient(config, async (_, init) => {
    requests.push(init);
    if (reject && init.body.get("file").name === "bad.pdf") return Response.json(errorEnvelope("PDF_EXTRACTION_FAILED", "Test rejection"), { status: 422 });
    return accepted(init.body);
  });
  let queue = await uploadBatch(client, IDs.case, newUploadItems([pdf("a.pdf"), pdf("bad.pdf"), pdf("c.pdf")], ""), noop, noop, new AbortController().signal);
  assert.deepEqual(queue.map(q => q.status), ["uploaded", "failed", "uploaded"]);
  reject = false;
  queue = await uploadBatch(client, IDs.case, queue, noop, noop, new AbortController().signal);
  assert.equal(requests.length, 4); assert.equal(queue.filter(q => q.status === "uploaded").length, 3);
  assert.notEqual(requests[1].headers["Idempotency-Key"], requests[3].headers["Idempotency-Key"]);
});
test("unknown upload outcomes reuse the same captured request key", async () => {
  const requests = [];
  const client = createClient(config, async (_, init) => { requests.push(init); if (requests.length === 1) throw new TypeError("Network failure"); return accepted(init.body); });
  let queue = await uploadBatch(client, IDs.case, newUploadItems([pdf("retry.pdf")], ""), noop, noop, new AbortController().signal);
  assert.equal(queue[0].status, "unknown");
  queue = await uploadBatch(client, IDs.case, queue, noop, noop, new AbortController().signal);
  assert.equal(queue[0].status, "uploaded"); assert.equal(requests[0].headers["Idempotency-Key"], requests[1].headers["Idempotency-Key"]);
});
test("cross-case upload responses stop the batch without inventing documents", async () => {
  let calls = 0; const documents = [];
  const client = createClient(config, async (_, init) => { calls++; return accepted(init.body, { case_id: IDs.actor }); });
  const queue = await uploadBatch(client, IDs.case, newUploadItems([pdf("a.pdf"), pdf("b.pdf")], ""), noop, d => documents.push(d), new AbortController().signal);
  assert.equal(calls, 1); assert.equal(documents.length, 0); assert.deepEqual(queue.map(q => q.status), ["unverified", "pending"]);
});
test("file selection permits multiple PDFs and types can be assigned after upload", () => {
  const html = renderToStaticMarkup(React.createElement(DocumentUploads, { disabled: false, items: [], onUpload: noop, onRetry: noop, onClear: noop }));
  assert.match(html, /multiple=""/); assert.match(html, /Upload selected PDFs/); assert.doesNotMatch(html, /name="document_type"/);
  const editor = renderToStaticMarkup(React.createElement(DocumentTypeEditor, { document: documentResource("OTHER"), disabled: false, onSave: noop }));
  assert.match(editor, /Save document type/); assert.match(editor, /TECHNICAL_SPECIFICATION/);
});
test("login form masks passwords and does not contain a default password", () => {
  const html = renderToStaticMarkup(React.createElement(LoginForm, { busy: false, error: null, onLogin: async () => {} }));
  assert.match(html, /type="password"/); assert.match(html, /autocomplete="current-password"/i); assert.match(html, /Sign in/); assert.doesNotMatch(html.match(/<input[^>]*type="password"[^>]*>/)[0], /\bvalue=/);
});


test("reopening case history restores recorded simulation, repair, review and audit IDs", async () => {
  const backend = fixtureBackend();
  Object.assign(backend.state, { caseResource: caseResource(), documents: [documentResource(), documentResource("TECHNICAL_SPECIFICATION")],
    job: jobResource(), polls: 3, challenge: challengeResource(), simulation: simulationResource(),
    repair: { ...repairResource(), status: "SUBMITTED" }, reviews: [reviewResource()], audit: [auditResource()] });
  const client = createClient(config, backend.fetcher);
  const restored = await restoreCaseResources(client, { ...emptyIds(), case_id: IDs.case, analysis_job_id: IDs.job });
  assert.equal(restored.ids.simulation_id, IDs.simulation);
  assert.equal(restored.ids.repair_proposal_id, IDs.repair);
  assert.equal(restored.resources.reviews.length, 1);
  assert.equal(restored.resources.audit.length, 1);
  assert.equal(recoveredStep(restored.resources), 5);
});


function historyCases() {
  return Array.from({ length: 12 }, (_, index) => ({ ...caseResource(), case_id: crypto.randomUUID(), title: `History ${index}`,
    category: index % 2 ? "SERVICES" : "IT_EQUIPMENT", created_at: new Date(Date.UTC(2026,10,7,0,index)).toISOString() }));
}
test("case history paginates five newest cases without gaps or duplicates", () => {
  const cases = historyCases();
  const options = { query: "", category: "", recentOnly: false, page: 1 };
  const first = caseHistoryPage(cases, [cases[0].case_id], options);
  const second = caseHistoryPage(cases, [], { ...options, page: 2 });
  const third = caseHistoryPage(cases, [], { ...options, page: 3 });
  assert.deepEqual([first.items.length, second.items.length, third.items.length], [5,5,2]);
  assert.equal(first.items[0].title, "History 11");
  assert.equal(first.pages, 3);
  assert.equal(new Set([...first.items, ...second.items, ...third.items].map(c => c.case_id)).size, 12);
});
test("category, search and recently opened filters combine and clamp pagination", () => {
  const cases = historyCases();
  const options = { query: "", category: "SERVICES", recentOnly: false, page: 99 };
  const filtered = caseHistoryPage(cases, [], options);
  assert.equal(filtered.total, 6); assert.equal(filtered.page, 2); assert.equal(filtered.items.length, 1);
  const recent = caseHistoryPage(cases, [cases[1].case_id, cases[2].case_id], { ...options, recentOnly: true });
  assert.equal(recent.total, 1); assert.equal(recent.page, 1); assert.equal(recent.items[0].case_id, cases[1].case_id);
  const empty = caseHistoryPage(cases, [], { ...options, query: "no-such-case" });
  assert.equal(empty.total, 0); assert.equal(empty.page, 1);
});
test("case history renders category options, page controls and only five rows", () => {
  const html = renderToStaticMarkup(React.createElement(CaseHistory, { cases: historyCases(), recentIds: [], activeId: null,
    loading: false, error: null, disabled: false, onOpen: noop, onRefresh: noop, onClose: noop }));
  assert.match(html, /All categories/); assert.match(html, /value="SERVICES"/);
  assert.match(html, /Page 1 of 3/); assert.match(html, /Next/);
  assert.equal((html.match(/>Open case<\/button>/g) ?? []).length, 5);
});
