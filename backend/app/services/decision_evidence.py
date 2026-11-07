"""Independent grounding, neutral-language and quantitative-source checks."""
import json
import re
from sqlalchemy import select
from app.api.response import ApiError
from app.core.transactions import case_for, resource_for
from app.models import Finding, EvidenceRef, Document, DocumentPage
from app.services.documents.pdf import normalize

_NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)*")
_WORD_NUMBER = re.compile(r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|hundred|thousand|million|billion)\b", re.I)
_ALLEGATION = re.compile(r"\b(?:fraud\w*|corrupt\w*|collusi\w*|wrongdoing|criminal\w*|brib\w*|overpric\w*|guilty|actual savings|financial loss|proof of)\b", re.I)
_METRIC = re.compile(r"\b(?:suppliers?|eligib\w*|prices?|offers?|delta|savings?|loss(?:es)?|IDR|Rp|rupiah|percent\w*)\b|%", re.I)


def _invalid(message):
    raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", message)


def neutral(text):
    if _ALLEGATION.search(text):
        _invalid("Draft language must remain neutral and avoid allegations")


def sources_for(db, actor, case_id, finding_id):
    case = case_for(db, actor, case_id)
    finding = resource_for(db, actor, Finding, finding_id)
    if finding.case_id != case_id:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Finding not found for this case")
    if case.case_status in {"ARCHIVED", "REVIEW_COMPLETED"}:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "Case is closed for new decision drafts")
    if finding.status not in {"OPEN", "UNDER_REVIEW"}:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "Finding is not active")
    if finding.evidence_status != "VERIFIED":
        _invalid("Required finding evidence is not VERIFIED")
    sources = []
    refs = db.scalars(select(EvidenceRef).where(EvidenceRef.finding_id == finding_id)
        .order_by(EvidenceRef.document_id, EvidenceRef.page_number, EvidenceRef.id)).all()
    for ref in refs:
        if ref.verification_status != "VERIFIED":
            _invalid("Required evidence reference is not VERIFIED")
        document = resource_for(db, actor, Document, ref.document_id)
        if document.case_id != case_id:
            _invalid("Evidence does not belong to the finding case")
        page = db.scalar(select(DocumentPage).where(DocumentPage.document_id == document.id,
            DocumentPage.page_number == ref.page_number))
        if page is None or ref.page_number > document.page_count or not normalize(ref.excerpt) or normalize(ref.excerpt) not in page.normalized_text:
            _invalid("Required evidence excerpt could not be independently verified")
        sources.append({"document_id": str(ref.document_id), "page_number": ref.page_number, "excerpt": ref.excerpt})
    if not sources:
        _invalid("No VERIFIED evidence is available")
    return case, finding, {"case_id": str(case.id), "case_version": case.version,
        "finding_id": str(finding.id), "finding_version": finding.version,
        "finding": {"type": finding.type, "title": finding.title, "summary": finding.summary}, "evidence": sources}


def check_citations(citations, context):
    checks = {"checked": 0, "passed": 0, "failed": 0}
    for citation in citations:
        checks["checked"] += 1
        if any(str(citation.document_id) == ref["document_id"] and citation.page_number == ref["page_number"]
            and normalize(citation.excerpt) and normalize(citation.excerpt) in normalize(ref["excerpt"])
            for ref in context["evidence"]):
            checks["passed"] += 1
        else:
            checks["failed"] += 1
    return checks


def validate_challenge(output, context):
    if not output.question.endswith("?"):
        _invalid("A challenge must contain a question")
    neutral(output.question + " " + output.risk_rationale)
    supported = {n for c in output.evidence for n in _NUMBER.findall(c.excerpt)}
    if any(n not in supported for n in _NUMBER.findall(output.question + " " + output.risk_rationale)):
        _invalid("Challenge numerals must be grounded in cited evidence")
    if _WORD_NUMBER.search(output.question + " " + output.risk_rationale):
        _invalid("Use evidence-supported digits rather than unvalidated number words")


def validate_repair_text(proposed_text, justification, context):
    neutral(proposed_text + " " + justification)
    if _NUMBER.search(justification) or _WORD_NUMBER.search(proposed_text + " " + justification):
        _invalid("Quantitative interpretation must be rendered from simulation output by the server")
    if _METRIC.search(proposed_text + " " + justification):
        _invalid("Model/human draft text must not introduce quantitative simulation claims")
    supported = {n for ref in context["evidence"] for n in _NUMBER.findall(ref["excerpt"])}
    inputs = context["simulation"]["input_snapshot"]
    for field in ("baseline", "alternative"):
        supported.update(_NUMBER.findall(json.dumps(inputs.get(field, {}))))
    if any(n not in supported for n in _NUMBER.findall(proposed_text)):
        _invalid("Proposed requirement numerals must be grounded in verified evidence or scenario input")


def validated_simulation_context(snapshot, *, case_id=None, finding_id=None, simulation_id=None):
    for expected, actual in ((case_id, snapshot.case_id), (finding_id, snapshot.finding_id), (simulation_id, snapshot.simulation_id)):
        if expected is not None and expected != actual:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Simulation not found for this finding")
    context = snapshot.as_context()
    try:
        result = context["result"]
        for key in ("baseline", "alternative", "delta"):
            metrics = result[key]
            for field in ("eligible_supplier_count", "lowest_total_offer_idr"):
                value = metrics[field]
                if type(value) is not int or (key != "delta" and value < 0):
                    raise ValueError()
        inputs = context["input_snapshot"]
        for scenario in ("baseline", "alternative"):
            value = inputs[scenario]["minimum_ram_gb"]
            if type(value) is not int or value <= 0:
                raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ApiError(422, "SIMULATION_INPUT_INVALID", "Stored simulation does not contain usable immutable P0 results") from None
    return context


def simulation_interpretation(context):
    result = context["simulation"]["result"]
    # Formatting only. Aris's engine remains the sole calculator.
    def metrics(name):
        values = result[name]
        return f"{name}: eligible_supplier_count={values['eligible_supplier_count']}, lowest_total_offer_idr={values['lowest_total_offer_idr']}"
    return "Synthetic simulation (" + context["simulation"]["engine_version"] + "; " + context["simulation"]["supplier_data_version"] + "): " + "; ".join(metrics(k) for k in ("baseline", "alternative", "delta")) + ". Illustrative scenario only; not evidence of actual savings, financial loss or wrongdoing. This remains a draft and does not amend official documents."
