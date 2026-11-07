"""Contract requests/responses and versioned internal decision-generation output."""
from typing import Annotated, Literal
from pydantic import Field, UUID4, model_validator
from app.schemas.shared import StrictModel, PositiveVersion, UtcTimestamp, ChallengeStatus, RepairStatus, RepairActionType
from app.schemas.p0 import NonEmpty, Citation


class ChallengeCreate(StrictModel):
    finding_id: UUID4
    generation_mode: Literal["AI_ASSISTED"]
    requested_evidence: Annotated[list[NonEmpty], Field(min_length=1)]


class ChallengePatch(StrictModel):
    question: NonEmpty | None = None
    status: ChallengeStatus | None = None
    expected_version: PositiveVersion

    @model_validator(mode="after")
    def disallow_null(self):
        if any(getattr(self,k) is None for k in self.model_fields_set):
            raise ValueError("Provided fields cannot be null")
        return self


class RepairCreate(StrictModel):
    action_type: RepairActionType
    simulation_id: UUID4
    generation_mode: Literal["AI_ASSISTED"]


class RepairPatch(StrictModel):
    proposed_text: NonEmpty | None = None
    status: RepairStatus | None = None
    expected_version: PositiveVersion

    @model_validator(mode="after")
    def disallow_null(self):
        if any(getattr(self,k) is None for k in self.model_fields_set):
            raise ValueError("Provided fields cannot be null")
        return self


class ChallengeOutput(StrictModel):
    question: NonEmpty
    risk_rationale: NonEmpty
    evidence: Annotated[list[Citation], Field(min_length=1)]


class RepairOutput(StrictModel):
    before_text: NonEmpty
    proposed_text: NonEmpty
    justification: NonEmpty
    evidence: Annotated[list[Citation], Field(min_length=1)]


class ChallengeView(StrictModel):
    challenge_id: UUID4
    case_id: UUID4
    finding_id: UUID4
    status: ChallengeStatus
    question: str
    risk_rationale: str
    requested_evidence: list[str]
    ai_execution_id: UUID4 | None
    human_edits: bool
    version: PositiveVersion
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class RepairView(StrictModel):
    repair_proposal_id: UUID4
    finding_id: UUID4
    case_id: UUID4
    status: RepairStatus
    action_type: RepairActionType
    before_text: str
    proposed_text: str
    justification: str
    simulation_id: UUID4 | None
    ai_execution_id: UUID4 | None
    human_edits: bool
    version: PositiveVersion
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class ChallengeDeleted(StrictModel):
    challenge_id: UUID4
    deleted_at: UtcTimestamp


class RepairDeleted(StrictModel):
    repair_proposal_id: UUID4
    deleted_at: UtcTimestamp
