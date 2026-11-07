"""Independent citation, identity and explicit numeric verification for P1."""
import re
from datetime import date
from app.services.documents.pdf import normalize
from app.services.ai.provider import ProviderFailure


def contains_identity(text, supplier):
    return bool(re.search(r"(?<!\w)" + re.escape(supplier) + r"(?!\w)", text, re.I))


def numeric_value(text, metric):
    # Explicit written durations are deterministic too (e.g. three years=36
    # months); unknown wording remains unresolved rather than model-converted.
    words = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
        "twelve": 12, "sixteen": 16, "thirty-six": 36, "thirty six": 36}
    text = re.sub(r"\b(?:" + "|".join(sorted(map(re.escape, words), key=len, reverse=True)) + r")\b(?=[\s-]*(?:months?|years?|GB|days?|units?|items?)\b)",
        lambda match: str(words[match.group().lower()]), text, flags=re.I)
    patterns = {
        "RAM_GB": r"(?<![\d.,-])(\d+)[\s-]*GB\b",
        "WARRANTY_MONTHS": r"(?<![\d.,-])(\d+)[\s-]*(months?|years?)\b",
        "DELIVERY_DAYS": r"(?<![\d.,-])(\d+)[\s-]*days?\b",
        "QUANTITY": r"(?<![\d.,-])(\d+)[\s-]*(?:units?|items?)\b",
    }
    if metric not in patterns:
        return None
    found = re.findall(patterns[metric], text, re.I)
    values = set()
    for value in found:
        if isinstance(value, tuple):
            number, unit = value
            values.add(int(number) * (12 if unit.lower().startswith("year") else 1))
        else:
            values.add(int(value))
    return next(iter(values)) if len(values) == 1 else None


class EvidenceValidator:
    def __init__(self, pages):
        self.pages = pages
        self.checks = {"checked": 0, "passed": 0, "failed": 0}
        self.warnings = []

    def validate(self, citations, allowed):
        refs = []
        for citation in citations:
            key = (str(citation.document_id), citation.page_number)
            excerpt = normalize(citation.excerpt)
            passed = str(citation.document_id) in allowed and key in self.pages and bool(excerpt) and excerpt in self.pages[key]
            self.checks["checked"] += 1
            self.checks["passed" if passed else "failed"] += 1
            if not passed:
                self.warnings.append({"code": "EVIDENCE_EXCERPT_NOT_FOUND", "document_id": str(citation.document_id),
                    "page_number": citation.page_number, "message": "P1 citation or source role could not be independently verified."})
            refs.append({**citation.model_dump(mode="json"), "verification_status": "VERIFIED" if passed else "UNVERIFIED"})
        return refs


def verified(refs):
    return bool(refs) and all(r["verification_status"] == "VERIFIED" for r in refs)


def unique_records(output):
    for values, key in ((output.criteria, lambda x: x.criterion_id),
                        (output.observations, lambda x: (x.criterion_id, x.supplier_ref)),
                        (output.decisions, lambda x: (x.criterion_id, x.supplier_ref))):
        keys = [key(x) for x in values]
        if len(keys) != len(set(keys)):
            raise ProviderFailure("AI_SCHEMA_VALIDATION_FAILED", False)
    ids = {r.criterion_id for r in output.criteria}
    if any(x.criterion_id not in ids for x in [*output.observations, *output.decisions]):
        raise ProviderFailure("AI_SCHEMA_VALIDATION_FAILED", False)


