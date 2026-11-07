"""PROPOSED P1.1 schemas, separate from the locked P0 enum sets."""
from datetime import date
from typing import Annotated, Literal
from pydantic import Field, StringConstraints, UUID4, model_validator
from app.schemas.shared import StrictModel, PositiveVersion, ProcessingStatus, UtcTimestamp
from app.schemas.p0 import Citation, EvidenceView

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
SupplierRef = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Ids = Annotated[list[UUID4], Field(min_length=1, max_length=50)]
Metric = Literal["RAM_GB", "WARRANTY_MONTHS", "DELIVERY_DAYS", "QUANTITY", "CONTEXTUAL"]
Decision = Literal["COMPLIANT", "NON_COMPLIANT", "NOT_EVALUATED", "AMBIGUOUS"]


class EvaluationCreate(StrictModel):
    evaluation_document_id: UUID4
    supplier_document_ids: Annotated[list[UUID4], Field(max_length=50)]
    criteria_document_ids: Ids
    check_types: Annotated[list[Literal["CRITERIA_CONSISTENCY", "EVIDENCE_VERIFICATION", "DECISION_CONSISTENCY"]], Field(min_length=1, max_length=3)]

    @model_validator(mode="after")
    def distinct_checks(self):
        if len(set(self.check_types)) != len(self.check_types):
            raise ValueError("Duplicate check types")
        return self


class Criterion(StrictModel):
    criterion_id: Text
    description: Text
    mandatory: bool | None
    applicable_supplier: SupplierRef | None
    metric: Metric
    operator: Literal["MIN", "MAX", "EQUAL", "CONTEXTUAL"]
    required_value: Annotated[int, Field(strict=True, ge=0)] | None
    evidence: Annotated[list[Citation], Field(min_length=1)]


class Observation(StrictModel):
    criterion_id: Text
    supplier_ref: SupplierRef
    actual_value: Annotated[int, Field(strict=True, ge=0)] | None
    validity_from: date | None
    validity_until: date | None
    ambiguous: bool
    contextual_explanation: Annotated[str, Field(max_length=2000)]
    evidence: Annotated[list[Citation], Field(min_length=1)]


class EvaluationStatement(StrictModel):
    criterion_id: Text
    supplier_ref: SupplierRef
    recorded_decision: Decision
    confidence: Annotated[float, Field(ge=0, le=1)]
    evidence: Annotated[list[Citation], Field(min_length=1)]


class AssessmentOutput(StrictModel):
    criteria: Annotated[list[Criterion], Field(max_length=100)]
    observations: Annotated[list[Observation], Field(max_length=500)]
    decisions: Annotated[list[EvaluationStatement], Field(max_length=500)]


class ReadinessItem(StrictModel):
    requirement_id: str
    description: str
    mandatory: bool | None
    required_value: int | None
    actual_value: int | None
    unit: Metric
    readiness_status: Literal["VERIFIED", "MISSING", "NEEDS_REVIEW", "NOT_APPLICABLE", "NON_COMPLIANT"]
    evidence: list[EvidenceView]
    explanation: str
    recommended_action: str | None
    requires_human_review: bool


class EvaluationItem(StrictModel):
    supplier_ref: str
    criterion_id: str
    criterion_description: str
    recorded_decision: Decision
    evidence_assessment: Literal["SUPPORTED", "UNSUPPORTED", "MISSING", "AMBIGUOUS", "NOT_APPLICABLE"]
    consistency_result: Literal["CONSISTENT", "INCONSISTENT", "NEEDS_REVIEW"]
    explanation: str
    evidence: list[EvidenceView]
    recommended_action: Literal["REQUEST_REEVALUATION", "HUMAN_REVIEW", "NONE"]


class StatusChange(StrictModel):
    requirement_id: str
    before_status: str | None
    after_status: str | None


class AssessmentView(StrictModel):
    check_id: UUID4
    case_id: UUID4
    job_id: UUID4
    kind: Literal["EVALUATION", "READINESS"]
    version: PositiveVersion
    previous_check_id: UUID4 | None
    supplier_ref: str | None
    status: ProcessingStatus
    ai_execution_id: UUID4 | None
    reference_date: date
    summary: dict[str, int]
    items: list[EvaluationItem]
    requirements: list[ReadinessItem]
    finding_ids: list[UUID4]
    changes: list[StatusChange]
    created_at: UtcTimestamp
