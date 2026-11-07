"""Read-only, source-labelled offer facts and original-finding repair records."""
import re
from uuid import UUID

from sqlalchemy import select

from app.api.decision_presenters import repair_data
from app.api.presenters import finding_data, job_data
from app.api.response import ApiError
from app.core.transactions import case_for, resource_for, wire
from app.models import AnalysisJob, Document, DocumentPage, Finding, RepairProposal, Review
from app.services.assurance.reviews import review_view

MONEY = r"(?:\d{1,3}(?:,\d{3})+|\d{1,3}(?:\.\d{3})+|\d+)(?![\d.,])"
ATTRIBUTES = (
    ("memory", "Memory"), ("processor", "Processor"), ("storage", "Storage"),
    ("display", "Display"), ("security", "Security"), ("operating_system", "Operating system"),
    ("delivery", "Delivery"), ("warranty", "Warranty"),
)


def source_facts(document, pages):
    facts, seen = [], set()

    def add(field, label, value, page, excerpt, amount=None):
        identity = (field, str(value), page.page_number)
        if not str(value).strip() or identity in seen:
            return
        seen.add(identity)
        facts.append({"field": field, "label": label, "value": str(value).strip(), "amount_idr": amount,
            "source": {"document_id": str(document.id), "page_number": page.page_number, "excerpt": excerpt}})

    def money(value):
        return int(re.sub(r"[,.]", "", value))

    for page in pages:
        text = page.normalized_text
        if wire(document.document_type) == "SUPPLIER_QUOTATION":
            for match in re.finditer(r"\b(?:evaluated|quoted|grand|offer)?\s*total(?: price)?(?: of)?\s+(?:Rp|IDR)\s*(?P<value>" + MONEY + ")", text, re.I):
                amount = money(match.group("value"))
                add("total_price_idr", "Quoted total price", f"IDR {amount:,}", page, match.group(0), amount)
            # Explicit table headings establish which amounts are unit and total.
            table = r"\bItem\s+Quantity\s+Unit\s+(?:basis|price)\s+Total\s+.+?\s+(?P<quantity>\d+)\s+(?:Rp|IDR)\s*(?P<unit>" + MONEY + r")\s+(?:Rp|IDR)\s*(?P<total>" + MONEY + r")"
            for match in re.finditer(table, text, re.I):
                add("quantity", "Offered quantity", match.group("quantity"), page, match.group(0))
                for field, label, key in (("unit_price_idr", "Quoted unit price", "unit"), ("line_total_idr", "Quoted line item total", "total")):
                    amount = money(match.group(key))
                    add(field, label, f"IDR {amount:,}", page, match.group(0), amount)
            patterns = (
                ("supplier_name", "Supplier name", r"\b(?:Fictional offer from|Supplier name\s*:?|Vendor name\s*:?)\s+(?P<value>.+?)(?=\s+Document ID\b|\s+Commercial offer\b|$)"),
                ("model", "Offered model", r"\boffer\s+\d+\s+units?\s+of\s+(?P<value>.+?)(?=\s+for a\b|\s+at a\b|[.;]|$)"),
                ("quantity", "Offered quantity", r"\boffer\s+(?P<value>\d+)\s+(?:units|laptops|devices)\b"),
                ("offer_validity", "Offer validity", r"\b(?:quotation|offer)\s+is valid for\s+(?P<value>\d+\s+(?:calendar\s+|business\s+)?days)"),
                ("tax_basis", "Tax basis", r"\b(?P<value>VAT[- ]inclusive|VAT[- ]exclusive|including VAT|excluding VAT)\b"),
            )
            for field, label, pattern in patterns:
                for match in re.finditer(pattern, text, re.I):
                    add(field, label, match.group("value"), page, match.group(0))
            section = re.search(r"\bOffered configuration\s+(?:Attribute\s+Offer\s+)?(?P<body>.+?)(?=\s+Supplier declaration\b|$)", text, re.I)
            for field, label in ATTRIBUTES:
                stop = "|".join(re.escape(other) for _, other in ATTRIBUTES if other != label) + r"|Supplier declaration|Control note|Document ID"
                pattern = rf"\b{re.escape(label)}\s*:?\s+(?P<value>.+?)(?=\s+(?:{stop})\b|$)"
                for match in re.finditer(pattern, section.group("body") if section else "", re.I):
                    if len(match.group("value")) <= 700:
                        add(field, label, match.group("value"), page, match.group(0))
        if wire(document.document_type) == "WARRANTY_EVIDENCE":
            for match in re.finditer(r"\bTerm\s+(?P<value>.+?)(?=\s+(?:Service route|Geographic scope|Exclusions|Traceability|Authorization statement)\b|$)", text, re.I):
                if len(match.group("value")) <= 700:
                    add("warranty_term", "Warranty letter term", match.group("value"), page, match.group(0))
    return {"document_id": str(document.id), "filename": document.filename, "facts": facts}


def vendor_summary(db, actor, case_id, analysis_job_id):
    case_for(db, actor, case_id)
    current = resource_for(db, actor, AnalysisJob, analysis_job_id)
    if current.case_id != case_id:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Analysis not found for this case")
    inputs = {UUID(value) for value in current.input_document_ids_json}
    documents = db.scalars(select(Document).where(Document.case_id == case_id, Document.id.in_(inputs),
        Document.deleted_at.is_(None), Document.processing_status == "COMPLETED",
        Document.document_type.in_(["SUPPLIER_QUOTATION", "WARRANTY_EVIDENCE"])).order_by(Document.uploaded_at, Document.id)).all()
    document_facts = []
    for document in documents:
        pages = db.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id).order_by(DocumentPage.page_number)).all()
        document_facts.append(source_facts(document, pages))
    usable = db.scalars(select(AnalysisJob).where(AnalysisJob.case_id == case_id,
        AnalysisJob.processing_status.in_(["COMPLETED", "NEEDS_REVIEW"])).order_by(AnalysisJob.created_at, AnalysisJob.id)).all()
    usable = [job for job in usable if job.result_json is not None]
    initial = next((job for job in usable if job.result_json.get("finding_ids")), usable[0] if usable else None)
    initial_ids = {UUID(value) for value in initial.result_json.get("finding_ids", [])} if initial else set()
    original = db.scalars(select(Finding).where(Finding.case_id == case_id, Finding.id.in_(initial_ids)).order_by(Finding.created_at, Finding.id)).all() if initial_ids else []
    repairs = db.scalars(select(RepairProposal).where(RepairProposal.case_id == case_id, RepairProposal.finding_id.in_(initial_ids),
        RepairProposal.deleted_at.is_(None)).order_by(RepairProposal.created_at, RepairProposal.id)).all() if initial_ids else []
    repair_ids = [repair.id for repair in repairs]
    reviews = db.scalars(select(Review).where(Review.case_id == case_id, Review.repair_proposal_id.in_(repair_ids)).order_by(Review.created_at, Review.id)).all() if repair_ids else []
    return {"case_id": str(case_id), "analysis_job_id": str(current.id), "document_facts": document_facts,
        "initial_analysis": job_data(db, initial) if initial else None,
        "initial_findings": [finding_data(db, finding) for finding in original],
        "repair_proposals": [repair_data(repair) for repair in repairs],
        "reviews": [review_view(review).model_dump(mode="json") for review in reviews],
        "extraction_method": "source_labeled_fields_v1",
        "limitations": ["Only explicit labelled values in the selected analysis evidence set are extracted; absent fields remain unavailable.",
            "Multiple values remain source-specific and are not silently reconciled.",
            "A later clean assessment is not proof that an original finding was repaired or formally resolved."]}
