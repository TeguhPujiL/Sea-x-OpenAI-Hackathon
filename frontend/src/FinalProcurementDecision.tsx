import React, { useState } from "react";
import type { Resources } from "./workflow";
import type { ProcurementDecision } from "./procurementConclusion";

export function FinalProcurementDecision({ resources, selectedVendorId, selectedVendorLabel, disabled, onConclude }: {
  resources: Resources; selectedVendorId: string | null; selectedVendorLabel: string | null; disabled: boolean;
  onConclude?: (decision: ProcurementDecision, reason: string, confirmed: boolean) => void;
}) {
  const [decision, setDecision] = useState<ProcurementDecision>("GO");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const conclusion = resources.procurementConclusion;
  const ready = resources.procurementConclusion !== undefined && !resources.procurementConclusionError && !!resources.job?.result;
  return <section className="final-procurement-decision" aria-label="Final procurement decision">
    <h3>Conclude the procurement review</h3>
    {conclusion ? <div className="notice info-notice" role="status"><strong>{conclusion.decision === "GO" ? `GO - ${conclusion.selected_vendor_label}` : "NO-GO - no vendor selected"}</strong>
      <p>{conclusion.decision_reason}</p><p>Recorded by {conclusion.reviewer.display_name} on {new Date(conclusion.created_at).toLocaleString()}.</p>
      <p>This saved internal conclusion is final for this assessment.</p></div> : <form onSubmit={event => { event.preventDefault(); onConclude?.(decision, reason.trim(), confirmed); }}>
      {resources.procurementConclusionError && <p className="notice warning-notice" role="status">The saved conclusion could not be loaded: {resources.procurementConclusionError}. Refresh resources before deciding.</p>}
      <fieldset disabled={disabled || !ready || !onConclude}><legend>Final decision</legend>
        <label className="checkbox"><input type="radio" name="procurement_decision" checked={decision === "GO"} onChange={() => setDecision("GO")} />GO - proceed with the selected vendor</label>
        <label className="checkbox"><input type="radio" name="procurement_decision" checked={decision === "NO_GO"} onChange={() => setDecision("NO_GO")} />NO-GO - end without choosing a vendor</label>
        {decision === "GO" ? <><p>{selectedVendorLabel ? `Selected: ${selectedVendorLabel}` : "Select a vendor above before recording GO."}</p>
          <label className="checkbox"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />I reviewed this vendor's price, specifications, documentation, repair outcomes and any remaining concerns.</label></> : <p>No vendor will be selected in the final decision.</p>}
        <label className="field"><span>Decision reason</span><textarea required minLength={20} maxLength={4000} rows={3} value={reason}
          onChange={event => setReason(event.target.value)} placeholder="Explain the decision and how any remaining concerns were considered." /></label>
        <button className="primary" disabled={reason.trim().length < 20 || reason.trim().split(/\s+/).length < 4 || decision === "GO" && (!selectedVendorId || !confirmed)}>Record {decision === "GO" ? "GO" : "NO-GO"} decision</button>
      </fieldset>
      {!ready && !resources.procurementConclusionError && <p className="muted">Load the current assessment and its saved decision before concluding.</p>}
    </form>}
    <p className="muted">This concludes the internal procurement review. It does not issue statutory approval or change the v1.1 case approval status.</p>
  </section>;
}
