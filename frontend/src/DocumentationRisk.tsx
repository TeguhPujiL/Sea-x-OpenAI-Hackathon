import React from "react";
import type { DocumentationRisk as Risk } from "./vendorAssessmentData";
export function DocumentationRisk({ risk }: { risk: Risk }) {
  return <span className={`documentation-risk risk-${risk.color}`} title={risk.reasons.join(" ")}>
    <span className="risk-light" aria-hidden="true" />{risk.color[0].toUpperCase() + risk.color.slice(1)} · {risk.score === null ? "Unscored" : `${risk.score} finding${risk.score === 1 ? "" : "s"}`} · {risk.label}
  </span>;
}
