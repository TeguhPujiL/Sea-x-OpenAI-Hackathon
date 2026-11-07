from hashlib import sha256
from uuid import uuid4

import pymupdf
import pytest

from app.services.documents.evidence import excerpt_matches
from app.services.documents.pdf import PdfExtractionFailed, PdfRejected, extract_pdf


def make_pdf(texts=("Minimum RAM 32 GB",), encrypted=False):
    with pymupdf.open() as document:
        for text in texts:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
        if encrypted:
            return document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256,
                                    owner_pw="owner-test", user_pw="user-test")
        return document.tobytes()


def extract(payload, **changes):
    options = dict(document_id=uuid4(), content_type="application/pdf",
                   max_bytes=1_000_000, max_pages=10, max_text_characters=100_000)
    options.update(changes)
    return extract_pdf(payload, **options)


def test_real_pages_and_checksum():
    payload = make_pdf(("Minimum RAM 32 GB", "Quantity 50 units"))
    result = extract(payload)
    assert result.sha256 == sha256(payload).hexdigest()
    assert result.page_count == 2
    assert [p.page_number for p in result.pages] == [1, 2]
    assert result.pages[1].normalized_text == "Quantity 50 units"
    pages = {(p.document_id, p.page_number): p.normalized_text for p in result.pages}
    assert excerpt_matches(pages, result.pages[0].document_id, 1, "RAM  32\nGB")
    assert not excerpt_matches(pages, result.pages[0].document_id, 2, "RAM 32 GB")


@pytest.mark.parametrize("kind", ["mime", "signature", "malformed", "oversized", "encrypted", "textless", "pages", "text"])
def test_rejected_pdfs(kind):
    payload = make_pdf()
    changes = {}
    if kind == "mime": changes["content_type"] = "image/png"
    if kind == "signature": payload = b"not a PDF"
    if kind == "malformed": payload = b"%PDF-1.7\ninvalid"
    if kind == "oversized": changes["max_bytes"] = len(payload) - 1
    if kind == "encrypted": payload = make_pdf(encrypted=True)
    if kind == "textless": payload = make_pdf(("",))
    if kind == "pages": payload = make_pdf(("First", "Second")); changes["max_pages"] = 1
    if kind == "text": changes["max_text_characters"] = 1
    with pytest.raises(PdfExtractionFailed if kind == "textless" else PdfRejected):
        extract(payload, **changes)


def test_evidence_fails_closed_and_does_not_change_semantics():
    document_id = uuid4()
    pages = {(document_id, 1): "Minimum RAM 32 GB"}
    assert not excerpt_matches(pages, uuid4(), 1, "Minimum RAM 32 GB")
    for page_number in (0, -1, True, 1.0):
        assert not excerpt_matches(pages, document_id, page_number, "RAM")
    for excerpt in ("", " \n", "RAM 16 GB", "ram 32 GB"):
        assert not excerpt_matches(pages, document_id, 1, excerpt)
