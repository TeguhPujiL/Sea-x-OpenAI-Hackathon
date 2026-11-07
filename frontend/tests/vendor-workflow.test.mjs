import test from "node:test";
import assert from "node:assert/strict";
import { createClient, TransportError } from "../src/api.ts";
import { documentationRisk, vendorAssessment } from "../src/vendorAssessmentData.ts";
import { simulationSupport, vendorWorkflow, prepareVendorSimulationBatch } from "../src/vendorWorkflowData.ts";
import { loadWorkspace } from "../src/resources.ts";
import { emptyIds, emptyResources } from "../src/workflow.ts";
import { IDs, caseResource, documentResource, jobResource, findingResource, challengeResource, simulationResource, envelope, page } from "./fixtures.mjs";

const parameters = () => ({ baseline: 32, alternative: 16, version: "synthetic-suppliers-v1" });
const config = { baseUrl: "/api/v1", development: true };

function mixedResources() {
  const documents = [];
  for (const source of ["Positive", "Negative"]) {
    for (const [type, name] of [["TOR", "01_Terms_of_Reference"], ["TECHNICAL_SPECIFICATION", "02_Technical_Specification"]]) {
      documents.push({ ...documentResource(type), document_id: crypto.randomUUID(), filename: `${source}__${name}.pdf` });
    }
    for (const vendor of ["A", "B"]) for (const [type, name] of [["SUPPLIER_QUOTATION", "Quotation"], ["WARRANTY_EVIDENCE", "Warranty"]]) {
      documents.push({ ...documentResource(type), document_id: crypto.randomUUID(), filename: `${source}__Vendor_${vendor}_${name}.pdf` });
    }
  }
  const negativeTor = documents.find(doc => doc.filename === "Negative__01_Terms_of_Reference.pdf");
  const negativeSpec = documents.find(doc => doc.filename === "Negative__02_Technical_Specification.pdf");
  const findings = [
    { ...findingResource(), finding_id: crypto.randomUUID(), title: "Memory baseline conflict", evidence: [
      { document_id: negativeTor.document_id, page_number: 1, excerpt: "Minimum memory 16 GB", verification_status: "VERIFIED" },
      { document_id: negativeSpec.document_id, page_number: 1, excerpt: "Mandatory memory 32 GB", verification_status: "VERIFIED" },
    ] },
    { ...findingResource(), finding_id: crypto.randomUUID(), severity: "MEDIUM", title: "RAM need requires workload evidence", evidence: [
      { document_id: negativeTor.document_id, page_number: 1, excerpt: "Approved RAM 16 GB", verification_status: "VERIFIED" },
    ] },
  ];
  const job = jobResource();
  job.result.finding_ids = findings.map(finding => finding.finding_id);
  job.ai_execution.input_document_ids = documents.map(doc => doc.document_id);
  const challenges = findings.map(finding => ({ ...challengeResource(), challenge_id: crypto.randomUUID(), finding_id: finding.finding_id }));
  return { ...emptyResources(), caseResource: caseResource(), documents, job, findings, challengeHistory: challenges, simulationHistory: [] };
}

function responseFor(body, overrides = {}) {
  return { ...simulationResource(), simulation_id: crypto.randomUUID(), finding_id: body.finding_id,
    input_snapshot: { ...simulationResource().input_snapshot, baseline: body.baseline, alternative: body.alternative }, ...overrides };
}

test("shared challenge points repeat for each relevant vendor without leaking across source packages", () => {
  const resources = mixedResources(), workflow = vendorWorkflow(resources);
  assert.equal(workflow.vendors.length, 2);
  for (const vendor of workflow.vendors) {
    const positive = vendor.packages.find(pack => pack.source === "positive");
    const negative = vendor.packages.find(pack => pack.source === "negative");
    assert.equal(positive.points.length, 0);
    assert.deepEqual(negative.points.map(point => point.finding.finding_id), resources.findings.map(finding => finding.finding_id));
    assert.ok(negative.points.every(point => point.shared));
    assert.ok(negative.points.every(point => point.challenges.length === 1));
    assert.equal(positive.risk.color, "green");
    assert.equal(negative.risk.color, "red");
  }
  // Repeating a point in the presentation does not manufacture challenge records.
  assert.equal(workflow.challenges.length, 2);
});

