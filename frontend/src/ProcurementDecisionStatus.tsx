import React from "react";
import type { Resources } from "./workflow";
import { Timestamp } from "./Timestamp";

export interface ProcurementStatusInfo {
  state: "GO" | "NO_GO" | "PENDING" | "UNAVAILABLE" | "LOADING";
  vendorId?: string; recordedAt?: string; detail?: string;
}

/** Only persisted conclusions set GO/NO_GO. A local preference is never a decision. */
export function activeProcurementStatus(resources: Resources): ProcurementStatusInfo {
  if (resources.procurementConclusionError) return { state: "UNAVAILABLE", detail: "Refresh resources to load the saved decision." };
  const conclusion = resources.procurementConclusion;
  if (conclusion && conclusion.case_id === resources.caseResource?.case_id && conclusion.analysis_job_id === resources.job?.job_id) {
    return { state: conclusion.decision, vendorId: conclusion.selected_vendor_id ?? undefined,
      recordedAt: conclusion.created_at, detail: `Recorded by ${conclusion.reviewer.display_name}.` };
  }
  if (!resources.job?.result) return { state: "PENDING", detail: "Complete an assessment before recording a decision." };
  return resources.procurementConclusion === undefined ? { state: "LOADING" }
    : { state: "PENDING", detail: "No GO or NO-GO decision is saved for this assessment." };
}

export function ProcurementDecisionStatus({ status }: { status: ProcurementStatusInfo }) {
  const label = status.state === "GO" ? `GO - Vendor ${status.vendorId}`
    : status.state === "NO_GO" ? "NO-GO - no vendor selected"
    : status.state === "PENDING" ? "Decision pending"
    : status.state === "UNAVAILABLE" ? "Decision status unavailable" : "Loading decision status";
  const color = status.state === "GO" ? "completed" : status.state === "NO_GO" ? "failed" : "needs_review";
  return <div className="procurement-decision-status" role="status">
    <span className={`badge badge-${color}`}>{label}</span>
    {status.recordedAt && <p>Recorded: <Timestamp value={status.recordedAt} /></p>}
    {status.detail && <p className="muted">{status.detail}</p>}
  </div>;
}
