import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { vendorAssessment } from "../src/vendorAssessmentData.ts";
import { VendorAssessment } from "../src/VendorAssessment.tsx";
import { emptyResources } from "../src/workflow.ts";
import { IDs, caseResource, documentResource, jobResource, findingResource } from "./fixtures.mjs";

function mixed() {
  const documents = [documentResource(), documentResource("TECHNICAL_SPECIFICATION")];
  for (const source of ["Positive", "Negative"]) for (const vendor of ["A", "B", "C"]) {
    for (const [prefix, type, kind] of [["05", "SUPPLIER_QUOTATION", "Quotation"], ["06", "WARRANTY_EVIDENCE", "Warranty_Letter"]]) {
      documents.push({ ...documentResource(type), document_id: crypto.randomUUID(), filename: `${source}__${prefix}${vendor}_Vendor_${vendor}_${kind}.pdf` });
    }
  }
  const evaluation = { ...documentResource("EVALUATION_REPORT"), document_id: crypto.randomUUID(), filename: "Negative__07_Bid_Evaluation_Report.pdf" };
  documents.push(evaluation);
  const quotation = documents.find(d => d.filename === "Negative__05B_Vendor_B_Quotation.pdf");
  const concern = { ...findingResource(), title: "Vendor B delivery mismatch", evidence: [
    { document_id: quotation.document_id, page_number: 1, excerpt: "Delivery within 25 days", verification_status: "VERIFIED" },
  ] };
  const shared = { ...findingResource(), finding_id: crypto.randomUUID(), title: "Requirement baseline needs reconciliation" };
  const job = jobResource();
  job.result.finding_ids = [concern.finding_id, shared.finding_id];
  job.ai_execution.input_document_ids = documents.map(d => d.document_id);
  return { ...emptyResources(), caseResource: caseResource(), documents, job, findings: [concern, shared] };
}
const pack = (result, vendor, source) => result.vendors.find(v => v.id === vendor).packages.find(p => p.source === source);
const html = resources => renderToStaticMarkup(React.createElement(VendorAssessment, { resources, disabled: false, onChallenge() {} }));

test("mixed Assess groups three vendors and preserves independent document packages and valid candidates", () => {
  const r = mixed(), result = vendorAssessment(r);
  assert.deepEqual(result.vendors.map(v => v.label), ["Vendor A", "Vendor B", "Vendor C"]);
  assert.equal(result.candidateCount, 5);
  assert.equal(pack(result, "B", "positive").candidate, true);
  assert.equal(pack(result, "B", "negative").candidate, false);
  assert.equal(pack(result, "C", "positive").warrantyPresent, true);
  assert.equal(pack(result, "B", "negative").findings[0].title, "Vendor B delivery mismatch");
  assert.equal(result.sharedFindings.length, 1);
  assert.equal(pack(result, "A", "positive").openFindings.length, 0);
  const markup = html(r);
  assert.match(markup, /Assessment by vendor/);
  assert.match(markup, /Candidate for detailed evaluation/);
  assert.match(markup, /Shared evaluation concerns/);
  assert.match(markup, /Review documents \(2\)/);
  assert.doesNotMatch(markup, /vendor is compliant|all requirements are met|approved vendor/i);
});

test("package labels never decide validity; a Positive-labelled finding stays a concern", () => {
  const r = mixed();
  const positiveB = r.documents.find(d => d.filename === "Positive__05B_Vendor_B_Quotation.pdf");
  r.findings[0].evidence[0].document_id = positiveB.document_id;
  const result = vendorAssessment(r);
  assert.equal(pack(result, "B", "positive").candidate, false);
  assert.equal(pack(result, "B", "negative").candidate, true);
});

test("vendor named in a verified evaluation excerpt is linked only within that package", () => {
  const r = mixed();
  r.findings[0].evidence = [{ document_id: r.documents.at(-1).document_id, page_number: 1,
    excerpt: "Vendor C warranty was reported as missing", verification_status: "VERIFIED" }];
  const result = vendorAssessment(r);
  assert.equal(pack(result, "C", "negative").findings.length, 1);
  assert.equal(pack(result, "C", "positive").findings.length, 0);
  assert.equal(pack(result, "C", "negative").warrantyPresent, true);
  assert.match(html(r), /not an automatic vendor rejection/);
});

