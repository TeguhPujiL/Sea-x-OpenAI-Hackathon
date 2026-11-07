from hashlib import sha256
from threading import Lock

_PARSER_LOCK = Lock()
import pymupdf
from app.api.response import ApiError


def normalize(text):
    return " ".join(text.split())


def extract_pdf(payload, content_type, settings):
    if len(payload) > settings.upload_max_bytes:
        raise ApiError(413, "FILE_TOO_LARGE", "PDF exceeds the upload limit")
    if content_type != "application/pdf" or not payload.startswith(b"%PDF-"):
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Only PDF uploads are supported")
    try:
        with _PARSER_LOCK, pymupdf.open(stream=payload, filetype="pdf") as document:
            if document.needs_pass or document.is_encrypted or document.metadata.get("encryption"):
                raise ApiError(400, "VALIDATION_ERROR", "Encrypted PDFs are not supported")
            if not document.is_pdf or document.is_repaired:
                raise ApiError(422, "PDF_EXTRACTION_FAILED", "PDF parsing failed")
            if not 1 <= document.page_count <= settings.pdf_max_pages:
                raise ApiError(422, "PDF_EXTRACTION_FAILED", "PDF page limit exceeded")
            pages = []
            characters = 0
            for page in document:
                text = page.get_text("text")
                characters += len(text)
                if characters > settings.pdf_max_characters:
                    raise ApiError(422, "PDF_EXTRACTION_FAILED", "Extracted text limit exceeded")
                pages.append(normalize(text))
            if not any(pages):
                raise ApiError(422, "PDF_EXTRACTION_FAILED", "PDF has no usable text; OCR is unavailable")
            return sha256(payload).hexdigest(), pages
    except ApiError:
        raise
    except (RuntimeError, ValueError):
        raise ApiError(422, "PDF_EXTRACTION_FAILED", "PDF parsing failed") from None
