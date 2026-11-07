from typing import Annotated, Literal

from pydantic import Field, UUID4, field_validator

from app.schemas.p0 import Citation, ExecutionView
from app.schemas.shared import PositiveVersion, StrictModel, UtcTimestamp

Text = Annotated[str, Field(min_length=1, max_length=4000)]
Evidence = Annotated[list[Citation], Field(min_length=1, max_length=30)]


class FindingScenarioCreate(StrictModel):
    finding_id: UUID4
    expected_case_version: PositiveVersion
    expected_finding_version: PositiveVersion
    assumptions: Annotated[list[Text], Field(max_length=12)] = []

    @field_validator("assumptions")
    @classmethod
    def meaningful_assumptions(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError("Assumptions cannot be blank")
        return values


class Baseline(StrictModel):
    description: Text
    assumptions: list[Text]
    evidence: Evidence


class Alternative(StrictModel):
    title: Text
    change: Text
    expected_effect: Text
    limitations: Annotated[list[Text], Field(min_length=1, max_length=12)]
    evidence: Evidence


class ScenarioOutput(StrictModel):
    title: Text
    baseline: Baseline
    alternatives: Annotated[list[Alternative], Field(min_length=1, max_length=4)]
    remaining_uncertainties: Annotated[list[Text], Field(min_length=1, max_length=12)]


class DeterministicCheck(StrictModel):
    check_type: str
    status: Literal["PASS", "CONCERN", "UNKNOWN", "NOT_APPLICABLE"]
    description: str
    observations: dict


class FindingScenarioView(ScenarioOutput):
    scenario_id: UUID4
    case_id: UUID4
    finding_id: UUID4
    analysis_job_id: UUID4
    status: Literal["DRAFT", "NEEDS_REVIEW"]
    deterministic_checks: list[DeterministicCheck]
    ai_execution: ExecutionView
    created_at: UtcTimestamp