test("documentation score counts unique active findings independently of severity", () => {
  const concern = findingResource();
  assert.deepEqual([documentationRisk(true, true, [], []).color, documentationRisk(true, true, [], []).score], ["green", 0]);
  assert.deepEqual([documentationRisk(false, true, [], []).color, documentationRisk(false, true, [], []).score], ["yellow", null]);
  assert.equal(documentationRisk(true, true, [], [{ ...concern, severity: "LOW" }]).score, 1);
  assert.deepEqual([documentationRisk(true, true, [], [concern]).color, documentationRisk(true, true, [], [concern]).score], ["yellow", 1]);
  assert.equal(documentationRisk(true, true, [], [{ ...concern, evidence_status: "UNVERIFIED" }]).score, 1);
  assert.equal(documentationRisk(false, true, [{ ...documentResource(), processing_status: "FAILED" }], []).score, null);
  assert.deepEqual([documentationRisk(false, false, [], []).color, documentationRisk(false, false, [], []).score], ["yellow", null]);
  assert.equal(documentationRisk(true, true, [], [{ ...concern, status: "DISMISSED" }]).score, 0);
  assert.equal(documentationRisk(true, true, [], [concern, concern]).score, 1);
  const low = Array.from({ length: 3 }, () => ({ ...concern, finding_id: crypto.randomUUID(), severity: "LOW" }));
  assert.equal(documentationRisk(true, true, [], low).color, "red");
  assert.equal(documentationRisk(true, true, [], low).score, 3);
  assert.equal(documentationRisk(true, true, [], [{ ...concern, status: "RESOLVED" }]).score, 0);
});

test("vendor aggregate counts the union across current packages and ignores packages outside the analysis", () => {
  const resources = mixedResources();
  const positiveTor = resources.documents.find(doc => doc.filename === "Positive__01_Terms_of_Reference.pdf");
  const positiveSpec = resources.documents.find(doc => doc.filename === "Positive__02_Technical_Specification.pdf");
  resources.findings[0].evidence[0].document_id = positiveTor.document_id;
  resources.findings[0].evidence[1].document_id = positiveSpec.document_id;
  let vendors = vendorAssessment(resources).vendors;
  assert.ok(vendors.every(vendor => vendor.packages.every(pack => pack.risk.score === 1)));
  assert.ok(vendors.every(vendor => vendor.risk.score === 2 && vendor.risk.color === "yellow"));
  resources.job.ai_execution.input_document_ids = resources.job.ai_execution.input_document_ids.filter(id =>
    !resources.documents.some(doc => doc.document_id === id && doc.filename.startsWith("Positive__Vendor_")));
  vendors = vendorAssessment(resources).vendors;
  assert.ok(vendors.every(vendor => vendor.risk.score === 1 && vendor.risk.color === "yellow"));
});

test("one shared finding repeated across included packages counts once in each vendor total", () => {
  const resources = mixedResources();
  resources.findings = [resources.findings[0]];
  resources.job.result.finding_ids = resources.findings.map(finding => finding.finding_id);
  resources.findings[0].evidence = [resources.findings[0].evidence[0]];
  resources.documents.find(doc => doc.document_id === resources.findings[0].evidence[0].document_id).filename = "01_Common_Terms_of_Reference.pdf";
  const vendors = vendorAssessment(resources).vendors;
  assert.ok(vendors.every(vendor => vendor.packages.every(pack => pack.challengePoints.length === 1)));
  assert.ok(vendors.every(vendor => vendor.risk.score === 1 && vendor.risk.color === "yellow"));
});

