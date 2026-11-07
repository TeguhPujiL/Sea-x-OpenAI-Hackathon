import React, { useState } from "react";
import type { CaseResource } from "./contracts";
import { caseHistoryPage } from "./history";
export function CaseHistory({ cases, recentIds, activeId, loading, error, disabled, onOpen, onRefresh, onClose, onDelete }: {
  cases: CaseResource[]; recentIds: string[]; activeId: string | null; loading: boolean;
  onDelete?: (value: CaseResource) => void;
  error: string | null; disabled: boolean; onOpen: (id: string) => void; onRefresh: () => void; onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [recentOnly, setRecentOnly] = useState(false);
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const categories = [...new Set(cases.filter(c => !c.deleted_at).map(c => c.category))].sort();
  const result = caseHistoryPage(cases, recentIds, { query, category, recentOnly, page });
  const items = result.items;
  return <section className="panel case-history" aria-label="Case history">
    <div className="split"><div><h2>Case history</h2><p>Reopen an available case to view its documents, analysis, and audit history.</p></div>
      <button className="quiet" onClick={onClose}>Close history</button></div>
    <div className="history-controls"><label className="field"><span>Search cases</span><input value={query} onChange={e => { setQuery(e.target.value); setPage(1); }} placeholder="Case title, number, or ID" /></label>
      <label className="field"><span>Category</span><select value={category} onChange={e => { setCategory(e.target.value); setPage(1); }}><option value="">All categories</option>{categories.map(value => <option key={value} value={value}>{value.replaceAll("_", " ").toLowerCase()}</option>)}</select></label>
      <label className="checkbox"><input type="checkbox" checked={recentOnly} onChange={e => { setRecentOnly(e.target.checked); setPage(1); }} />Recently opened only</label>
      <button className="secondary" onClick={onRefresh} disabled={loading || disabled}>Refresh cases</button></div>
    <p className="muted">Most recently updated cases appear first, with 5 cases per page. Case information is loaded from the server.</p>
    {loading ? <p role="status">Loading case history…</p> : error ? <p role="alert" className="inline-warning">{error}</p> : !items.length ? <p>No matching cases available.</p> :
      <ul className="history-list">{items.map(c => <li key={c.case_id}><div><strong>{c.title}</strong><p>{c.case_number} · {c.case_status.replaceAll("_", " ").toLowerCase()}{recentIds.includes(c.case_id) ? " · Recently opened" : ""}</p><p className="history-updated">Last updated: <time dateTime={c.updated_at} title={c.updated_at}>{new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(c.updated_at))}</time></p><code>{c.case_id}</code></div>
        <div className="button-row"><button className="secondary" onClick={() => onOpen(c.case_id)} disabled={disabled || c.case_id === activeId}>{c.case_id === activeId ? "Current case" : "Open case"}</button>{onDelete && <button className="quiet delete-document" disabled={disabled} onClick={() => onDelete(c)} aria-label={`Delete case ${c.title}`}>Delete case</button>}</div></li>)}</ul>}
    {!loading && !error && result.total > 0 && <nav className="button-row history-pagination" aria-label="Case history pages">
      <button className="secondary" disabled={disabled || result.page <= 1} onClick={() => setPage(result.page - 1)}>Previous</button>
      <span role="status" aria-live="polite">Page {result.page} of {result.pages} · {result.total} cases</span>
      <button className="secondary" disabled={disabled || result.page >= result.pages} onClick={() => setPage(result.page + 1)}>Next</button>
    </nav>}
  </section>;
}
