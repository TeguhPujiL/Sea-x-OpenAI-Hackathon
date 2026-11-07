"""Pure evidence helpers; callers must supply authorized stored pages only."""
from collections.abc import Mapping
from uuid import UUID


def normalize_text(text: str) -> str:
    # Whitespace only: preserve case, punctuation and numbers.
    return " ".join(text.split())


def excerpt_matches(
    authorized_pages: Mapping[tuple[UUID, int], str],
    document_id: UUID,
    page_number: int,
    excerpt: str,
) -> bool:
    """Fail closed; absence must not reveal whether another case has this page.

    This is a content check, not an authorization mechanism. Build the mapping
    from server-authorized persisted pages, never from model or client input.
    """
    if type(page_number) is not int or page_number < 1:
        return False
    page = authorized_pages.get((document_id, page_number))
    candidate = normalize_text(excerpt)
    return page is not None and bool(candidate) and candidate in normalize_text(page)
