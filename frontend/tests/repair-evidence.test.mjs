import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { RepairEvidence } from "../src/RepairEvidence.tsx";
import { initialRevisionSelection, reconcileRevisionSelection, repairEvidence, validateEvidenceSet, revisionReadiness, revisionUploadDescription } from "../src/repairEvidenceData.ts";
import { emptyResources } from "../src/workflow.ts";
import { caseResource, documentResource, findingResource, jobResource, challengeResource, IDs } from "./fixtures.mjs";

function recorded() {
  const documents = [documentResource(), documentResource("TECHNICAL_SPECIFICATION")];
  const job = jobResource();
  return { ...emptyResources(), caseResource: caseResource(), documents, job, findings: [findingResource()] };
}
const revision = (overrides = {}) => ({ ...documentResource("TECHNICAL_SPECIFICATION"), document_id: crypto.randomUUID(), filename: "02_Revised_Technical_Specification.pdf", ...overrides });

test("selection starts with authoritative analysis inputs and keeps explicit deselections when revisions arrive", () => {
  const r = recorded();
  let selection = initialRevisionSelection(r);
  assert.deepEqual(new Set(selection.selectedIds), new Set([IDs.tor, IDs.spec]));
  selection.selectedIds = [IDs.tor];
  const revised = revision(); r.documents.push(revised);
  selection = reconcileRevisionSelection(r, selection);
  assert.deepEqual(new Set(selection.selectedIds), new Set([IDs.tor, revised.document_id]));
  assert.ok(!selection.selectedIds.includes(IDs.spec));
  selection.selectedIds = [IDs.tor];
  assert.deepEqual(reconcileRevisionSelection(r, selection).selectedIds, [IDs.tor]);
});

test("a new analysis or case resets selections to its recorded evidence rather than a stale revision set", () => {
  const r = recorded(), selection = initialRevisionSelection(r), revised = revision();
  r.documents.push(revised); r.job = { ...r.job, job_id: crypto.randomUUID(), ai_execution: { ...r.job.ai_execution, input_document_ids: [IDs.tor, revised.document_id] } };
  const next = reconcileRevisionSelection(r, selection);
  assert.deepEqual(new Set(next.selectedIds), new Set([IDs.tor, revised.document_id]));
  const fresh = { ...r, caseResource: { ...caseResource(), case_id: crypto.randomUUID() } };
  assert.deepEqual(reconcileRevisionSelection(fresh, next).selectedIds, []);
});

test("deleted, foreign and unreadable documents cannot enter a submitted evidence set", () => {
  const r = recorded();
  const bad = [revision({ deleted_at: "2026-11-07T00:00:00Z" }), revision({ case_id: crypto.randomUUID() }), revision({ processing_status: "FAILED" }), revision({ page_count: 0 })];
  r.documents.push(...bad);
  assert.equal(repairEvidence(r).usableDocuments.length, 2);
  assert.equal(validateEvidenceSet(r, [IDs.tor, bad[0].document_id]).ready, false);
  assert.match(validateEvidenceSet(r, [IDs.tor, bad[1].document_id]).errors.join(" "), /foreign/);
  assert.equal(validateEvidenceSet(r, [IDs.tor, IDs.spec, IDs.spec]).ready, false);
  assert.equal(validateEvidenceSet(r, [IDs.tor]).ready, false);
  assert.equal(validateEvidenceSet(r, [IDs.tor, IDs.spec]).ready, true);
});

test("re-analysis needs reviewed open points, selected new evidence or explicit existing-evidence acknowledgement, and saved types", () => {
  const r = recorded(), ids = [IDs.tor, IDs.spec];
  assert.equal(revisionReadiness(r, ids, [], true).ready, false);
  assert.equal(revisionReadiness(r, ids, [IDs.finding], false).ready, false);
  assert.equal(revisionReadiness(r, ids, [IDs.finding], true).ready, true);
  const revised = revision(); r.documents.push(revised);
  assert.equal(revisionReadiness(r, [IDs.tor, revised.document_id], [IDs.finding], false).ready, true);
  assert.equal(revisionReadiness(r, [IDs.tor, revised.document_id], [IDs.finding], false, { [revised.document_id]: "OTHER" }).ready, false);
  r.job.status = "PROCESSING";
  assert.equal(validateEvidenceSet(r, ids).ready, false);
});

test("a completed new analysis without old findings does not pretend prior findings were resolved", () => {
  const r = recorded(); r.job = { ...r.job, job_id: crypto.randomUUID(), result: { finding_ids: [] } };
  assert.equal(repairEvidence(r).openPoints.length, 0);
  assert.equal(r.findings[0].status, "OPEN");
});

