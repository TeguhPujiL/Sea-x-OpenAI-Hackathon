import React from "react";
import type { Resources } from "./workflow";
import { vendorWorkflow, type SimulationParameters } from "./vendorWorkflowData";
import { DocumentationRisk } from "./DocumentationRisk";
import { VendorGroup, VendorGroups } from "./VendorGroup";
import { FindingScenarioPanel } from "./FindingScenarioPanel";

export function VendorSimulations({ resources, disabled, onRun, onUse, scenarioAvailability = "disabled", scenarioLoadError, onGenerateScenarios, onRepair }: {
  resources: Resources; disabled: boolean; onRun?: (findingIds: string[], parameters: SimulationParameters) => void; onUse?: (simulationId: string) => void;
  scenarioAvailability?: "loading" | "ready" | "disabled" | "error"; scenarioLoadError?: string | null;
  onGenerateScenarios?: (findingIds: string[], assumptions: string[]) => void; onRepair?: () => void;
}) {
  const workflow = vendorWorkflow(resources);
  return <section className="vendor-simulations"><h3>Simulate challenged points by vendor</h3>
    <p>Generate model-assisted what-if scenarios for each challenged finding, grouped by vendor. Scenarios describe the current situation, possible changes, evidence, and remaining uncertainties. Calculations and evidence checks are produced separately by code where inputs support them.</p>
    <p className="muted">Finding-based scenarios use the opt-in proposed v1.2 prototype extension. They are drafts for human review and do not resolve a finding or approve a vendor.</p>
    {scenarioAvailability === "loading" && <p role="status">Loading finding-based scenarios…</p>}
    {scenarioAvailability === "disabled" && <p className="notice warning-notice">Finding-based scenario generation is not enabled in this deployment. Enable and migrate the prototype extension to generate a scenario for every finding. Existing RAM calculations remain available.</p>}
    {scenarioAvailability === "error" && <p className="notice error-notice">Could not load model scenarios: {scenarioLoadError}. Refresh resources before generating another scenario.</p>}
    <p className="muted">Shared points reuse their recorded challenges and results across vendor groups. Changing inputs creates a new immutable simulation.</p>
    <VendorGroups label="Simulate vendor groups">{workflow.groups.map(vendor => {
      const points = [...new Map(vendor.packages.flatMap(pack => pack.points).map(point => [point.finding.finding_id, point])).values()];
      const eligible = points.filter(point => point.support.supported && point.canChallenge && point.challenges.some(c => c.status !== "CLOSED"));
      const modelEligible = points.filter(point => point.canChallenge && point.challenges.some(c => c.status !== "CLOSED"));
      return <VendorGroup key={vendor.id} title={vendor.label} summary={<DocumentationRisk risk={vendor.risk} />}>
        <button className="primary" disabled={disabled || scenarioAvailability !== "ready" || !onGenerateScenarios || !modelEligible.length}
          onClick={() => onGenerateScenarios?.(modelEligible.map(point => point.finding.finding_id), [])}>Generate scenarios for all challenged points ({modelEligible.length})</button>
        <details className="ram-calculation"><summary>Optional RAM supplier-eligibility calculation</summary>
        <form onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget);
          onRun?.(eligible.map(point => point.finding.finding_id), { baseline: Number(form.get("baseline")), alternative: Number(form.get("alternative")), version: String(form.get("supplier_data_version")) }); }}>
          <fieldset disabled={disabled || !eligible.length || !onRun}><legend>RAM scenario for {vendor.label}</legend><div className="vendor-scenario-grid">
            <label className="field"><span>Baseline minimum RAM (GB)</span><input name="baseline" type="number" min={1} step={1} defaultValue={32} required /></label>
            <label className="field"><span>Alternative minimum RAM (GB)</span><input name="alternative" type="number" min={1} step={1} defaultValue={16} required /></label>
          </div><label className="field"><span>Supplier data version</span><input name="supplier_data_version" defaultValue="synthetic-suppliers-v1" required /></label></fieldset>
          <button className="primary" disabled={disabled || !eligible.length || !onRun}>Simulate all supported challenges for {vendor.label} ({eligible.length})</button>
        </form>
        </details>
        {!points.length && <p>No open challenge points for this vendor.</p>}
        {vendor.packages.map(pack => <section className="vendor-package" key={pack.source}><h5>{pack.source === "uploaded" ? "Uploaded documents" : `${pack.source} package`}</h5>
          {pack.points.map(point => <article className="vendor-concern" key={point.finding.finding_id}><h5>{point.finding.title}</h5>
            {point.shared && <span className="shared-point-label">Shared point</span>}
            <p>{!point.canChallenge ? "Evidence or case state requires review" : !point.challenges.some(c => c.status !== "CLOSED") ? "Generate an active challenge first" : "Ready for a finding-based scenario"}</p>
            <FindingScenarioPanel findingId={point.finding.finding_id} documents={resources.documents}
              scenarios={(resources.findingScenarioHistory ?? []).filter(scenario => scenario.finding_id === point.finding.finding_id && scenario.analysis_job_id === resources.job?.job_id && scenario.case_id === resources.caseResource?.case_id)}
              disabled={disabled || scenarioAvailability !== "ready"} canGenerate={point.canChallenge && point.challenges.some(c => c.status !== "CLOSED")} onGenerate={onGenerateScenarios} />
            <p className="muted">Additional deterministic RAM calculation: {point.support.reason}</p>
            {point.simulations.map(simulation => <details key={simulation.simulation_id}><summary>Recorded simulation · {simulation.created_at}</summary>
              <dl className="metadata"><dt>Baseline minimum RAM</dt><dd>{simulation.input_snapshot.baseline.minimum_ram_gb} GB</dd><dt>Alternative minimum RAM</dt><dd>{simulation.input_snapshot.alternative.minimum_ram_gb} GB</dd>
                <dt>Engine</dt><dd>{simulation.engine_version}</dd><dt>Supplier data version</dt><dd>{simulation.supplier_data_version ?? "Not exposed by server (G07)"}</dd></dl>
              <div className="table-scroll"><table className="metrics-table"><caption>Recorded RAM eligibility result</caption><thead><tr><th>Scenario</th><th>Eligible suppliers</th><th>Lowest total offer (IDR)</th></tr></thead><tbody>
                {(["baseline", "alternative", "delta"] as const).map(key => <tr key={key}><th>{key}</th><td>{simulation.result[key].eligible_supplier_count}</td><td>{new Intl.NumberFormat("en-GB").format(simulation.result[key].lowest_total_offer_idr)}</td></tr>)}
              </tbody></table></div><p>{simulation.interpretation}</p><code>{simulation.simulation_id}</code>
              <button className="secondary" disabled={disabled || !onUse} onClick={() => onUse?.(simulation.simulation_id)}>Use this simulation in Repair</button>
            </details>)}
          </article>)}
        </section>)}
        <p className="muted">Illustrative supplier eligibility only. The result does not resolve other documentation concerns or establish actual savings or loss.</p>
      </VendorGroup>;
    })}</VendorGroups>
    <button className="primary" disabled={disabled || !onRepair} onClick={onRepair}>Continue to Repair revised evidence</button>
  </section>;
}
