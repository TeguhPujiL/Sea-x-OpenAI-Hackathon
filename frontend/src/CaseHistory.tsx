import React, { useState } from "react";
import type { CaseResource } from "./contracts";
import { orderCases } from "./history";
export function CaseHistory({ cases, recentIds, activeId, loading, error, disabled, onOpen, onRefresh, onClose }: {
  cases: CaseResource[]; recentIds: string[]; activeId: string | null; loading: boolean;
  error: string | null; disabled: boolean; onOpen: (id: string) => void; onRefresh: () => void; onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [recentOnly, setRecentOnly] = useState(false);
  const items = orderCases(cases, recentIds).filter(c => (!recentOnly || recentIds.includes(c.case_id))
    && `${c.title} ${c.case_number} ${c.case_id}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <section className="panel case-history" aria-label="Case history">
    <div className="split"><div><h2>Case history</h2><p>Reopen an available case to view its documents, analysis, and audit history.</p></div>
      <button className="quiet" onClick={onClose}>Close history</button></div>
    <div className="history-controls"><label className="field"><span>Search cases</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Case title, number, or ID" /></label>
      <label className="checkbox"><input type="checkbox" checked={recentOnly} onChange={e => setRecentOnly(e.target.checked)} />Recently opened only</label>
      <button className="secondary" onClick={onRefresh} disabled={loading || disabled}>Refresh cases</button></div>
    <p className="muted">Recently opened cases appear first. Case information is loaded from the server.</p>
    {loading ? <p role="status">Loading case history…</p> : error ? <p role="alert" className="inline-warning">{error}</p> : !items.length ? <p>No matching cases available.</p> :
      <ul className="history-list">{items.map(c => <li key={c.case_id}><div><strong>{c.title}</strong><p>{c.case_number} · {c.case_status.replaceAll("_", " ").toLowerCase()}{recentIds.includes(c.case_id) ? " · Recently opened" : ""}</p><code>{c.case_id}</code></div>
        <button className="secondary" onClick={() => onOpen(c.case_id)} disabled={disabled || c.case_id === activeId}>{c.case_id === activeId ? "Current case" : "Open case"}</button></li>)}</ul>}
  </section>;
}