test("unsupported warranty, arithmetic and delivery points cannot be presented as RAM simulations", () => {
  const finding = findingResource();
  assert.equal(simulationSupport(finding).supported, true);
  for (const title of ["Warranty evidence contradiction", "HPS arithmetic mismatch", "Delivery deviation", "Purchase order RAM substitution"]) {
    // RAM in summary is insufficient when the finding names another method.
    const support = simulationSupport({ ...finding, title });
    assert.equal(support.supported, false, title);
    assert.match(support.reason, /No simulation method/);
  }
});

test("vendor batch deduplicates repeated shared finding IDs and sends canonical per-finding requests", async () => {
  const resources = mixedResources(), calls = [], accepted = [];
  const client = createClient(config, async (url, init) => {
    const body = JSON.parse(init.body); calls.push({ url, body, key: init.headers["Idempotency-Key"] });
    return Response.json(envelope(responseFor(body)), { status: 201 });
  });
  const [first, second] = resources.findings.map(finding => finding.finding_id);
  const batch = prepareVendorSimulationBatch(client, resources, [first, first, second, second], parameters(),
    (simulation, completed, total) => accepted.push({ id: simulation.finding_id, completed, total }));
  const results = await batch.send();
  assert.equal(results.length, 2); assert.equal(calls.length, 2);
  assert.deepEqual(accepted, [{ id: first, completed: 1, total: 2 }, { id: second, completed: 2, total: 2 }]);
  assert.deepEqual(calls[0].body, { finding_id: first, baseline: { minimum_ram_gb: 32 }, alternative: { minimum_ram_gb: 16 }, supplier_data_version: "synthetic-suppliers-v1" });
  assert.equal(calls[0].url, `/api/v1/cases/${IDs.case}/simulations`);
  assert.ok(calls.every(call => call.key)); assert.notEqual(calls[0].key, calls[1].key);
});

test("partial transport retry keeps the uncertain request key/body and skips completed simulations", async () => {
  const resources = mixedResources(), calls = [], callbacks = [];
  const [first, second] = resources.findings.map(finding => finding.finding_id);
  let interrupted = false;
  const client = createClient(config, async (url, init) => {
    const body = JSON.parse(init.body); calls.push({ body: init.body, key: init.headers["Idempotency-Key"], finding: body.finding_id });
    if (body.finding_id === second && !interrupted) { interrupted = true; throw new TypeError("Mock interrupted response only"); }
    return Response.json(envelope(responseFor(body)), { status: 201 });
  });
  const values = parameters();
  const batch = prepareVendorSimulationBatch(client, resources, [first, second], values,
    (simulation, completed, total) => callbacks.push([simulation.finding_id, completed, total]));
  await assert.rejects(batch.send(), TransportError);
  assert.deepEqual(callbacks, [[first, 1, 2]]);
  values.baseline = 128; values.version = "must-not-replace-captured-version";
  const result = await batch.send();
  assert.equal(result.length, 2); assert.equal(calls.length, 3);
  assert.deepEqual(calls.map(call => call.finding), [first, second, second]);
  assert.equal(calls[1].key, calls[2].key); assert.equal(calls[1].body, calls[2].body);
  assert.notEqual(calls[0].key, calls[1].key);
  assert.deepEqual(callbacks, [[first, 1, 2], [second, 2, 2]]);
  assert.equal(JSON.parse(calls[2].body).baseline.minimum_ram_gb, 32);
});

