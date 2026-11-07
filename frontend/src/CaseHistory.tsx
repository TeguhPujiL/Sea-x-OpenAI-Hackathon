import React, { useState } from "react";
import type { CaseResource } from "./contracts";
import { caseHistoryPage } from "./history";
import { latestActivity, stepActivity, type HistoryActivity } from "./historyActivity";
import { Timestamp } from "./Timestamp";
import { ProcurementDecisionStatus } from "./ProcurementDecisionStatus";
export function CaseHistory({ cases, activity = {}, recentIds, activeId, loading, error, disabled, onOpen, onRefresh, onClose, onDelete }: {
  cases: CaseResource[]; recentIds: string[]; activeId: string | null; loading: boolean;
  activity?: HistoryActivity;
  onDelete?: (value: CaseResource) => void;
  error: string | null; disabled: boolean; onOpen: (id: string) => void; onRefresh: () => void; onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [recentOnly, setRecentOnly] = useState(false);
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const categories = [...new Set(cases.filter(c => !c.deleted_at).map(c => c.category))].sort();
  const result = caseHistoryPage(cases, recentIds, { query, category, recentOnly, page }, activity);
  const items = result.items;
  return <section className="panel case-history" aria-label="Case history">
    <div className="split"><div><h2>Case history</h2><p>Reopen an available case to view its documents, analysis, and audit history.</p></div>
      <button className="quiet" onClick={onClose}>Close history</button></div>
    <div className="history-controls"><label className="field"><span>Search cases</span><input value={query} onChange={e => { setQuery(e.target.value); setPage(1); }} placeholder="Case title, number, or ID" /></label>
      <label className="field"><span>Category</span><select value={category} onChange={e => { setCategory(e.target.value); setPage(1); }}><option value="">All categories</option>{categories.map(value => <option key={value} value={value}>{value.replaceAll("_", " ").toLowerCase()}</option>)}</select></label>
      <label className="checkbox"><input type="checkbox" checked={recentOnly} onChange={e => { setRecentOnly(e.target.checked); setPage(1); }} />Recently opened only</label>
      <button className="secondary" onClick={onRefresh} disabled={loading || disabled}>Refresh cases</button></div>
    <p className="muted">Most recently updated cases appear first, with 5 cases per page. Ordering includes recorded workflow activity. Times use your local time zone; hover to see the saved UTC timestamp.</p>
    {loading ? <p role="status">Loading case history…</p> : error ? <p role="alert" className="inline-warning">{error}</p> : !items.length ? <p>No matching cases available.</p> :
      <ul className="history-list">{items.map(c => <li key={c.case_id}><div><strong>{c.title}</strong><p>{c.case_number} · {c.case_status.replaceAll("_", " ").toLowerCase()}{recentIds.includes(c.case_id) ? " · Recently opened" : ""}</p><p className="history-updated">Last updated: <Timestamp value={c.updated_at} /></p><code>{c.case_id}</code></div>
        <div className="history-activity"><ProcurementDecisionStatus status={activity[c.case_id]?.procurementStatus ?? {
          state: "UNAVAILABLE", detail: activity[c.case_id]?.error ?? "Refresh cases to load the saved decision status.",
        }} /><p><strong>{activity[c.case_id] && !activity[c.case_id].error ? "Latest activity" : "Case updated"}</strong><br /><Timestamp value={latestActivity(c, activity[c.case_id])} /></p>
          <details><summary>Step timestamps</summary>
            {!activity[c.case_id] || activity[c.case_id].error ? <p role="status">Step history unavailable. {activity[c.case_id]?.error ?? "Refresh cases to load recorded activity."}</p> :
              <ol className="history-steps">{stepActivity(activity[c.case_id]).map((step, index) => <li key={step.name}><strong>{String(index + 1).padStart(2, "0")} · {step.name}</strong>
                {step.latest ? <><Timestamp value={step.latest} /><details><summary>{step.events.length} recorded {step.events.length === 1 ? "event" : "events"}</summary><ul>{step.events.map(event => <li key={event.event_id}><span>{event.event_type.replaceAll("_", " ").toLowerCase()}</span><Timestamp value={event.occurred_at} /></li>)}</ul></details></> : <span>No action recorded</span>}
              </li>)}</ol>}
          </details></div>
        <div className="button-row"><button className="secondary" onClick={() => onOpen(c.case_id)} disabled={disabled || c.case_id === activeId}>{c.case_id === activeId ? "Current case" : "Open case"}</button>{onDelete && <button className="quiet delete-document" disabled={disabled} onClick={() => onDelete(c)} aria-label={`Delete case ${c.title}`}>Delete case</button>}</div></li>)}</ul>}
    {!loading && !error && result.total > 0 && <nav className="button-row history-pagination" aria-label="Case history pages">
      <button className="secondary" disabled={disabled || result.page <= 1} onClick={() => setPage(result.page - 1)}>Previous</button>
      <span role="status" aria-live="polite">Page {result.page} of {result.pages} · {result.total} cases</span>
      <button className="secondary" disabled={disabled || result.page >= result.pages} onClick={() => setPage(result.page + 1)}>Next</button>
    </nav>}
  </section>;
}
