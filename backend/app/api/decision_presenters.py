from app.api.presenters import fields
from app.schemas.decisions import ChallengeView, RepairView


def challenge_data(row):
    data = {"challenge_id": str(row.id), **fields(row, "case_id finding_id status question risk_rationale ai_execution_id human_edits version created_at updated_at"), "requested_evidence": row.requested_evidence_json}
    ChallengeView.model_validate(data)
    return data


def repair_data(row):
    data = {"repair_proposal_id": str(row.id), **fields(row, "finding_id case_id status action_type before_text proposed_text justification simulation_id ai_execution_id human_edits version created_at updated_at")}
    RepairView.model_validate(data)
    return data
