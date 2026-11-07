"""Evaluation conclusions compare recorded decisions with verified evidence checks."""
import re
from app.services.evidence.supplier_readiness import unique_records, assess_requirement, verified, contains_identity


def evaluate(output, validator, criteria_ids, supplier_ids, report_id, reference_date, check_types):
    unique_records(output)
    criteria = {c.criterion_id: c for c in output.criteria}
    refs = {c.criterion_id: validator.validate(c.evidence, criteria_ids) for c in output.criteria}
    observations = {(o.criterion_id, o.supplier_ref): o for o in output.observations}
    observed_refs = {(o.criterion_id, o.supplier_ref): validator.validate(o.evidence, supplier_ids) for o in output.observations}
    items = []
    for statement in output.decisions:
        criterion = criteria[statement.criterion_id]
        key = (statement.criterion_id, statement.supplier_ref)
        report_refs = validator.validate(statement.evidence, {report_id})
        assessed = assess_requirement(criterion, observations.get(key), statement.supplier_ref, refs[criterion.criterion_id],
            observed_refs.get(key, []), validator.pages, reference_date, False, supplier_ids)
        evidence_assessment = {"VERIFIED": "SUPPORTED", "NON_COMPLIANT": "UNSUPPORTED", "MISSING": "MISSING", "NEEDS_REVIEW": "AMBIGUOUS", "NOT_APPLICABLE": "NOT_APPLICABLE"}[assessed["readiness_status"]]
        consistency = "NEEDS_REVIEW"
        # A missing model observation cannot prove that a document does not exist.
        # Only explicit, verified substantive comparisons justify an inconsistency.
        report_text = " ".join(r["excerpt"] for r in report_refs)
        negative = bool(re.search(r"\bnon[ _-]compliant\b|\brejected\b|\bfailed\b|\bmissing\b|\bnot provided\b", report_text, re.I))
        positive = bool(re.search(r"\bcompliant\b|\bpassed\b", re.sub(r"\bnon[ _-]compliant\b", "", report_text, flags=re.I), re.I))
        recorded_supported = contains_identity(report_text, statement.supplier_ref) and negative != positive and (
            (negative and statement.recorded_decision == "NON_COMPLIANT") or (positive and statement.recorded_decision == "COMPLIANT"))
        topic = {"WARRANTY_MONTHS": r"\bwarranty\b", "RAM_GB": r"\bRAM\b|\bmemory\b", "DELIVERY_DAYS": r"\bdelivery\b", "QUANTITY": r"\bquantity\b"}.get(criterion.metric)
        criterion_named = contains_identity(report_text, criterion.criterion_id) or bool(topic and re.search(topic, report_text, re.I))
        if verified(report_refs) and recorded_supported and criterion_named and "DECISION_CONSISTENCY" in check_types and evidence_assessment in {"SUPPORTED", "UNSUPPORTED"} and statement.recorded_decision in {"COMPLIANT", "NON_COMPLIANT"}:
            supported = evidence_assessment == "SUPPORTED"
            recorded = statement.recorded_decision == "COMPLIANT"
            consistency = "CONSISTENT" if supported == recorded else "INCONSISTENT"
        items.append({"supplier_ref": statement.supplier_ref, "criterion_id": criterion.criterion_id,
            "criterion_description": criterion.description, "recorded_decision": statement.recorded_decision,
            "evidence_assessment": evidence_assessment, "consistency_result": consistency,
            "explanation": assessed["explanation"] + (" The recorded decision differs; an authorized person should re-evaluate it." if consistency == "INCONSISTENT" else ""),
            "evidence": assessed["evidence"] + report_refs,
            "recommended_action": "REQUEST_REEVALUATION" if consistency == "INCONSISTENT" else "NONE" if consistency == "CONSISTENT" else "HUMAN_REVIEW"})
    # Criteria with no report statement remain explicitly unresolved, not silently clean.
    return items
