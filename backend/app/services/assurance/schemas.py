"""Feature-local v1.1 schemas. Shared schema changes remain with Teguh."""
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import Field, field_validator

from app.schemas.shared import (
    AssuranceStatus, Envelope, Pagination, PositiveVersion, ResourceId,
    ReviewDecision, StrictModel, UtcTimestamp,
)


class ReviewCreate(StrictModel):
    repair_proposal_id: ResourceId
    decision: ReviewDecision
    decision_reason: Annotated[str, Field(min_length=10, max_length=4000)]
    expected_case_version: PositiveVersion

    @field_validator("decision_reason")
    @classmethod
    def meaningful_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10 or len(value.split()) < 3 or sum(c.isalnum() for c in value) < 6:
            raise ValueError("Explain the decision in at least three words and ten characters")
        return value


class ActorView(StrictModel):
    actor_id: ResourceId
    display_name: str
    role: str


class ReviewView(StrictModel):
    review_id: ResourceId
    case_id: ResourceId
    repair_proposal_id: ResourceId
    decision: ReviewDecision
    decision_reason: str
    review_status: Literal["COMPLETED"]
    reviewer: ActorView
    assurance_status_after: AssuranceStatus
    created_at: UtcTimestamp


class AuditActorView(StrictModel):
    actor_id: ResourceId
    display_name: str | None
    role: str | None


class ResourceView(StrictModel):
    type: str
    id: ResourceId
    version: PositiveVersion


class AuditView(StrictModel):
    event_id: ResourceId
    case_id: ResourceId
    event_type: str
    actor: AuditActorView
    resource: ResourceView
    occurred_at: UtcTimestamp
    request_id: str
    details: dict
    previous_hash: str | None
    event_hash: str | None


T = TypeVar("T")


class Page(StrictModel, Generic[T]):
    items: list[T]
    pagination: Pagination


class ListQuery(StrictModel):
    limit: Annotated[int, Field(ge=1, le=200)] = 20
    offset: Annotated[int, Field(ge=0)] = 0


class AuditQuery(ListQuery):
    limit: Annotated[int, Field(ge=1, le=200)] = 50


# Prevent FastAPI's default 422 schema from misrepresenting Appendix B behavior.
ERROR_RESPONSES = {
    status: {"model": Envelope[None], "description": description}
    for status, description in {
        400: "VALIDATION_ERROR", 401: "AUTHENTICATION_REQUIRED", 403: "FORBIDDEN",
        404: "RESOURCE_NOT_FOUND", 409: "VERSION_CONFLICT, INVALID_STATE_TRANSITION or IDEMPOTENCY_KEY_REUSED",
        422: "EVIDENCE_VALIDATION_FAILED", 500: "INTERNAL_ERROR",
    }.items()
}