def assess_requirement(criterion, observation, supplier, criterion_refs, observation_refs, pages, reference_date, guidance, supplier_documents=()):
    required_text = " ".join(r["excerpt"] for r in criterion_refs)
    actual_text = " ".join(r["excerpt"] for r in observation_refs)
    status = "NEEDS_REVIEW"
    actual = None
    explanation = "Available evidence requires human interpretation; document presence alone does not establish compliance."
    governing_ok = verified(criterion_refs)
    if criterion.applicable_supplier and criterion.applicable_supplier != supplier:
        if governing_ok and re.search(r"only\s+for\s+" + re.escape(criterion.applicable_supplier) + r"\b", required_text, re.I):
            status = "NOT_APPLICABLE"
            explanation = "The verified criterion explicitly applies only to another supplier."
    elif governing_ok and observation is None:
        status = "MISSING"
        explanation = "No qualifying supplier evidence was extracted from the selected document snapshot; this is not a misconduct conclusion."
    elif governing_ok and observation and verified(observation_refs):
        documents = {r["document_id"] for r in observation_refs}
        # Every cited supplier document must independently contain this identity.
        source_text = " ".join(t for (d, _), t in pages.items() if d in documents)
        identity_ok = all(contains_identity(" ".join(t for (d, _), t in pages.items() if d == doc), supplier) for doc in documents)
        dates_ok = all(value is None or value.isoformat() in actual_text for value in (observation.validity_from, observation.validity_until))
        for label, claimed in ((r"valid\s+from", observation.validity_from), (r"valid\s+until|expires|expiry|expiration\s+date", observation.validity_until)):
            if re.search(label, source_text, re.I):
                values = set(re.findall(r"(?:" + label + r")\s*[:=]?\s*(\d{4}-\d{2}-\d{2})", source_text, re.I))
                if len(values) != 1 or claimed is None or claimed.isoformat() not in values:
                    dates_ok = False
                else:
                    try:
                        date.fromisoformat(next(iter(values)))
                    except ValueError:
                        dates_ok = False
        if observation.validity_from and observation.validity_until and observation.validity_from > observation.validity_until:
            dates_ok = False
        if observation.validity_from and reference_date < observation.validity_from:
            dates_ok = False
        if observation.validity_until and reference_date > observation.validity_until:
            dates_ok = False
        required = numeric_value(required_text, criterion.metric)
        actual = numeric_value(actual_text, criterion.metric)
        topic = {"WARRANTY_MONTHS": r"warranty|coverage", "RAM_GB": r"RAM|memory", "DELIVERY_DAYS": r"delivery", "QUANTITY": r"quantity|units"}.get(criterion.metric)
        conflicting_snapshot = False
        # A model may omit an inconvenient selected document. Scan explicit
        # same-supplier metric values independently rather than trusting selection.
        for doc in supplier_documents:
            full_text = " ".join(t for (d, _), t in pages.items() if d == doc)
            if topic and contains_identity(full_text, supplier) and re.search(topic, full_text, re.I):
                found = numeric_value(full_text, criterion.metric)
                if found is None or found != actual:
                    conflicting_snapshot = True
        operator_ok = {
            "MIN": bool(re.search(r"\b(minimum|at least|not less than)\b|>=", required_text, re.I)),
            "MAX": bool(re.search(r"\b(maximum|at most|within|not more than)\b|<=", required_text, re.I)),
            "EQUAL": bool(re.search(r"\b(exactly|equal to)\b", required_text, re.I)),
            "CONTEXTUAL": False,
        }[criterion.operator]
        if not identity_ok:
            explanation = "Supplier identity could not be independently matched in each cited document."
        elif not dates_ok:
            explanation = "The cited validity period is missing, conflicting, expired or outside the assessment reference date."
        elif conflicting_snapshot:
            explanation = "Selected supplier documents contain conflicting or ambiguous values; human reconciliation is required."
        elif criterion.metric == "CONTEXTUAL" and observation.contextual_explanation and not re.search(r"\d|fraud|corrupt|collus|misconduct|backdat|fabricat|falsif", observation.contextual_explanation, re.I):
            explanation = "Tentative AI interpretation requiring human verification: " + observation.contextual_explanation
        elif not observation.ambiguous and not re.search(r"\b(no warranty|missing|not provided|without warranty)\b", actual_text, re.I) and operator_ok and required is not None and actual is not None and required == criterion.required_value and actual == observation.actual_value:
            satisfied = {"MIN": actual >= required, "MAX": actual <= required, "EQUAL": actual == required}.get(criterion.operator, False)
            status = "VERIFIED" if satisfied else "NON_COMPLIANT"
            explanation = f"Verified {criterion.metric} evidence states {actual}; the criterion requires {criterion.operator} {required}. This is an evidence check, not supplier disqualification."
    if criterion.mandatory is None and status in {"VERIFIED", "NON_COMPLIANT"}:
        status = "NEEDS_REVIEW"
        explanation = "The substantive comparison is available, but mandatory/optional classification is unresolved."
    if criterion.mandatory is None and status == "MISSING":
        status = "NEEDS_REVIEW"
        explanation = "No matching evidence was extracted and the criterion's mandatory status is unclear."
    action = None
    if guidance and status not in {"VERIFIED", "NOT_APPLICABLE"}:
        action = "PROPOSED: Provide qualifying evidence or clarification only if permitted by the procurement rules; preserve the original records and request human verification."
    return {"requirement_id": criterion.criterion_id, "description": criterion.description,
        "mandatory": criterion.mandatory, "required_value": criterion.required_value, "actual_value": actual,
        "unit": criterion.metric, "readiness_status": status, "evidence": criterion_refs + observation_refs,
        "explanation": explanation, "recommended_action": action, "requires_human_review": status not in {"VERIFIED", "NOT_APPLICABLE"}}


def readiness(output, validator, criteria_ids, supplier_ids, supplier, reference_date, guidance):
    unique_records(output)
    observations = {(o.criterion_id, o.supplier_ref): o for o in output.observations}
    # Validate all assertions, even unrelated supplier observations that will not be used.
    observed_refs = {(o.criterion_id, o.supplier_ref): validator.validate(o.evidence, supplier_ids) for o in output.observations}
    items = []
    for criterion in output.criteria:
        refs = validator.validate(criterion.evidence, criteria_ids)
        key = (criterion.criterion_id, supplier)
        foreign = any(o.criterion_id == criterion.criterion_id and o.supplier_ref != supplier for o in output.observations)
        item = assess_requirement(criterion, observations.get(key), supplier, refs, observed_refs.get(key, []), validator.pages, reference_date, guidance, supplier_ids)
        if foreign and key not in observations:
            item.update(readiness_status="NEEDS_REVIEW", explanation="Available evidence belongs to another supplier and cannot establish this supplier's readiness.", requires_human_review=True)
        items.append(item)
    return items
