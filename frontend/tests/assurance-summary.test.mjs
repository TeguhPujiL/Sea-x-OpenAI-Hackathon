import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { assuranceSummary, reviewLabels } from "../src/assuranceSummaryData.ts";
import { AssuranceSummary } from "../src/AssuranceSummary.tsx";
import { emptyResources } from "../src/workflow.ts";
import { IDs, caseResource, documentResource, jobResource, findingResource, repairResource, reviewResource } from "./fixtures.mjs";

const proposal = () => ({ ...documentResource("SUPPLIER_QUOTATION"), document_id: IDs.actor, filename: "vendor-a-proposal.pdf" });
function recorded(clean = false) {
  const job = jobResource("COMPLETED", clean);
  job.ai_execution.input_document_ids.push(IDs.actor);
  return { ...emptyResources(), caseResource: caseResource(), documents: [documentResource(), documentResource("TECHNICAL_SPECIFICATION"), proposal()], job,
    findings: clean ? [] : [findingResource()], repair: clean ? null : repairResource() };
}
const markup = resources => renderToStaticMarkup(React.createElement(AssuranceSummary, { resources }));

test("clean analysis reports its actual counts and coverage without a compliance approval", () => {
  const r = recorded(true), summary = assuranceSummary(r), html = markup(r);
  assert.equal(summary.requirementCount, 2);
  assert.equal(summary.findingCount, 0);
  assert.match(summary.proposals[0].coverage, /Included; no finding cites/);
  assert.match(html, /No integrity findings returned/);
  assert.match(html, /Vendor requirement compliance: not determined by this analysis/);
  assert.doesNotMatch(html, /proposal satisfies|vendor is compliant|all requirements are met/i);
  assert.match(html, /vendor-a-proposal.pdf/);
});
test("a proposal uploaded after analysis is shown as outside that analysis", () => {
  const r = recorded(true);
  r.job.ai_execution.input_document_ids = [IDs.tor, IDs.spec];
  assert.equal(assuranceSummary(r).proposals[0].coverage, "Not included in this analysis");
  r.documents[2].deleted_at = "2026-11-07T03:00:00Z";
  assert.equal(assuranceSummary(r).proposals.length, 0);
});
test("finding evidence links vendor gaps to the recorded source and page", () => {
  const r = recorded();
  r.findings[0].evidence.push({ document_id: IDs.actor, page_number: 1, excerpt: "Quoted RAM: 16 GB", verification_status: "VERIFIED" });
  const html = markup(r);
  assert.equal(assuranceSummary(r).proposals[0].findings[0].finding_id, IDs.finding);
  assert.match(html, new RegExp(`href="#assurance-finding-${IDs.finding}"`));
  assert.match(html, /Conflicting minimum RAM requirements/);
  assert.match(html, /vendor-a-proposal.pdf · Page 1/);
  assert.match(html, /Quoted RAM: 16 GB/);
  assert.match(html, /high severity · open · verified evidence/);
});
test("recorded decisions and reviewer conclusions are preserved without treating draft approval as vendor approval", () => {
  const r = recorded();
  const review = { ...reviewResource(), decision_reason: "Reviewed proposal meets the RAM requirement in the cited evidence." };
  r.reviews = [review];
  const html = markup(r);
  assert.match(html, /Repair draft approved/);
  assert.match(html, /Reviewed proposal meets the RAM requirement in the cited evidence/);
  assert.match(html, /Reviewer conclusion, as recorded/);
  assert.match(html, /Vendor requirement compliance: not determined/);
  assert.match(html, new RegExp(review.reviewer.display_name));
  for (const [decision, label] of Object.entries(reviewLabels)) {
    r.reviews = [{ ...review, decision }];
    assert.ok(markup(r).includes(label));
  }
});
test("historical and cross-case review conclusions cannot appear as the current review", () => {
  const r = recorded();
  const review = reviewResource();
  r.reviews = [{ ...review, case_id: IDs.actor }, { ...review, repair_proposal_id: IDs.actor }];
  assert.equal(assuranceSummary(r).review, null);
  r.reviews = [review]; r.findings[0].analysis_job_id = IDs.retry;
  assert.equal(assuranceSummary(r).review, null);
});
test("FAILED, NEEDS_REVIEW and processing states never produce a clean conclusion", () => {
  for (const status of ["FAILED", "NEEDS_REVIEW", "QUEUED", "PROCESSING"]) {
    const r = recorded(true); r.job = jobResource(status, true);
    const summary = assuranceSummary(r), html = markup(r);
    assert.notEqual(summary.headline, "No integrity findings returned");
    assert.doesNotMatch(html, /completed analysis returned no integrity findings/i);
    if (status === "NEEDS_REVIEW") assert.match(html, /EVIDENCE_EXCERPT_NOT_FOUND/);
    if (status === "FAILED") assert.equal(summary.findingCount, null);
  }
});
test("failed checks, warnings and missing finding details prevent a reliable conclusion", () => {
  const variants = [r => { r.job.ai_execution.evidence_validation_passed = false; },
    r => { r.job.ai_execution.schema_valid = false; },
    r => { r.job.ai_execution.evidence_checks.failed = 1; },
    r => { r.job.ai_execution = null; },
    r => { r.job.warnings.push({ code: "TEST_WARNING", message: "Synthetic evidence warning" }); }];
  for (const alter of variants) {
    const r = recorded(true); alter(r);
    assert.equal(assuranceSummary(r).headline, "Evidence review required");
  }
  const r = recorded(); r.findings = [];
  assert.equal(assuranceSummary(r).findingCount, 1);
  assert.equal(assuranceSummary(r).missingFindings, true);
  assert.match(markup(r), /Some finding details are unavailable/);
});
test("missing requirement counts are not fabricated as zero and vendor filenames remain text", () => {
  const r = recorded(true); delete r.job.result.requirement_count;
  r.documents[2].filename = '<script>alert("x")</script>.pdf';
  assert.equal(assuranceSummary(r).requirementCount, null);
  assert.match(markup(r), /Not reported/);
  assert.doesNotMatch(markup(r), /<script>/);
  r.job.result.requirement_count = 0;
  assert.equal(assuranceSummary(r).requirementCount, 0);
});
test("empty or foreign case data never contributes a summary or proposal", () => {
  assert.match(markup(emptyResources()), /Create or reopen a case/);
  const r = recorded(); r.documents[2].case_id = IDs.retry; r.job.case_id = IDs.retry;
  const summary = assuranceSummary(r);
  assert.equal(summary.job, null); assert.equal(summary.findings.length, 0); assert.equal(summary.proposals.length, 0);
});
