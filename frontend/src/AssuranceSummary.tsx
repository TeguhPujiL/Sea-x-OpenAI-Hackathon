import React from "react";
import { assuranceSummary } from "./assuranceSummaryData";
import type { Resources } from "./workflow";

const human = (value: string) => value.replaceAll("_", " ").toLowerCase();
export function AssuranceSummary({ resources }: { resources: Resources }) {
  const summary = assuranceSummary(resources);
  return <section className="assurance-summary" aria-labelledby="assurance-summary-title">
    <div className="section-title"><h3 id="assurance-summary-title">Assurance summary</h3><span className="eyebrow">Vendor proposal recommendations</span></div>
    <p>Review each proposal's recorded result and recommended next step before making your decision.</p>
    {summary.proposals.length ? <div className="vendor-proposal-results">{summary.proposals.map(proposal => <article className={`vendor-proposal-result vendor-result-${proposal.tone}`} key={proposal.document.document_id} aria-labelledby={`proposal-title-${proposal.document.document_id}`}>
      <div className="split"><h4 id={`proposal-title-${proposal.document.document_id}`}>{proposal.document.filename}</h4><span className={`proposal-outcome outcome-${proposal.tone}`}>{proposal.status}</span></div>
      <p>{proposal.resultSummary}</p>
      <p className="muted">Analysis coverage: {proposal.coverage}</p>
      <div className="proposal-recommendation"><h5>Recommendation: {proposal.recommendation}</h5><ol>{proposal.nextSteps.map(step => <li key={step}>{step}</li>)}</ol></div>
      {!!proposal.findings.length && <div className="proposal-findings"><h5>Findings for this proposal</h5><ul>{proposal.findings.map(f => <li key={f.finding_id}><a href={`#assurance-finding-${f.finding_id}`}>{f.title}</a><p>{f.summary}</p><p className="muted">{human(f.severity)} severity · {human(f.status)}</p>{f.resolution_note && <p>Recorded resolution: {f.resolution_note}</p>}</li>)}</ul></div>}
      {!!proposal.sharedFindings.length && <details><summary>Shared case findings to consider</summary><ul>{proposal.sharedFindings.map(f => <li key={f.finding_id}><a href={`#assurance-finding-${f.finding_id}`}>{f.title}</a> · {human(f.status)}</li>)}</ul></details>}
    </article>)}</div> : <p>No active document is classified as a supplier quotation. Assign that document type in Upload to identify vendor proposals.</p>}
    <p className="summary-scope">Recommendations use the recorded analysis. A proposal with no recorded issues can proceed to further evaluation; confirmation that every mandatory requirement is satisfied requires checking the proposal against those requirements.</p>
    <details className="summary-analysis-context"><summary>Analysis context</summary><h4>{summary.headline}</h4><p>{summary.narrative}</p>
      <dl className="summary-facts"><div><dt>Requirements extracted across the analysis</dt><dd>{summary.requirementCount ?? "Not reported"}</dd></div>
        <div><dt>Findings returned across the analysis</dt><dd>{summary.findingCount ?? "Not available"}</dd></div></dl></details>
    {summary.missingFindings && <p className="inline-warning">Some finding details are unavailable. Refresh resources before relying on this summary.</p>}
    {!!summary.job?.warnings.length && <div className="summary-warnings"><h4>Processing warnings</h4><ul>{summary.job.warnings.map((w,i) => <li key={i}><strong>{w.code}</strong>: {w.message}</li>)}</ul></div>}
    {!!summary.findings.length && <div className="summary-findings"><h4>Recorded findings</h4>{summary.findings.map(finding => <article key={finding.finding_id} id={`assurance-finding-${finding.finding_id}`}>
      <h5>{finding.title}</h5><p className="muted">{human(finding.severity)} severity · {human(finding.status)} · {human(finding.evidence_status)} evidence</p><p>{finding.summary}</p>
      <details><summary>Supporting evidence</summary>{finding.evidence.map((e,i) => {
        const doc = summary.documents.find(d => d.document_id === e.document_id);
        const available = doc && e.page_number >= 1 && e.page_number <= doc.page_count;
        return <div className="evidence-card" key={i}><strong>{doc?.filename ?? "Document unavailable"} · Page {e.page_number}</strong>{available ? <blockquote>{e.excerpt}</blockquote> : <p className="inline-warning">Refresh documents to check this page reference.</p>}<p className="muted">{human(e.verification_status)}</p></div>;
      })}</details></article>)}</div>}
    {summary.job && <details className="summary-source"><summary>Summary source</summary><p>Analysis: <code>{summary.job.job_id}</code> · {human(summary.job.status)}</p>
      {summary.job.ai_execution && <p>AI execution: <code>{summary.job.ai_execution.execution_id}</code></p>}<p>Generated from the loaded server records. Refresh resources for the latest recorded state.</p></details>}
  </section>;
}
