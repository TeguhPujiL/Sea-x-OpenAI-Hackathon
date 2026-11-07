"""DC1 proposal schema, using the existing nine document types."""
from typing import Annotated, Literal
from pydantic import Field, UUID4
from app.schemas.shared import StrictModel, DocumentType, PositiveVersion
from app.schemas.p0 import Citation, EvidenceView


class ClassificationRequest(StrictModel):
    expected_version: PositiveVersion


class ClassificationOutput(StrictModel):
    suggested_type: DocumentType
    confidence: Annotated[float, Field(ge=0, le=1)]
    ambiguous: bool
    rationale: Annotated[str, Field(min_length=1, max_length=1500)]
    evidence: Annotated[list[Citation], Field(min_length=1, max_length=3)]


class ClassificationView(StrictModel):
    document_id: UUID4
    case_id: UUID4
    expected_version: PositiveVersion
    suggested_type: DocumentType
    confidence: float
    status: Literal["AUTO_READY", "NEEDS_REVIEW"]
    rationale: str
    evidence: list[EvidenceView]
    ai_execution_id: UUID4
