import React from "react";
import type { FindingScenario } from "./findingScenarios";
import type { DocumentResource } from "./contracts";

export function FindingScenarioPanel({ findingId, scenarios, documents, disabled, canGenerate, onGenerate }: {
  findingId: string; scenarios: FindingScenario[]; documents: DocumentResource[]; disabled: boolean; canGenerate: boolean;
  onGenerate?: (findingIds: string[], assumptions: string[]) => void;
}) {
  function evidence(refs: FindingScenario["baseline"]["evidence"]) {
    return <details><summary>Source evidence</summary>{refs.map((ref,index) => <div className="evidence-card" key={index}>
      <strong>{documents.find(doc => doc.document_id === ref.document_id)?.filename ?? "Document unavailable"} · Page {ref.page_number}</strong><blockquote>{ref.excerpt}</blockquote>
    </div>)}</details>;
  }
  return <section className="finding-scenario-panel">
    {scenarios.map(scenario => <article className="finding-scenario-result" key={scenario.scenario_id}>
      <div className="split"><h5>{scenario.title}</h5><span className="proposal-outcome">{scenario.status}</span></div>
      <h6>Current situation</h6><p>{scenario.baseline.description}</p>
      {!!scenario.baseline.assumptions.length && <><h6>Assumptions</h6><ul>{scenario.baseline.assumptions.map(item => <li key={item}>{item}</li>)}</ul></>}
      {evidence(scenario.baseline.evidence)}
      {scenario.alternatives.map((alternative,index) => <section className="scenario-alternative" key={index}>
        <h6>{alternative.title}</h6><p><strong>What changes:</strong> {alternative.change}</p><p><strong>Possible effect:</strong> {alternative.expected_effect}</p>
        {!!alternative.limitations.length && <><strong>Conditions and limits</strong><ul>{alternative.limitations.map(item => <li key={item}>{item}</li>)}</ul></>}
        {evidence(alternative.evidence)}
      </section>)}
      {!!scenario.deterministic_checks.length && <><h6>Calculated and evidence checks</h6>{scenario.deterministic_checks.map((check,index) => <section className="scenario-check" key={index}>
        <strong>{check.check_type.replaceAll("_", " ")} · {check.status}</strong><p>{check.description}</p>
        {!!Object.keys(check.observations).length && <details><summary>Check inputs and observations</summary><dl className="metadata">{Object.entries(check.observations).map(([key,value]) => <React.Fragment key={key}>
          <dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
        </React.Fragment>)}</dl></details>}
      </section>)}</>}
      {!!scenario.remaining_uncertainties.length && <><h6>Still requires review</h6><ul>{scenario.remaining_uncertainties.map(item => <li key={item}>{item}</li>)}</ul></>}
      <details><summary>Scenario provenance</summary><p>{scenario.ai_execution.provider} / {scenario.ai_execution.model} · {scenario.created_at}</p><code>{scenario.scenario_id}</code>
        <p>AI execution: <code>{scenario.ai_execution.execution_id}</code></p><p>Evidence checks: {scenario.ai_execution.evidence_checks.passed} / {scenario.ai_execution.evidence_checks.checked}</p>
      </details>
    </article>)}
    <form onSubmit={event => { event.preventDefault(); const raw = String(new FormData(event.currentTarget).get("assumptions") ?? "");
      onGenerate?.([findingId], raw.split("\n").map(item => item.trim()).filter(Boolean)); }}>
      <label className="field"><span>Additional assumptions for this finding (optional)</span><textarea name="assumptions" rows={2} maxLength={2000} disabled={disabled || !canGenerate} placeholder="One assumption per line. Assumptions remain subject to review." /></label>
      <button className="secondary" disabled={disabled || !canGenerate || !onGenerate}>{scenarios.length ? "Generate another what-if draft" : "Generate finding-based simulation"}</button>
    </form>
  </section>;
}
