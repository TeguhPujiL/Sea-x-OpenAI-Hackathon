import re
from uuid import UUID

from sqlalchemy import select

from app.api.response import ApiError
from app.core.security import check_version
from app.core.transactions import case_for, resource_for, wire
from app.models import AnalysisJob, Challenge, Document, DocumentPage, EvidenceRef, Finding
from app.services.documents.pdf import normalize


def source_context(db, actor, case_id, payload):
    case = case_for(db, actor, case_id)
    finding = resource_for(db, actor, Finding, payload.finding_id)
    if finding.case_id != case_id:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Finding not found for this case")
    check_version(case.version, payload.expected_case_version)
    check_version(finding.version, payload.expected_finding_version)
    if case.case_status in {"ARCHIVED", "REVIEW_COMPLETED"} or finding.status not in {"OPEN", "UNDER_REVIEW"}:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "An open case and active finding are required")
    challenge = db.scalar(select(Challenge).where(Challenge.case_id == case_id, Challenge.finding_id == finding.id,
        Challenge.deleted_at.is_(None), Challenge.status.in_(["DRAFT", "READY"])).order_by(Challenge.created_at.desc(), Challenge.id.desc()))
    if challenge is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "A recorded active challenge is required for this finding")
    job = resource_for(db, actor, AnalysisJob, finding.analysis_job_id)
    if job.case_id != case_id or job.processing_status not in {"COMPLETED", "NEEDS_REVIEW"} or not job.result_json or str(finding.id) not in job.result_json.get("finding_ids", []):
        raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Source analysis does not contain a usable finding result")
    input_ids = set(job.input_document_ids_json)
    refs = db.scalars(select(EvidenceRef).where(EvidenceRef.finding_id == finding.id).order_by(EvidenceRef.document_id, EvidenceRef.page_number, EvidenceRef.id)).all()
    pages, evidence = {}, []
    for ref in refs:
        doc = resource_for(db, actor, Document, ref.document_id)
        page = db.scalar(select(DocumentPage).where(DocumentPage.document_id == doc.id, DocumentPage.page_number == ref.page_number))
        if doc.case_id != case_id or str(doc.id) not in input_ids or doc.processing_status != "COMPLETED" or not page or not 1 <= ref.page_number <= doc.page_count or not normalize(ref.excerpt) or normalize(ref.excerpt) not in normalize(page.normalized_text):
            raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "Finding sources are missing, deleted or not grounded in their source analysis")
        evidence.append({"document_id": str(doc.id), "page_number": ref.page_number, "excerpt": ref.excerpt})
        pages[(str(doc.id), ref.page_number)] = {"document_id": str(doc.id), "page_number": ref.page_number,
            "text": page.normalized_text, "document_version": doc.version, "sha256": doc.sha256}
    if not evidence:
        raise ApiError(422, "EVIDENCE_VALIDATION_FAILED", "At least one available finding citation is required")
    index = []
    for value in sorted(input_ids):
        doc = db.get(Document, UUID(value))
        if doc and doc.case_id == case_id and doc.deleted_at is None:
            index.append({"document_id": str(doc.id), "filename": doc.filename, "document_type": wire(doc.document_type),
                "version": doc.version, "processing_status": wire(doc.processing_status)})
    return {"case_id": str(case_id), "case_version": case.version, "finding_version": finding.version,
        "analysis_job_id": str(job.id), "finding_id": str(finding.id), "finding_type": finding.type,
        "finding_title": finding.title, "finding_summary": finding.summary, "evidence": evidence,
        "challenge": {"challenge_id": str(challenge.id), "version": challenge.version, "status": wire(challenge.status),
            "question": challenge.question, "requested_evidence": list(challenge.requested_evidence_json)},
        "source_pages": list(pages.values()), "document_index": index, "user_assumptions": list(payload.assumptions),
        "source_needs_review": finding.evidence_status != "VERIFIED" or job.processing_status == "NEEDS_REVIEW" or bool(job.warnings_json)
            or any(ref.verification_status != "VERIFIED" for ref in refs)}


_NUMBER = re.compile(r"\d|%|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|hundred|thousand|million|billion)\b", re.I)
_CLAIM = re.compile(r"\b(?:fraud\w*|corrupt\w*|collusi\w*|criminal\w*|brib\w*|guilty|actual savings|financial loss|proven loss|approved|awarded)\b", re.I)


