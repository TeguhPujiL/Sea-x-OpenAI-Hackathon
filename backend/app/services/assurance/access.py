"""Explicit backend case grants; identity alone never grants case access.

Replace get_case_grants with a trusted authorization adapter during core integration.
Neither request bodies nor identity headers can populate these grants.
"""
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from pydantic import UUID4
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.orm import Session

from app.api.response import ApiError
from app.core.config import ROOT
from app.core.security import Actor, require_idempotency_key
from app.models import Case


class AssuranceAccess(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_prefix="PROCUREMIND_ASSURANCE_", extra="ignore",
    )
    case_grants: dict[UUID4, frozenset[UUID4]] = {}


def get_case_grants() -> dict[UUID, frozenset[UUID]]:
    return AssuranceAccess().case_grants


CaseGrants = Annotated[dict[UUID, frozenset[UUID]], Depends(get_case_grants)]


def review_idempotency_key(key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]) -> str:
    return require_idempotency_key(key)


def case_for_actor(session: Session, case_id: UUID, actor: Actor, grants: dict,
                   *, writing: bool = False) -> Case:
    if case_id not in grants.get(actor.actor_id, frozenset()):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Case not found")
    case = session.get(Case, case_id)
    if case is None or (writing and case.deleted_at is not None):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Case not found")
    # Read-only review/audit history remains available for authorized deleted cases.
    return case
