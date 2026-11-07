"""Internal PDF extraction; no HTTP mappings or contract enums are inferred."""
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

import pymupdf

from app.services.documents.evidence import normalize_text


class PdfRejected(ValueError):
    """Internal rejection. API adapters must use verified Appendix B mappings."""


class PdfExtractionFailed(PdfRejected):
    """Map to user-required PDF_EXTRACTION_FAILED once the adapter is defined."""


@dataclass(frozen=True)
class ExtractedPage:
    document_id: UUID
    page_number: int
    normalized_text: str


@dataclass(frozen=True)
class ExtractedPdf:
    sha256: str
    page_count: int
    pages: tuple[ExtractedPage, ...]


def extract_pdf(
    payload: bytes,
    *,
    document_id: UUID,
    content_type: str,
    max_bytes: int,
    max_pages: int,
    max_text_characters: int,
) -> ExtractedPdf:
    """Parse in memory without writing files, logging content or creating findings.

    Limits are explicit caller policy; no undocumented contract limits are set.
    Upload adapters must enforce size while streaming BEFORE buffering bytes.
    Production parsing needs a worker process with memory and time limits.
    """
    for limit in (max_bytes, max_pages, max_text_characters):
        if type(limit) is not int or limit < 1:
            raise ValueError("PDF limits must be positive integers")
    if document_id.version != 4:
        raise ValueError("document_id must be UUID v4")
    if len(payload) > max_bytes:
        raise PdfRejected("PDF exceeds byte limit")
    if content_type.split(";", 1)[0].strip().lower() != "application/pdf":
        raise PdfRejected("PDF MIME type required")
    if not payload.startswith(b"%PDF-"):
        raise PdfRejected("PDF signature required")
    try:
        with pymupdf.open(stream=payload, filetype="pdf") as document:
            if document.needs_pass or document.is_encrypted:
                raise PdfRejected("Encrypted PDF is not supported")
            if not document.is_pdf or document.is_repaired:
                raise PdfRejected("Malformed PDF is not supported")
            if not 1 <= document.page_count <= max_pages:
                raise PdfRejected("PDF page limit exceeded or document is empty")
            pages = []
            character_count = 0
            for number, page in enumerate(document, start=1):
                text = page.get_text("text")
                character_count += len(text)
                if character_count > max_text_characters:
                    raise PdfRejected("Extracted text limit exceeded")
                pages.append(ExtractedPage(document_id, number, normalize_text(text)))
            if not any(page.normalized_text for page in pages):
                raise PdfExtractionFailed("PDF has no usable text; OCR is unavailable")
            return ExtractedPdf(sha256(payload).hexdigest(), len(pages), tuple(pages))
    except PdfRejected:
        raise
    except (RuntimeError, ValueError):
        # Do not include parser detail or document content in outward errors.
        raise PdfExtractionFailed("PDF parsing failed") from None
