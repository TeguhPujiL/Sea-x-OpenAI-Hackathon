// Authored regression cases. Execution is deferred at the user's request.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { comparisonData } from "../src/VendorDecisionSummary.tsx";
import { createVendorComparisonPdf } from "../src/vendorComparisonPdf.ts";
import { emptyResources } from "../src/workflow.ts";
import { caseResource, documentResource, jobResource, findingResource } from "./fixtures.mjs";

const font = readFileSync(new URL("../public/fonts/NotoSans-Regular.ttf", import.meta.url)).toString("base64");
const generatedAt = "2026-11-07T07:00:00Z";
function comparison() {
  const resources = { ...emptyResources(), caseResource: caseResource(), job: jobResource(), findings: [findingResource()],
    documents: [documentResource(), documentResource("TECHNICAL_SPECIFICATION"),
      { ...documentResource("SUPPLIER_QUOTATION"), document_id: crypto.randomUUID(), filename: "Vendor_A_Quotation.pdf" },
      { ...documentResource("WARRANTY_EVIDENCE"), document_id: crypto.randomUUID(), filename: "Vendor_A_Warranty.pdf" }] };
  resources.job.ai_execution.input_document_ids = resources.documents.map(document => document.document_id);
  return comparisonData(resources, "A");
}

test("vendor comparison produces an actual embedded-font PDF without changing its source records", () => {
  const report = comparison(), before = JSON.stringify(report);
  const doc = createVendorComparisonPdf(report, font, generatedAt);
  const bytes = Buffer.from(doc.output("arraybuffer"));
  assert.equal(bytes.subarray(0, 5).toString("ascii"), "%PDF-");
  assert.ok(bytes.length > 10000);
  assert.ok(doc.getNumberOfPages() >= 2);
  assert.ok(doc.getFontList().NotoSans.includes("normal"));
  assert.equal(JSON.stringify(report), before);
  assert.equal(report.preference_status, "PROVISIONAL_PREFERENCE_UNRESOLVED_POINTS");
});

test("long filenames, hashes, citations and multiple vendors paginate without truncating input records", () => {
  const report = comparison(), original = report.vendors[0];
  report.vendors = Array.from({ length: 12 }, (_, index) => ({ ...original, id: String(index), label: `Vendor ${index}`,
    packages: original.packages.map(pack => ({ ...pack, documents: pack.documents.map(document => ({ ...document,
      document_id: crypto.randomUUID(), filename: `${"Long_document_filename_".repeat(35)}${index}.pdf`, sha256: "a".repeat(64) })) })) }));
  report.findings = Array.from({ length: 8 }, (_, index) => ({ ...report.findings[0], finding_id: crypto.randomUUID(), title: `Recorded finding ${index}`,
    evidence: [{ ...report.findings[0].evidence[0], excerpt: "A complete recorded evidence passage with no truncation. ".repeat(90) }] }));
  const before = JSON.stringify(report);
  const doc = createVendorComparisonPdf(report, font, generatedAt);
  assert.ok(doc.getNumberOfPages() > 12);
  assert.equal(JSON.stringify(report), before);
  assert.equal(Buffer.from(doc.output("arraybuffer")).subarray(0, 5).toString("ascii"), "%PDF-");
});

test("Unicode source labels and empty workspaces remain exportable without a false compliance result", () => {
  const report = comparison();
  report.vendors[0].label = "Vendor Étoile - Łódź - Δοκιμή";
  report.vendors[0].packages[0].documents[0].filename = "révision_évidence_😀.pdf";
  const doc = createVendorComparisonPdf(report, font, generatedAt);
  assert.equal(Buffer.from(doc.output("arraybuffer")).subarray(0, 5).toString("ascii"), "%PDF-");
  const empty = comparisonData(emptyResources(), null);
  const emptyDoc = createVendorComparisonPdf(empty, font, generatedAt);
  assert.ok(emptyDoc.getNumberOfPages() >= 1);
  assert.equal(empty.selected_vendor_id, null);
  assert.equal(empty.usable_analysis, false);
});

test("missing font and invalid timestamps fail explicitly instead of returning a misleading report", () => {
  assert.throws(() => createVendorComparisonPdf(comparison(), "", generatedAt), /font is unavailable/);
  assert.throws(() => createVendorComparisonPdf(comparison(), font, "invalid timestamp"), /timestamp is invalid/);
});

test("recorded experimental scenarios retain their alternatives, checks and actual execution provenance", () => {
  const report = comparison();
  report.finding_scenarios = [{ scenario_id: crypto.randomUUID(), case_id: report.case_id, finding_id: report.findings[0].finding_id,
    analysis_job_id: report.analysis_job_id, status: "DRAFT", title: "Recorded requirement clarification scenario",
    baseline: { description: "The recorded source requirements differ.", assumptions: ["A reviewer must confirm the authorized baseline."],
      evidence: [{ document_id: report.findings[0].evidence[0].document_id, page_number: 1, excerpt: "Minimum RAM: 16 GB" }] },
    alternatives: [{ title: "Seek the authorized amendment", change: "Request the missing change record.", expected_effect: "The reviewer can evaluate the requirement basis.",
      limitations: ["This does not establish full compliance."], evidence: [{ document_id: report.findings[0].evidence[0].document_id, page_number: 1, excerpt: "Minimum RAM: 16 GB" }] }],
    deterministic_checks: [{ check_type: "MEMORY_BASELINE", status: "CONCERN", description: "Two cited requirements differ.", observations: { recorded_values: [16, 32] } }],
    remaining_uncertainties: ["The current authority for the change has not been confirmed."], ai_execution: jobResource().ai_execution, created_at: generatedAt }];
  const before = JSON.stringify(report);
  const doc = createVendorComparisonPdf(report, font, generatedAt);
  assert.equal(Buffer.from(doc.output("arraybuffer")).subarray(0, 5).toString("ascii"), "%PDF-");
  assert.ok(doc.getNumberOfPages() >= 3);
  assert.equal(JSON.stringify(report), before);
});
