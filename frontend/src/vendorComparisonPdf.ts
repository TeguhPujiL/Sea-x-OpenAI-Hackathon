import { jsPDF } from "jspdf";
import type { comparisonData } from "./VendorDecisionSummary";
import type { FindingScenario } from "./findingScenarios";

type Comparison = ReturnType<typeof comparisonData>;
type Color = [number, number, number];
const INK: Color = [29, 54, 59];
const MUTED: Color = [83, 105, 111];
const TEAL: Color = [19, 104, 94];
const LINE: Color = [207, 220, 219];
const riskColor = (color: string): Color => color === "red" ? [151, 44, 43] : color === "green" ? [28, 106, 67] : [133, 92, 14];
const riskFill = (color: string): Color => color === "red" ? [255, 240, 237] : color === "green" ? [235, 247, 239] : [255, 248, 227];

/** Build a static browser-side report from the same comparison shown in Assure.
 * The caller supplies the bundled, licensed Noto Sans font as raw base64.
 * This function performs no network, DOM, storage or API operation.
 */
export function createVendorComparisonPdf(comparison: Comparison, fontBase64: string, generatedAt = new Date().toISOString()): jsPDF {
  if (!fontBase64.trim()) throw new Error("The report font is unavailable. Try downloading the report again.");
  const date = new Date(generatedAt);
  if (!Number.isFinite(date.getTime())) throw new Error("The report generation timestamp is invalid.");
  const doc = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait", compress: true, putOnlyUsedFonts: true });
  doc.addFileToVFS("NotoSans-Regular.ttf", fontBase64);
  doc.addFont("NotoSans-Regular.ttf", "NotoSans", "normal");
  doc.setFont("NotoSans", "normal");
  const glyphs: Record<number, number> | undefined = doc.getFont().metadata?.cmap?.unicode?.codeMap;
  if (!glyphs) throw new Error("The report font could not be loaded. Try downloading the report again.");
  doc.setProperties({ title: "ProcureMind - vendor comparison report", author: "ProcureMind",
    subject: "Recorded documentation risk and vendor preference for human review", keywords: "vendor comparison, documentation review, human assurance" });
  doc.setCreationDate(date);

  const left = 16, width = 178, bottom = 277;
  let y = 27;
  const unsupported = new Set<string>();
  function display(value: unknown): string {
    const raw = value === null || value === undefined ? "Not recorded" : String(value);
    return Array.from(raw.replace(/\r\n?/g, "\n")).map(char => {
      if (char === "\n") return char;
      const code = char.codePointAt(0)!;
      if (code >= 32 && code !== 127 && glyphs![code]) return char;
      const notation = `[U+${code.toString(16).toUpperCase().padStart(4, "0")}]`;
      unsupported.add(notation);
      return notation;
    }).join("");
  }
  function font(size: number, color: Color = INK) {
    doc.setFont("NotoSans", "normal"); doc.setFontSize(size); doc.setTextColor(...color);
  }
  function header() {
    font(11, TEAL); doc.text("PROCUREMIND", left, 13);
    font(8, MUTED); doc.text("VENDOR COMPARISON / HUMAN REVIEW", left + width, 13, { align: "right" });
    doc.setDrawColor(...LINE); doc.setLineWidth(0.25); doc.line(left, 18, left + width, 18);
  }
  function newPage() { doc.addPage(); header(); y = 27; }
  function ensure(height: number) { if (y + height > bottom) newPage(); }
  function lines(value: unknown, size = 9.5, maxWidth = width): string[] {
    font(size); return doc.splitTextToSize(display(value), maxWidth) as string[];
  }
  function paragraph(value: unknown, options: { size?: number; color?: Color; indent?: number; after?: number } = {}) {
    const size = options.size ?? 9.5, indent = options.indent ?? 0;
    const lineHeight = size * 0.352778 * 1.45;
    const wrapped = lines(value, size, width - indent);
    ensure(Math.min(2, wrapped.length) * lineHeight);
    for (const line of wrapped) {
      ensure(lineHeight); font(size, options.color ?? INK); doc.text(line, left + indent, y + lineHeight * 0.77); y += lineHeight;
    }
    y += options.after ?? 2.5;
  }
  function heading(value: string, level = 1) {
    const size = level === 1 ? 13 : 10.8;
    const wrapped = lines(value, size), lineHeight = size * 0.352778 * 1.45;
    // Reserve room for the following paragraph, or table header plus first row.
    // This keeps section headings from becoming the final item on a page.
    ensure(Math.min(wrapped.length, 3) * lineHeight + 25);
    y += level === 1 ? 3.5 : 2;
    for (const line of wrapped) { ensure(lineHeight + 7); font(size, TEAL); doc.text(line, left, y + lineHeight * 0.77); y += lineHeight; }
    y += 2.5;
  }
  function field(label: string, value: unknown) { paragraph(`${label}: ${value === null || value === undefined ? "Not recorded" : value}`, { size: 9, after: 1.5 }); }
  function bullet(value: unknown) { paragraph(`- ${display(value)}`, { indent: 2, size: 9, after: 1.8 }); }
  function table(columns: { label: string; width: number }[], rows: { cells: unknown[]; color?: string }[]) {
    const size = 8.5, lineHeight = 4.2, pad = 2;
    const headerLines = columns.map(column => lines(column.label, size, column.width - pad * 2));
    const headHeight = Math.max(...headerLines.map(value => value.length)) * lineHeight + pad * 2;
    function tableHeader() {
      ensure(headHeight + lineHeight + pad * 2);
      doc.setFillColor(235, 242, 241); doc.rect(left, y, width, headHeight, "F");
      let x = left;
      headerLines.forEach((value, index) => { font(size, TEAL); value.forEach((line, n) => doc.text(line, x + pad, y + pad + (n + 0.77) * lineHeight)); x += columns[index].width; });
      y += headHeight;
    }
    tableHeader();
    for (const row of rows) {
      const values = row.cells.map((cell, index) => lines(cell, size, columns[index].width - pad * 2));
      const count = Math.max(1, ...values.map(value => value.length));
      let offset = 0;
      while (offset < count) {
        if (bottom - y < lineHeight + pad * 2) { newPage(); tableHeader(); }
        const capacity = Math.max(1, Math.floor((bottom - y - pad * 2) / lineHeight));
        const take = Math.min(capacity, count - offset), rowHeight = take * lineHeight + pad * 2;
        doc.setFillColor(...(row.color ? riskFill(row.color) : [255, 255, 255] as Color));
        doc.rect(left, y, width, rowHeight, "F");
        let x = left;
        values.forEach((value, index) => {
          font(size, index === 1 && row.color ? riskColor(row.color) : INK);
          value.slice(offset, offset + take).forEach((line, n) => doc.text(line, x + pad, y + pad + (n + 0.77) * lineHeight));
          x += columns[index].width;
        });
        doc.setDrawColor(...LINE); doc.setLineWidth(0.15); doc.line(left, y + rowHeight, left + width, y + rowHeight);
        y += rowHeight; offset += take;
        if (offset < count) { newPage(); tableHeader(); }
      }
    }
    y += 4;
  }

  header();
  paragraph("Vendor comparison report", { size: 22, color: TEAL, after: 3 });
  paragraph("Documentation risk, evidence coverage and recorded preference", { size: 10, color: MUTED, after: 5 });
  const localDate = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Jakarta" }).format(date);
  field("Generated (Asia/Jakarta)", `${localDate} WIB`);
  field("Generated (UTC)", date.toISOString());
  field("Case ID", comparison.case_id);
  field("Analysis job ID", comparison.analysis_job_id);
  field("Analysis status", comparison.analysis_status);
  field("Case / assurance status", `${comparison.case_status ?? "Not recorded"} / ${comparison.assurance_status ?? "Not recorded"}`);

  heading("Current vendor preference");
  field("Preferred vendor", comparison.selected_vendor_label ?? "No current vendor selected");
  if (comparison.procurement_conclusion) {
    const conclusion = comparison.procurement_conclusion;
    heading("Final internal procurement decision", 2);
    field("Decision", conclusion.decision === "GO" ? "GO" : "NO-GO");
    field("Selected vendor", conclusion.selected_vendor_label ?? "None");
    field("Reason", conclusion.decision_reason);
    field("Reviewer", conclusion.reviewer.display_name);
    field("Recorded at (UTC)", conclusion.created_at);
    field("Conclusion ID", conclusion.conclusion_id);
    paragraph("This saved internal conclusion does not issue statutory approval or change the v1.1 case approval status.");
  }
  field("Preference status", comparison.preference_status);
  paragraph(comparison.preference_status === "PROVISIONAL_PREFERENCE_UNRESOLVED_POINTS"
    ? "This preference is provisional. Unresolved findings or processing warnings still require review."
    : "Any selected vendor is a preference for authorized human review, not an award or procurement approval.", { color: MUTED });
  if (comparison.stale_selection) paragraph("The earlier preference is unavailable in this analysis. A currently analyzed vendor must be selected again.", { color: riskColor("yellow") });
  paragraph("Vendor selection does not resolve findings, complete the workflow or change server assurance status.", { size: 9, color: MUTED });

  heading("Vendor score comparison");
  paragraph("Scores count distinct applicable active findings, including shared points. Green: 0 with completed coverage. Yellow: 1-2. Red: 3 or more. Missing or incomplete coverage remains unscored; the colors are review indicators, not eligibility decisions.", { size: 9, color: MUTED });
  if (comparison.vendors.length) table([
    { label: "Vendor", width: 43 }, { label: "Finding score", width: 23 }, { label: "Risk indicator", width: 29 },
    { label: "Analyzed quotations", width: 30 }, { label: "Preference / coverage", width: 53 },
  ], comparison.vendors.map(vendor => ({ color: vendor.risk.color, cells: [vendor.label, vendor.risk.score ?? "Unscored",
    vendor.risk.color.toUpperCase(), vendor.analyzed_quotation_ids.length,
    vendor.id === comparison.selected_vendor_id ? "Preferred for human review" : vendor.selectable ? "Available for human review" : "Analysis coverage incomplete"] })));
  else paragraph("No vendor-labelled supplier quotations are available in the loaded comparison.", { color: MUTED });

  heading("Recorded workflow progress");
  const measureLabels: Record<string, string> = { uploaded_documents: "Uploaded documents", analyzed_documents: "Documents included in analysis",
    extracted_requirements: "Extracted requirements", current_findings: "Current findings", unresolved_findings: "Unresolved findings",
    recorded_challenges: "Recorded current-analysis challenges", recorded_simulations: "Recorded current-analysis simulations",
    recorded_finding_scenarios: "Recorded finding scenarios", repair_status: "Loaded current repair status", loaded_reviews: "Loaded case reviews" };
  table([{ label: "Recorded measure", width: 121 }, { label: "Value", width: 57 }], Object.entries(comparison.progress).map(([key, value]) => ({
    cells: [measureLabels[key] ?? key.replaceAll("_", " "), value ?? (key === "repair_status" ? "Not loaded" : "Not reported")],
  })));
  paragraph("These are counts of loaded records. They do not establish that every challenge, simulation method, evidence revision or human review is complete.", { size: 9, color: MUTED });

  const documents = new Map(comparison.vendors.flatMap(vendor => vendor.packages.flatMap(pack => pack.documents)).map(document => [document.document_id, document]));
  for (const vendor of comparison.vendors) {
    heading(vendor.label);
    paragraph(`${vendor.risk.color.toUpperCase()} - ${vendor.risk.score === null ? "Unscored" : `${vendor.risk.score} active finding(s)`} - ${vendor.risk.label}`, { color: riskColor(vendor.risk.color) });
    vendor.risk.reasons.forEach(bullet);
    field("Recorded open point IDs", vendor.open_point_ids.length ? vendor.open_point_ids.join(", ") : "None recorded");
    const offer = vendor.offer_and_repair_summary;
    heading("Offer facts and original-finding repair result", 2);
    if (!offer.available) paragraph("Source-labelled vendor facts and original repair history are not loaded. Values are not inferred.", { color: MUTED });
    for (const pack of offer.packages) {
      field("Evidence package", pack.source);
      if (!pack.facts.length) paragraph("No explicit labelled offer facts were extracted from the selected documents.", { size: 9, color: MUTED });
      for (const fact of pack.facts) {
        field(fact.label, fact.value);
        paragraph(`Source: ${documents.get(fact.source.document_id)?.filename ?? fact.source.document_id}, page ${fact.source.page_number}`, { size: 8, color: MUTED });
        paragraph(fact.source.excerpt, { size: 8, indent: 2, after: 3 });
      }
      field("Newly included vendor documents", pack.newly_included_document_ids.length);
    }
    field("Current reassessment result", offer.current_assessment);
    field("Original finding analysis", offer.initial_analysis_job_id ?? "Not loaded");
    if (offer.available && !offer.original_findings.length) paragraph("No original finding is linked to this vendor in the loaded baseline.", { size: 9, color: MUTED });
    for (const original of offer.original_findings) {
      paragraph(original.title, { size: 10, color: TEAL });
      field("Original finding status", original.status);
      field("Repair outcome", original.outcome);
      for (const repair of original.repairs) {
        field("Repair proposal", `${repair.status} - ${repair.repair_proposal_id}`);
        field("Original text", repair.before_text); field("Proposed repair", repair.proposed_text); field("Justification", repair.justification);
      }
      for (const review of original.reviews) field(`Review ${review.decision}`, review.decision_reason);
    }
    paragraph("A clean reassessment, a repair proposal and a formally resolved finding are distinct records.", { size: 9, color: MUTED });
    for (const pack of vendor.packages) {
      heading(`${pack.source === "uploaded" ? "Uploaded documents" : `${pack.source} package`}`, 2);
      field("Recorded package status", pack.status);
      field("Package finding score", pack.risk.score === null ? "Unscored" : `${pack.risk.score} (${pack.risk.color.toUpperCase()})`);
      field("Direct finding IDs", pack.finding_ids.length ? pack.finding_ids.join(", ") : "None recorded");
      field("Shared finding IDs", pack.shared_finding_ids.length ? pack.shared_finding_ids.join(", ") : "None recorded");
      if (!pack.documents.length) paragraph("No vendor documents loaded for this package.", { size: 9, color: MUTED });
      for (const document of pack.documents) {
        ensure(18);
        paragraph(document.filename, { size: 9.5, color: TEAL, after: 1.5 });
        field("Document ID", document.document_id);
        field("Type / processing", `${document.document_type} / ${document.processing_status}`);
        field("Included in recorded analysis", document.included_in_analysis ? "Yes" : "No");
        paragraph(`SHA-256: ${document.sha256}`, { size: 8, color: MUTED, after: 3 });
      }
    }
  }

  heading("Recorded findings and cited source evidence");
  paragraph("The inventory above covers vendor-linked documents in this comparison. Other case evidence is identified below through source document IDs. A cited document can support a concern rather than establish that a vendor is defective.", { size: 9, color: MUTED });
  if (!comparison.findings.length) paragraph("No current finding details were loaded. This alone does not establish full vendor compliance.", { color: MUTED });
  comparison.findings.forEach((finding, index) => {
    heading(`${index + 1}. ${finding.title}`, 2);
    field("Finding ID", finding.finding_id);
    field("Status / severity / evidence", `${finding.status} / ${finding.severity} / ${finding.evidence_status}`);
    if (!finding.evidence.length) paragraph("No source citations are recorded for this finding.", { size: 9, color: MUTED });
    for (const ref of finding.evidence) {
      ensure(17);
      paragraph(`Source: ${documents.get(ref.document_id)?.filename ?? "Case evidence document"}`, { size: 9, color: TEAL, after: 1.5 });
      field("Document ID / page", `${ref.document_id} / ${ref.page_number}`);
      field("Citation verification", ref.verification_status);
      paragraph("Recorded excerpt:", { size: 8.5, color: MUTED, after: 0.5 });
      paragraph(ref.excerpt, { size: 9, indent: 3, after: 4 });
    }
  });

  const scenarios = (comparison as Comparison & { finding_scenarios?: FindingScenario[] }).finding_scenarios ?? [];
  if (scenarios.length) {
    heading("Recorded finding-based what-if drafts");
    paragraph("Experimental scenarios remain drafts for human review. Alternatives describe possible changes, not guaranteed outcomes. Deterministic checks and AI narrative are recorded separately; unresolved uncertainties remain visible.", { size: 9, color: MUTED });
    function scenarioCitations(refs: FindingScenario["baseline"]["evidence"]) {
      for (const ref of refs) {
        ensure(16);
        paragraph(`Source: ${documents.get(ref.document_id)?.filename ?? "Case evidence document"}`, { size: 8.5, color: TEAL, after: 1 });
        field("Document ID / page", `${ref.document_id} / ${ref.page_number}`);
        paragraph(ref.excerpt, { size: 8.5, indent: 3, after: 3 });
      }
    }
    scenarios.forEach((scenario, index) => {
      heading(`${index + 1}. ${scenario.title}`, 2);
      field("Scenario ID", scenario.scenario_id);
      field("Finding / analysis job", `${scenario.finding_id} / ${scenario.analysis_job_id}`);
      field("Scenario status / recorded time", `${scenario.status} / ${scenario.created_at}`);
      paragraph("Current situation", { size: 10, color: TEAL });
      paragraph(scenario.baseline.description);
      if (scenario.baseline.assumptions.length) {
        paragraph("Recorded assumptions", { size: 9, color: TEAL }); scenario.baseline.assumptions.forEach(bullet);
      }
      scenarioCitations(scenario.baseline.evidence);
      scenario.alternatives.forEach((alternative, alternativeIndex) => {
        heading(`Alternative ${alternativeIndex + 1}: ${alternative.title}`, 2);
        paragraph(`What changes: ${alternative.change}`);
        paragraph(`Possible effect: ${alternative.expected_effect}`);
        if (alternative.limitations.length) {
          paragraph("Conditions and limits", { size: 9, color: TEAL }); alternative.limitations.forEach(bullet);
        }
        scenarioCitations(alternative.evidence);
      });
      if (scenario.deterministic_checks.length) {
        heading("Calculated and evidence checks", 2);
        for (const check of scenario.deterministic_checks) {
          field("Recorded check", `${check.check_type} / ${check.status}`);
          paragraph(check.description);
          for (const [key, value] of Object.entries(check.observations)) {
            paragraph(`${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`, { size: 8.5, indent: 2 });
          }
        }
      }
      if (scenario.remaining_uncertainties.length) {
        paragraph("Still requires review", { size: 10, color: riskColor("yellow") }); scenario.remaining_uncertainties.forEach(bullet);
      }
      heading("Recorded scenario provenance", 2);
      field("Actual provider / model", `${scenario.ai_execution.provider} / ${scenario.ai_execution.model ?? "Not reported"}`);
      field("AI execution ID", scenario.ai_execution.execution_id);
      field("Operation / prompt version", `${scenario.ai_execution.operation} / ${scenario.ai_execution.prompt_version}`);
      field("Schema / evidence validation", `${scenario.ai_execution.schema_valid} / ${scenario.ai_execution.evidence_validation_passed}`);
      const checks = scenario.ai_execution.evidence_checks;
      field("Evidence counters", `${checks.passed} passed / ${checks.checked} checked / ${checks.failed} failed`);
      field("Measured latency", `${scenario.ai_execution.latency_ms} ms`);
      field("Provider-reported token usage", scenario.ai_execution.usage
        ? `${scenario.ai_execution.usage.input_tokens} input / ${scenario.ai_execution.usage.output_tokens} output` : "Not reported");
      field("AI input document IDs", scenario.ai_execution.input_document_ids.join(", "));
    });
  }

  heading("Record references");
  const recordLabels: Record<string, string> = { challenge_ids: "Challenge IDs", simulation_ids: "Simulation IDs",
    finding_scenario_ids: "Finding scenario IDs", repair_proposal_id: "Repair proposal ID", review_ids: "Review IDs" };
  for (const [key, value] of Object.entries(comparison.records)) {
    field(recordLabels[key] ?? key.replaceAll("_", " "), Array.isArray(value) ? value.length ? value.join(", ") : "None loaded" : value ?? "Not loaded");
  }

  heading("Scope and contract limits");
  comparison.limits.forEach(bullet);
  bullet("No audit hash-chain verification is performed by this report. It is a record snapshot for human review, not production certification.");
  if (unsupported.size) paragraph(`Font coverage note: unsupported source characters are preserved as Unicode code-point labels (${[...unsupported].join(", ")}). These labels stand for the original characters; no source text was silently omitted.`, { size: 8, color: MUTED });

  const pages = doc.getNumberOfPages();
  for (let page = 1; page <= pages; page++) {
    doc.setPage(page); doc.setDrawColor(...LINE); doc.setLineWidth(0.2); doc.line(left, 283, left + width, 283);
    font(7.2, MUTED); doc.text("Internal review - not procurement approval", left, 289);
    doc.text(`Page ${page} of ${pages}`, left + width, 289, { align: "right" });
  }
  return doc;
}