test("missing or unanalyzed warranty stays pending; failed or warning-bearing analyses never produce green candidates", () => {
  const r = mixed();
  const warranty = r.documents.find(d => d.filename === "Positive__06C_Vendor_C_Warranty_Letter.pdf");
  r.job.ai_execution.input_document_ids = r.job.ai_execution.input_document_ids.filter(id => id !== warranty.document_id);
  assert.equal(pack(vendorAssessment(r), "C", "positive").candidate, false);
  r.job.status = "NEEDS_REVIEW";
  assert.equal(vendorAssessment(r).candidateCount, 0);
  r.job.status = "COMPLETED"; r.job.warnings.push({ code: "EVIDENCE_EXCERPT_NOT_FOUND", message: "Review source" });
  assert.equal(vendorAssessment(r).candidateCount, 0);
  r.job = jobResource("FAILED");
  assert.equal(vendorAssessment(r).candidateCount, 0);
});

test("deleted, foreign, unlabelled and missing-result resources cannot create confident vendor candidates", () => {
  const r = mixed();
  const doc = r.documents.find(d => d.filename === "Positive__05A_Vendor_A_Quotation.pdf");
  doc.deleted_at = "2026-11-07T03:00:00Z";
  const foreign = { ...doc, deleted_at: null, case_id: crypto.randomUUID(), filename: "Vendor_Z_Quotation.pdf" };
  r.documents.push(foreign);
  const unlabelled = { ...doc, document_id: crypto.randomUUID(), deleted_at: null, filename: "supplier-offer.pdf" };
  r.documents.push(unlabelled);
  let result = vendorAssessment(r);
  assert.ok(!result.vendors.some(v => v.id === "Z"));
  assert.ok(!result.vendors.find(v => v.id === "A").packages.some(p => p.source === "positive"));
  assert.equal(result.unassigned.length, 1);
  r.job.result.finding_ids.push(crypto.randomUUID());
  assert.equal(vendorAssessment(r).candidateCount, 0);
});

test("only current active findings with verified available citations can be formally challenged", () => {
  const r = mixed(), finding = r.findings[0];
  assert.equal(vendorAssessment(r).canChallenge(finding), true);
  finding.evidence[0].page_number = 999;
  assert.equal(vendorAssessment(r).canChallenge(finding), false);
  assert.equal(vendorAssessment(r).candidateCount, 0);
  finding.evidence[0].page_number = 1; finding.status = "DISMISSED";
  assert.equal(vendorAssessment(r).canChallenge(finding), false);
  finding.status = "OPEN"; r.caseResource.case_status = "REVIEW_COMPLETED";
  assert.equal(vendorAssessment(r).canChallenge(finding), false);
  r.caseResource.case_status = "UNDER_ASSESSMENT";
  assert.equal(vendorAssessment(r).canChallenge({ ...finding, case_id: crypto.randomUUID() }), false);
});

test("Challenge finding passes the original finding ID; clean options never fabricate a challenge", () => {
  const r = mixed(), selected = [];
  const root = VendorAssessment({ resources: r, disabled: false, onChallenge: id => selected.push(id) });
  const buttons = [];
  function walk(node) {
    if (Array.isArray(node)) return node.forEach(walk);
    if (!node || typeof node !== "object") return;
    if (node.type === "button") buttons.push(node);
    walk(node.props?.children);
  }
  walk(root);
  assert.equal(buttons.length, 7); // One vendor concern plus the shared point in all six packages.
  const ownPoint = buttons.find(button => button.props["aria-label"] === `Challenge finding: ${r.findings[0].title}`);
  assert.equal(ownPoint.props.disabled, false);
  ownPoint.props.onClick();
  assert.deepEqual(selected, [r.findings[0].finding_id]);
  r.findings = []; r.job.result.finding_ids = [];
  buttons.length = 0;
  walk(VendorAssessment({ resources: r, disabled: false, onChallenge: id => selected.push(id) }));
  assert.equal(buttons.length, 0);
  assert.equal(vendorAssessment(r).candidateCount, 6);
});
