import React from "react";
import { assuranceSummary, reviewLabels } from "./assuranceSummaryData";
import type { Resources } from "./workflow";

const human = (value: string) => value.replaceAll("_", " ").toLowerCase();
export function AssuranceSummary({ resources }: { resources: Resources }) {
  const summary = assuranceSummary(resources);
  return <section className="assurance-summary" aria-labelledby="assurance-summary-title">
    <div className="section-title"><h3 id="assurance-summary-title">Assurance summary</h3><span className="eyebrow">Recorded analysis and review</span></div>
    <h4>{summary.headline}</h4><p>{summary.narrative}</p>
    <dl className="summary-facts"><div><dt>Requirements extracted</dt><dd>{summary.requirementCount ?? "Not reported"}</dd></div>
      <div><dt>Findings returned</dt><dd>{summary.findingCount ?? "Not available"}</dd></div>
      <div><dt>Human review</dt><dd>{summary.review ? "Recorded for selected correction" : "No review recorded for selected correction"}</dd></div></dl>
    <h4>Vendor proposal coverage</h4>
    {summary.proposals.length ? <div className="table-scroll"><table className="metrics-table"><caption>Uploaded supplier quotations in the recorded analysis</caption>
      <thead><tr><th scope="col">Proposal document</th><th scope="col">Analysis coverage</th><th scope="col">Finding references</th></tr></thead>
      <tbody>{summary.proposals.map(({ document, coverage, findings }) => <tr key={document.document_id}><th scope="row">{document.filename}</th><td>{coverage}</td>
        <td>{findings.length ? <ul>{findings.map(f => <li key={f.finding_id}><a href={`#assurance-finding-${f.finding_id}`}>{f.title}</a></li>)}</ul> : "None shown"}</td></tr>)}</tbody></table></div>
      : <p>No active document is classified as a supplier quotation. Assign that document type in Upload to identify vendor proposals.</p>}
    <p className="summary-scope"><strong>Vendor requirement compliance: not determined by this analysis.</strong> The recorded result covers requirement extraction and inconsistencies. It does not provide a compliance verdict for every vendor requirement. An approved repair draft applies to the proposed correction.</p>
    {summary.review && <article className="summary-review"><h4>{reviewLabels[summary.review.decision]}</h4>
      <p>Reviewer conclusion, as recorded:</p><blockquote>{summary.review.decision_reason}</blockquote>
      <p className="muted">{summary.review.reviewer.display_name} · {human(summary.review.reviewer.role)} · <time dateTime={summary.review.created_at}>{new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(new Date(summary.review.created_at))}</time></p>
      <code>{summary.review.review_id}</code></article>}
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