test("Repair presents multiple PDF uploads, explicit source selection and challenge acknowledgements", () => {
  const r = recorded();
  r.challengeHistory = [challengeResource()];
  const html = renderToStaticMarkup(React.createElement(RepairEvidence, { resources: r, disabled: false, onUpload() {}, onReanalyze() {} }));
  assert.match(html, /<input(?=[^>]*name="revised_files")(?=[^>]*multiple="")[^>]*>/);
  assert.match(html, /name="revision_reason"/);
  assert.match(html, /Evidence needed for open points/);
  assert.match(html, /Source evidence needing attention/);
  assert.match(html, /Recorded challenge:/);
  assert.match(html, /What documented workload supports the higher RAM threshold/);
  assert.match(html, /Conflicting minimum RAM requirements/);
  assert.match(html, /Deselect superseded versions explicitly/);
  assert.match(html, /Analyze selected revised evidence/);
  assert.match(html, /does not resolve the finding/);
  assert.doesNotMatch(html, /all concerns resolved|automatically approved/i);
});

test("receiving execution provenance after polling replaces provisional selection with that execution's actual inputs", () => {
  const r = recorded(), revised = revision(); r.documents.push(revised);
  r.job.ai_execution = null;
  const provisional = initialRevisionSelection(r);
  assert.equal(provisional.selectedIds.length, 3);
  r.job.ai_execution = { ...jobResource().ai_execution, input_document_ids: [IDs.tor, revised.document_id] };
  assert.deepEqual(new Set(reconcileRevisionSelection(r, provisional).selectedIds), new Set([IDs.tor, revised.document_id]));
});

function vendorRecorded() {
  const r = recorded();
  for (const vendor of ["A", "B"]) for (const type of ["SUPPLIER_QUOTATION", "WARRANTY_EVIDENCE"]) {
    r.documents.push({ ...documentResource(type), document_id: crypto.randomUUID(), filename: `Vendor_${vendor}_${type}.pdf` });
  }
  const quotationB = r.documents.find(doc => doc.filename === "Vendor_B_SUPPLIER_QUOTATION.pdf");
  const extra = { ...findingResource(), finding_id: crypto.randomUUID(), title: "Vendor B warranty clarification",
    evidence: [{ document_id: quotationB.document_id, page_number: 1, excerpt: "Warranty coverage requires clarification", verification_status: "VERIFIED" }] };
  r.findings.push(extra); r.job.result.finding_ids.push(extra.finding_id);
  r.job.ai_execution.input_document_ids = r.documents.map(doc => doc.document_id);
  r.challengeHistory = [challengeResource()];
  return r;
}

test("Repair groups revision uploads by vendor and repeats a shared recorded point without duplicate review requirements", () => {
  const r = vendorRecorded();
  const html = renderToStaticMarkup(React.createElement(RepairEvidence, { resources: r, disabled: false, onUpload() {}, onReanalyze() {} }));
  assert.match(html, /Repair vendor groups/);
  assert.match(html, /Show all vendor groups/);
  assert.match(html, /Hide all vendor groups/);
  assert.match(html, /Show|Hide Vendor A details/);
  assert.match(html, /Revised PDF upload for Vendor A/);
  assert.match(html, /Revised PDF upload for Vendor B/);
  assert.match(html, /Upload revised PDFs for Vendor A/);
  assert.match(html, /Upload revised PDFs for Vendor B/);
  assert.match(html, /Yellow · 1 finding/);
  assert.match(html, /Red · 2 findings/);
  assert.equal((html.match(new RegExp(`data-finding-id="${IDs.finding}"`, "g")) ?? []).length, 2);
  assert.equal((html.match(/What documented workload supports the higher RAM threshold/g) ?? []).length, 2);
  assert.equal(revisionReadiness(r, r.documents.map(doc => doc.document_id), r.findings.map(f => f.finding_id), true).ready, true);
});

test("Repair keeps the complete evidence inventory collapsed at the bottom with selected count and a separate re-analysis action", () => {
  const r = vendorRecorded();
  const html = renderToStaticMarkup(React.createElement(RepairEvidence, { resources: r, disabled: false, onUpload() {}, onReanalyze() {} }));
  const inventory = html.indexOf('<details class="repair-evidence-selection">');
  assert.ok(inventory > html.lastIndexOf("Upload revised PDFs for"));
  assert.match(html, /<details class="repair-evidence-selection"><summary>Current documents and evidence selection \(6\)<\/summary>/);
  assert.doesNotMatch(html, /<details class="repair-evidence-selection"[^>]*\bopen=/);
  const inventoryEnd = html.indexOf("</details>", inventory);
  assert.ok(html.indexOf("Analyze selected revised evidence") > inventoryEnd);
  assert.match(html, /6 documents selected for re-analysis/);
  assert.match(html, /does not establish vendor ownership/);
  assert.match(html, /Preserve the Vendor_A, Vendor_B/);
});

test("revision upload context is descriptive and requires a meaningful reason", () => {
  assert.equal(revisionUploadDescription("Vendor A", "  Correct the warranty coverage  "), "Vendor A: Correct the warranty coverage");
  assert.equal(revisionUploadDescription("Shared case evidence", "Reconcile the TOR and specification"), "Shared case evidence: Reconcile the TOR and specification");
  assert.throws(() => revisionUploadDescription("Vendor A", "fixed"), /at least ten/);
});