def validate_output(output, context):
    pages = {(page["document_id"], page["page_number"]): page["text"] for page in context["source_pages"]}
    refs = [*output.baseline.evidence, *(ref for alternative in output.alternatives for ref in alternative.evidence)]
    checks = {"checked": len(refs), "passed": 0, "failed": 0}
    def invalid(message):
        error = ApiError(422, "EVIDENCE_VALIDATION_FAILED", message)
        error.evidence_checks = dict(checks)
        raise error
    for ref in refs:
        page = pages.get((str(ref.document_id), ref.page_number))
        valid = page is not None and bool(normalize(ref.excerpt)) and normalize(ref.excerpt) in normalize(page)
        checks["passed" if valid else "failed"] += 1
    if checks["failed"]:
        invalid("Scenario citations do not match available case source pages")
    if output.baseline.assumptions != context["user_assumptions"]:
        invalid("Hypothetical assumptions must preserve the submitted text")
    prose = [output.title, output.baseline.description, *output.remaining_uncertainties,
        *(text for alternative in output.alternatives for text in [alternative.title, alternative.change, alternative.expected_effect, *alternative.limitations])]
    if any(_NUMBER.search(text) or _CLAIM.search(text) for text in prose):
        invalid("Scenario prose must remain qualitative and avoid numeric predictions or unsupported verdicts")
    if any(not re.search(r"\b(?:if|may|might|could|would|depending|subject)\b", alternative.expected_effect, re.I) for alternative in output.alternatives):
        invalid("Alternative effects must be conditional rather than promised outcomes")
    return checks


def deterministic_checks(context, citation_checks):
    checks = [{"check_type": "source_citation_integrity", "status": "PASS",
        "description": "Generated citations were independently matched to authorized stored source pages.", "observations": dict(citation_checks)},
        {"check_type": "source_document_presence", "status": "PASS",
        "description": "Cited source documents are active, readable and included in the source analysis; this does not establish full compliance.",
        "observations": {"cited_document_ids": sorted({page["document_id"] for page in context["source_pages"]}),
                         "indexed_source_documents": len(context["document_index"])}}]
    relevant = bool(re.search(r"\b(?:hps|arithmetic|estimate|subtotal|vat)\b", context["finding_title"] + " " + context["finding_summary"], re.I))
    arithmetic = {"check_type": "labeled_hps_integer_reconciliation", "status": "UNKNOWN" if relevant else "NOT_APPLICABLE",
        "description": "No unambiguous labeled subtotal, VAT and total figures are available for independent reconciliation." if relevant else "The finding does not identify an HPS arithmetic question.", "observations": {}}
    amount = r"((?:\d{1,3}(?:,\d{3})+|\d{1,3}(?:\.\d{3})+|\d+))(?=\s|$|[;])"
    patterns = {
        "subtotal": rf"\bLine-item subtotal\s+(?:Rp|IDR)\s*{amount}",
        "vat": rf"\bVAT\s+(\d{{1,2}})%\s*[x×]\s*subtotal\s+(?:Rp|IDR)\s*{amount}",
        "recomputed": rf"\bRecomputed total\s+(?:Rp|IDR)\s*{amount}",
        "displayed": rf"\bDisplayed approved total\s+(?:Rp|IDR)\s*{amount}",
    }
    candidates = []
    if relevant:
        for page in context["source_pages"]:
            matches = {name: list(re.finditer(pattern, normalize(page["text"]), re.I)) for name, pattern in patterns.items()}
            if not all(len(values) == 1 for values in matches.values()):
                continue
            def number(value):
                return int(value.replace(",", "").replace(".", ""))
            subtotal = number(matches["subtotal"][0].group(1))
            percent, vat = (number(value) for value in matches["vat"][0].groups())
            if subtotal * percent % 100:
                continue  # Never invent a rounding convention.
            recomputed, displayed = (number(matches[name][0].group(1)) for name in ("recomputed", "displayed"))
            calculated_vat = subtotal * percent // 100
            calculated_total = subtotal + calculated_vat
            candidates.append({"document_id": page["document_id"], "page_number": page["page_number"], "subtotal_idr": subtotal,
                "vat_percent": percent, "stated_vat_idr": vat, "calculated_vat_idr": calculated_vat,
                "stated_recomputed_total_idr": recomputed, "displayed_total_idr": displayed, "calculated_total_idr": calculated_total,
                "displayed_minus_calculated_idr": displayed - calculated_total})
        if len(candidates) == 1:
            result = candidates[0]
            arithmetic.update(status="PASS" if result["stated_vat_idr"] == result["calculated_vat_idr"] and result["stated_recomputed_total_idr"] == result["calculated_total_idr"] and result["displayed_total_idr"] == result["calculated_total_idr"] else "CONCERN",
                description="Integer arithmetic reconciled only the uniquely labeled cited figures; a difference is not proof of financial loss.", observations=result)
    checks.append(arithmetic)
    checks.append({"check_type": "other_quantitative_impact", "status": "UNKNOWN",
        "description": "No quantitative warranty, delivery, eligibility or financial-impact calculation is inferred. Use an approved method and explicit inputs for such calculations.", "observations": {}})
    return checks
