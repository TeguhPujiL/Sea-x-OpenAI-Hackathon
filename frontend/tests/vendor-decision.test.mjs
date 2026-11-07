import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { comparisonData, VendorDecisionSummary } from "../src/VendorDecisionSummary.tsx";
import { emptyResources } from "../src/workflow.ts";
import { caseResource, documentResource, jobResource, findingResource, challengeResource, simulationResource, repairResource, reviewResource } from "./fixtures.mjs";

function recorded() {
  const documents = [documentResource(), documentResource("TECHNICAL_SPECIFICATION")];
  for (const vendor of ["A", "B"]) for (const [type, kind] of [["SUPPLIER_QUOTATION", "Quotation"], ["WARRANTY_EVIDENCE", "Warranty"]]) {
    documents.push({ ...documentResource(type), document_id: crypto.randomUUID(), filename: `Vendor_${vendor}_${kind}.pdf` });
  }
  const job = jobResource(); job.ai_execution.input_document_ids = documents.map(doc => doc.document_id);
  return { ...emptyResources(), caseResource: caseResource(), documents, job, findings: [findingResource()],
    challengeHistory: [challengeResource()], challenge: challengeResource(), simulationHistory: [simulationResource()], simulation: simulationResource(), repair: repairResource(), reviews: [reviewResource()] };
}
const markup = (resources, selectedVendorId = null) => renderToStaticMarkup(React.createElement(VendorDecisionSummary, { resources, selectedVendorId, onSelectVendor() {}, disabled: false }));

test("Assure compares recorded vendor risk without automatically selecting a winner", () => {
  const resources = recorded(), report = comparisonData(resources, null), html = markup(resources);
  assert.equal(report.vendors.length, 2);
  assert.equal(report.selected_vendor_id, null);
  assert.equal(report.preference_status, "NO_CURRENT_PREFERENCE");
  assert.equal(report.vendors[0].risk.color, "yellow");
  assert.equal(report.vendors[0].risk.score, 1);
  assert.match(html, /Vendor score summary and preference/);
  assert.match(html, /Select Vendor A/); assert.match(html, /Select Vendor B/);
  assert.doesNotMatch(html, /checked=""/);
  assert.match(html, /No vendor is selected automatically/);
  assert.match(html, /not a declaration that every workflow step/);
});

test("red vendor selection remains provisional, preserves findings, and sends exact vendor ID", () => {
  const resources = recorded();
  const second = { ...findingResource(), finding_id: crypto.randomUUID(), severity: "LOW" };
  resources.findings.push(second); resources.job.result.finding_ids.push(second.finding_id);
  const third = { ...second, finding_id: crypto.randomUUID() };
  resources.findings.push(third); resources.job.result.finding_ids.push(third.finding_id);
  const before = JSON.stringify(resources);
  const report = comparisonData(resources, "B");
  assert.equal(report.selected_vendor_id, "B");
  assert.equal(report.preference_status, "PROVISIONAL_PREFERENCE_UNRESOLVED_POINTS");
  assert.equal(report.progress.unresolved_findings, 3);
  assert.equal(report.vendors[1].risk.color, "red");
  assert.equal(report.vendors[1].risk.score, 3);
  assert.equal(JSON.stringify(resources), before);
  const selected = [], root = VendorDecisionSummary({ resources, selectedVendorId: null, onSelectVendor: id => selected.push(id), disabled: false });
  const radios = [];
  function walk(node) {
    if (Array.isArray(node)) return node.forEach(walk);
    if (!node || typeof node !== "object") return;
    if (node.type === "input" && node.props.type === "radio") radios.push(node);
    walk(node.props?.children);
  }
  walk(root); radios[1].props.onChange();
  assert.deepEqual(selected, ["B"]);
  assert.match(markup(resources, "B"), /preference is provisional/);
});

test("pending, failed, outside-analysis and stale vendor choices cannot become current preferences", () => {
  assert.equal(comparisonData(emptyResources(), null).selected_vendor_id, null);
  assert.equal(comparisonData(emptyResources(), null).progress.repair_status, null);
  const resources = recorded();
  resources.job = jobResource("PROCESSING");
  assert.equal(comparisonData(resources, "A").selected_vendor_id, null);
  assert.equal(comparisonData(resources, "A").stale_selection, true);
  resources.job = jobResource("FAILED");
  assert.equal(comparisonData(resources, "A").usable_analysis, false);
  resources.job = jobResource();
  let report = comparisonData(resources, "A");
  assert.equal(report.selected_vendor_id, null);
  assert.ok(report.vendors.every(vendor => !vendor.selectable));
  assert.match(markup(resources, "A"), /previous preference is unavailable/);
  assert.equal(comparisonData(recorded(), "Unknown").selected_vendor_id, null);
  const incomplete = recorded(); incomplete.job.result.finding_ids.push(crypto.randomUUID());
  assert.equal(comparisonData(incomplete, "A").selected_vendor_id, null);
});

test("progress counts unique current records and excludes foreign or older-analysis histories", () => {
  const resources = recorded();
  resources.challengeHistory.push({ ...challengeResource(), challenge_id: crypto.randomUUID(), case_id: crypto.randomUUID() },
    { ...challengeResource(), challenge_id: crypto.randomUUID(), finding_id: crypto.randomUUID() });
  resources.simulationHistory.push({ ...simulationResource(), simulation_id: crypto.randomUUID(), finding_id: crypto.randomUUID() });
  const report = comparisonData(resources, "A");
  assert.equal(report.progress.recorded_challenges, 1);
  assert.equal(report.progress.recorded_simulations, 1);
  assert.equal(report.records.challenge_ids.length, 1);
  assert.equal(report.progress.repair_status, "DRAFT");
  assert.equal(report.progress.loaded_reviews, 1);
  assert.equal(report.findings[0].evidence[0].excerpt, "Minimum RAM: 16 GB");
  assert.ok(!JSON.stringify(report).includes("openai_api_key"));
});

test("clean current analyzed choice is a preference for human review and keeps contract gap visible", () => {
  const resources = recorded();
  resources.findings = []; resources.job.result.finding_ids = [];
  resources.repair = null; resources.reviews = [];
  const report = comparisonData(resources, "A");
  assert.equal(report.selected_vendor_id, "A");
  assert.equal(report.preference_status, "PREFERENCE_FOR_HUMAN_REVIEW");
  assert.equal(report.vendors[0].risk.color, "green");
  assert.ok(report.limits.some(value => value.includes("G01")));
  assert.match(markup(resources, "A"), /does not approve a procurement/);
});

test("deleted and foreign quotations do not supply a selectable vendor", () => {
  const resources = recorded();
  for (const document of resources.documents.filter(doc => doc.filename.startsWith("Vendor_A"))) document.deleted_at = "2026-11-07T03:00:00Z";
  for (const document of resources.documents.filter(doc => doc.filename.startsWith("Vendor_B"))) document.case_id = crypto.randomUUID();
  const report = comparisonData(resources, "A");
  assert.equal(report.vendors.length, 0); assert.equal(report.selected_vendor_id, null);
  assert.match(markup(resources), /No vendor-labelled supplier quotation/);
});