test("batch preconditions reject stale, foreign, closed or unverified points before any API call", () => {
  const mutations = [
    resources => { resources.findings[0].analysis_job_id = crypto.randomUUID(); },
    resources => { resources.findings[0].case_id = crypto.randomUUID(); },
    resources => { resources.findings[0].evidence_status = "UNVERIFIED"; },
    resources => { resources.findings[0].evidence[0].page_number = 999; },
    resources => { resources.challengeHistory[0].case_id = crypto.randomUUID(); },
    resources => { resources.challengeHistory[0].status = "CLOSED"; },
    resources => { resources.findings[0].status = "RESOLVED"; },
    resources => { resources.findings[0].title = "Warranty and RAM evidence conflict"; },
  ];
  for (const mutate of mutations) {
    const resources = mixedResources(); mutate(resources); let requests = 0;
    const client = createClient(config, async () => { requests++; throw new Error("No API call permitted"); });
    assert.throws(() => prepareVendorSimulationBatch(client, resources, [resources.findings[0].finding_id], parameters(), () => {}), /current verified RAM finding/);
    assert.equal(requests, 0);
  }
  const resources = mixedResources(), client = createClient(config, async () => { throw new Error("No API call permitted"); });
  assert.throws(() => prepareVendorSimulationBatch(client, resources, [], parameters(), () => {}), /at least one/);
  assert.throws(() => prepareVendorSimulationBatch(client, resources, [resources.findings[0].finding_id], { ...parameters(), baseline: 1.5 }, () => {}), /positive integer/);
});

test("cross-case or mismatched simulation responses cannot enter the accepted batch history", async () => {
  for (const overrides of [{ case_id: crypto.randomUUID() }, { finding_id: crypto.randomUUID() }]) {
    const resources = mixedResources(), accepted = [];
    const client = createClient(config, async (url, init) => Response.json(envelope(responseFor(JSON.parse(init.body), overrides)), { status: 201 }));
    const batch = prepareVendorSimulationBatch(client, resources, [resources.findings[0].finding_id], parameters(), value => accepted.push(value));
    await assert.rejects(batch.send(), /Cross-case or mismatched/);
    assert.equal(accepted.length, 0);
  }
});

test("workspace refresh restores all case challenge/simulation history for vendor groups", async () => {
  const resources = mixedResources();
  const simulation = { ...simulationResource(), finding_id: resources.findings[0].finding_id };
  const paths = [];
  const client = createClient(config, async input => {
    const path = new URL(input, "http://mock").pathname; paths.push(path);
    const data = path.endsWith("/documents") ? page(resources.documents)
      : path.endsWith("/findings") ? page(resources.findings)
      : path.endsWith("/challenges") ? page(resources.challengeHistory)
      : path.endsWith("/simulations") ? page([simulation])
      : path.startsWith("/api/v1/jobs/") ? resources.job : resources.caseResource;
    return Response.json(envelope(data));
  });
  const restored = await loadWorkspace(client, { ...emptyIds(), case_id: IDs.case, analysis_job_id: IDs.job });
  assert.equal(restored.challengeHistory.length, 2); assert.equal(restored.simulationHistory.length, 1);
  assert.ok(paths.some(path => path.endsWith("/challenges")));
  assert.ok(paths.some(path => path.endsWith("/simulations")));
  const group = vendorWorkflow(restored).vendors[0].packages.find(pack => pack.source === "negative");
  assert.equal(group.points[0].challenges.length, 1); assert.equal(group.points[0].simulations[0].simulation_id, simulation.simulation_id);
});

test("workspace refresh rejects foreign history instead of displaying it under a vendor", async () => {
  const resources = mixedResources(); resources.challengeHistory[0].case_id = crypto.randomUUID();
  const client = createClient(config, async input => {
    const path = new URL(input, "http://mock").pathname;
    return Response.json(envelope(path.endsWith("/documents") ? page(resources.documents)
      : path.endsWith("/findings") ? page(resources.findings)
      : path.endsWith("/challenges") ? page(resources.challengeHistory)
      : path.endsWith("/simulations") ? page([])
      : path.startsWith("/api/v1/jobs/") ? resources.job : resources.caseResource));
  });
  await assert.rejects(loadWorkspace(client, { ...emptyIds(), case_id: IDs.case, analysis_job_id: IDs.job }), /does not belong to the active case/);
});
