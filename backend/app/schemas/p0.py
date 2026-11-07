"""Exact public request fields plus internal schema-constrained AI output."""
from typing import Annotated, Literal
from pydantic import Field, UUID4, StringConstraints, model_validator
from app.schemas.shared import (StrictModel, IdrAmount, PositiveVersion, DocumentType,
    AnalysisType, FindingStatus, FindingSeverity)

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CaseCreate(StrictModel):
    title: NonEmpty
    category: NonEmpty
    description: str | None = None
    quantity: Annotated[int, Field(strict=True, ge=1)]
    budget_ceiling_idr: IdrAmount
    currency: Literal["IDR"] = "IDR"


class CasePatch(StrictModel):
    title: NonEmpty | None = None
    description: str | None = None
    quantity: Annotated[int, Field(strict=True, ge=1)] | None = None
    budget_ceiling_idr: IdrAmount | None = None
    expected_version: PositiveVersion

    @model_validator(mode="after")
    def nonnull_required_fields(self):
        for field in self.model_fields_set - {"description", "expected_version"}:
            if getattr(self, field) is None:
                raise ValueError("Required case fields cannot be null")
        return self


class DeleteRequest(StrictModel):
    reason: NonEmpty
    expected_version: PositiveVersion


class DocumentPatch(StrictModel):
    description: str | None = None
    document_type: DocumentType | None = None
    expected_version: PositiveVersion

    @model_validator(mode="after")
    def nonnull_type(self):
        if "document_type" in self.model_fields_set and self.document_type is None:
            raise ValueError("document_type cannot be null")
        return self


class AnalysisCreate(StrictModel):
    document_ids: Annotated[list[UUID4], Field(min_length=1)]
    analysis_types: Annotated[list[AnalysisType], Field(min_length=1)]
    force_reanalysis: bool = False

    @model_validator(mode="after")
    def unique_inputs(self):
        if len(set(self.document_ids)) != len(self.document_ids) or len(set(self.analysis_types)) != len(self.analysis_types):
            raise ValueError("Duplicate analysis inputs")
        return self


class RetryRequest(StrictModel):
    reason: NonEmpty


class FindingPatch(StrictModel):
    status: FindingStatus | None = None
    assignee_id: UUID4 | None = None
    resolution_note: str | None = None
    expected_version: PositiveVersion

    @model_validator(mode="after")
    def nonnull_status(self):
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


class DismissalRequest(StrictModel):
    reason_code: NonEmpty
    rationale: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3)]
    expected_version: PositiveVersion


# Internal AI schema version 1; not new public request fields or business enums.
class Citation(StrictModel):
    document_id: UUID4
    page_number: Annotated[int, Field(strict=True, ge=1)]
    excerpt: NonEmpty


class Requirement(StrictModel):
    text: NonEmpty
    evidence: Annotated[list[Citation], Field(min_length=1)]


class AiFinding(StrictModel):
    type: NonEmpty
    severity: FindingSeverity
    title: NonEmpty
    summary: NonEmpty
    confidence: Annotated[float, Field(ge=0, le=1)]
    evidence: Annotated[list[Citation], Field(min_length=1)]


class AnalysisOutput(StrictModel):
    requirements: list[Requirement]
    findings: list[AiFinding]


# Public response declarations preserve Section 6's exact wire names.
from typing import Generic, TypeVar
from app.schemas.shared import (UtcTimestamp, ProcessingStatus, CaseStatus, AssuranceStatus,
    EvidenceStatus, Pagination, ErrorBody)


class CaseView(StrictModel):
    case_id: UUID4
    case_number: str
    title: str
    category: str
    description: str | None
    quantity: int
    budget_ceiling_idr: IdrAmount
    currency: Literal["IDR"]
    case_status: CaseStatus
    assurance_status: AssuranceStatus
    version: PositiveVersion
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    deleted_at: UtcTimestamp | None


class DocumentView(StrictModel):
    document_id: UUID4
    case_id: UUID4
    filename: str
    document_type: DocumentType
    description: str | None
    mime_type: Literal["application/pdf"]
    size_bytes: int
    sha256: str
    page_count: int
    processing_status: ProcessingStatus
    version: PositiveVersion
    uploaded_at: UtcTimestamp
    deleted_at: UtcTimestamp | None


class EvidenceView(Citation):
    verification_status: EvidenceStatus


class FindingView(StrictModel):
    finding_id: UUID4
    case_id: UUID4
    analysis_job_id: UUID4
    ai_execution_id: UUID4
    type: str
    severity: FindingSeverity
    status: FindingStatus
    title: str
    summary: str
    confidence: Annotated[float, Field(ge=0, le=1)]
    evidence_status: EvidenceStatus
    evidence: list[EvidenceView]
    assignee_id: UUID4 | None
    resolution_note: str | None
    version: PositiveVersion
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class EvidenceChecks(StrictModel):
    checked: int
    passed: int
    failed: int


class Usage(StrictModel):
    input_tokens: int
    output_tokens: int


class ExecutionView(StrictModel):
    execution_id: UUID4
    provider: str
    model: str | None
    operation: str
    prompt_version: str
    input_document_ids: list[UUID4]
    schema_valid: bool
    evidence_validation_passed: bool
    evidence_checks: EvidenceChecks
    latency_ms: int
    usage: Usage | None


class JobResult(StrictModel):
    requirement_count: int
    finding_ids: list[UUID4]


class JobError(StrictModel):
    code: str
    message: str
    retryable: bool


class JobWarning(StrictModel):
    code: str
    document_id: UUID4
    page_number: int
    message: str


class JobView(StrictModel):
    job_id: UUID4
    case_id: UUID4
    job_type: Literal["DOCUMENT_ANALYSIS"]
    status: ProcessingStatus
    progress_percent: int
    ai_execution: ExecutionView | None
    result: JobResult | None
    warnings: list[JobWarning]
    error: JobError | None
    created_at: UtcTimestamp
    started_at: UtcTimestamp | None
    completed_at: UtcTimestamp | None
    retry_of_job_id: UUID4 | None = None


class CaseDeleted(StrictModel):
    case_id: UUID4
    deleted_at: UtcTimestamp


class DocumentDeleted(StrictModel):
    document_id: UUID4
    deleted_at: UtcTimestamp


class DismissalView(StrictModel):
    finding_id: UUID4
    status: Literal["DISMISSED"]
    dismissed_by: UUID4
    dismissed_at: UtcTimestamp
    version: PositiveVersion


Item = TypeVar("Item")


class ListData(StrictModel, Generic[Item]):
    items: list[Item]
    pagination: Pagination
