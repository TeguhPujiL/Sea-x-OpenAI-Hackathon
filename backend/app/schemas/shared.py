from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer, UUID4, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware UTC timestamp is required")
    return value.astimezone(timezone.utc)


UtcTimestamp = Annotated[datetime, AfterValidator(aware_utc), PlainSerializer(lambda v: aware_utc(v).isoformat().replace("+00:00", "Z"), return_type=str, when_used="json")]
IdrAmount = Annotated[int, Field(strict=True, ge=0)]
SignedIdrDelta = Annotated[int, Field(strict=True)]  # Contract Section 8 signed result.
PositiveVersion = Annotated[int, Field(strict=True, ge=1)]
ResourceId = UUID4

class ProcessingStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class CaseStatus(str, Enum):
    DRAFT = "DRAFT"
    UNDER_ASSESSMENT = "UNDER_ASSESSMENT"
    UNDER_REVIEW = "UNDER_REVIEW"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    ARCHIVED = "ARCHIVED"


class AssuranceStatus(str, Enum):
    ACTION_REQUIRED = "ACTION_REQUIRED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class EvidenceStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT = "INSUFFICIENT"


class FindingSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ChallengeStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    CLOSED = "CLOSED"


class RepairStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class RepairActionType(str, Enum):
    REVISE_REQUIREMENT = "REVISE_REQUIREMENT"
    MAINTAIN_WITH_JUSTIFICATION = "MAINTAIN_WITH_JUSTIFICATION"
    REQUEST_MORE_EVIDENCE = "REQUEST_MORE_EVIDENCE"


class ReviewDecision(str, Enum):
    APPROVE_DRAFT = "APPROVE_DRAFT"
    REQUEST_REVISION = "REQUEST_REVISION"
    REQUEST_EVIDENCE = "REQUEST_EVIDENCE"
    REJECT_DRAFT = "REJECT_DRAFT"


class DocumentType(str, Enum):
    TOR = "TOR"
    TECHNICAL_SPECIFICATION = "TECHNICAL_SPECIFICATION"
    OWNER_COST_ESTIMATE = "OWNER_COST_ESTIMATE"
    TECHNICAL_JUSTIFICATION = "TECHNICAL_JUSTIFICATION"
    SUPPLIER_QUOTATION = "SUPPLIER_QUOTATION"
    WARRANTY_EVIDENCE = "WARRANTY_EVIDENCE"
    EVALUATION_REPORT = "EVALUATION_REPORT"
    CONTRACT = "CONTRACT"
    OTHER = "OTHER"


class AnalysisType(str, Enum):
    REQUIREMENT_EXTRACTION = "REQUIREMENT_EXTRACTION"
    CONTRADICTION_DETECTION = "CONTRADICTION_DETECTION"


class ErrorDetail(StrictModel):
    field: str
    reason: str


class ErrorBody(StrictModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    retryable: bool


class Meta(StrictModel):
    request_id: str
    timestamp: UtcTimestamp
    api_version: Literal["v1"] = "v1"


T = TypeVar("T")


class Envelope(StrictModel, Generic[T]):
    success: bool
    data: T | None
    error: ErrorBody | None
    meta: Meta

    @model_validator(mode="after")
    def check_outcome(self):
        if self.success and self.error is not None:
            raise ValueError("Success cannot contain an error")
        if not self.success and (self.data is not None or self.error is None):
            raise ValueError("Failure requires null data and an error")
        return self


class Pagination(StrictModel):
    limit: Annotated[int, Field(strict=True, ge=1)]
    offset: Annotated[int, Field(strict=True, ge=0)]
    total: Annotated[int, Field(strict=True, ge=0)]


class VersionedMutation(StrictModel):
    expected_version: PositiveVersion


class HealthData(StrictModel):
    """PROPOSED health data; not one of the 36 business endpoint schemas."""
    status: Literal["ok"]
    demo_mode: bool
