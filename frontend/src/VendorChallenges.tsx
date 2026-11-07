import React from "react";
import type { Resources } from "./workflow";
import { vendorWorkflow } from "./vendorWorkflowData";
import { DocumentationRisk } from "./DocumentationRisk";
import { VendorGroup, VendorGroups } from "./VendorGroup";

export function VendorChallenges({ resources, disabled, onGenerate, onSimulate }: {
  resources: Resources; disabled: boolean; onGenerate?: (findingId: string, requested: string[]) => void; onSimulate: () => void;
}) {
  const workflow = vendorWorkflow(resources);
  return <section className="vendor-challenges"><h3>Points to challenge by vendor</h3>
    <p>Shared points appear for every affected vendor. Each point retains one finding and its recorded challenge history.</p>
    <VendorGroups label="Challenge vendor groups">{workflow.groups.map(vendor => <VendorGroup key={vendor.id} title={vendor.label} summary={<DocumentationRisk risk={vendor.risk} />}>
      {vendor.packages.map(pack => <section className="vendor-package" key={pack.source}>
        <h5>{pack.source === "uploaded" ? "Uploaded documents" : `${pack.source} package`}</h5>
        {!pack.points.length && <p>No open point to challenge for this option. Its documents remain available in Assess.</p>}
        {pack.points.map(point => <article className="vendor-concern" key={point.finding.finding_id}>
          <h5>{point.finding.title}</h5><p>{point.finding.summary}</p>
          {point.shared && <span className="shared-point-label">Shared point · also shown for other vendors</span>}
          <p className="muted">{point.finding.severity} · {point.finding.evidence_status} evidence</p>
          {point.challenges.length ? <><p>{point.challenges.length} recorded challenge(s)</p>{point.challenges.map(challenge => <details key={challenge.challenge_id} open={point.challenges.length === 1}>
            <summary>{challenge.status}: {challenge.question}</summary><p>{challenge.risk_rationale}</p><code>{challenge.challenge_id}</code>
            <p>AI execution: <code>{challenge.ai_execution_id ?? "Not reported"}</code></p>
          </details>)}</> : <form onSubmit={event => { event.preventDefault(); onGenerate?.(point.finding.finding_id,
            new FormData(event.currentTarget).getAll("requested_evidence").map(String)); }}>
            <fieldset disabled={disabled || !point.canChallenge || !onGenerate}><legend>Supporting evidence to request</legend>
              <label className="checkbox"><input type="checkbox" name="requested_evidence" value="TECHNICAL_JUSTIFICATION" defaultChecked />Technical justification</label>
              <label className="checkbox"><input type="checkbox" name="requested_evidence" value="MARKET_COMPARISON" defaultChecked />Market comparison</label>
            </fieldset><button className="secondary" disabled={disabled || !point.canChallenge || !onGenerate}>Generate challenge for this point</button>
          </form>}
          {!point.canChallenge && <p className="inline-warning">Verify this point's evidence and case state before generating a challenge.</p>}
          <p className="muted">Simulation: {point.support.reason}</p>
        </article>)}
      </section>)}
    </VendorGroup>)}</VendorGroups>
    <p className="muted">AI-generated challenges stay DRAFT until human readiness is recorded. Existing records are preserved.</p>
    <button className="primary" disabled={disabled} onClick={onSimulate}>Continue to Simulate</button>
  </section>;
}
