from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header

from app.api.response import ApiError
from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class Actor:
    actor_id: UUID
    display_name: str
    role: str
    scopes: frozenset[str]


def get_actor(settings: Annotated[Settings, Depends(get_settings)]) -> Actor:
    # No client actor/reviewer fields or identity headers are authoritative.
    # Production OIDC validation is intentionally not implemented by the scaffold.
    if not settings.demo_mode or settings.demo_actor_id is None:
        raise ApiError(401, "AUTHENTICATION_REQUIRED", "Authentication is required")
    return Actor(settings.demo_actor_id, settings.demo_display_name, settings.demo_role, settings.demo_scopes)


def require_scope(scope: str):
    def dependency(actor: Annotated[Actor, Depends(get_actor)]) -> Actor:
        if scope not in actor.scopes:
            raise ApiError(403, "FORBIDDEN", "Required scope is not granted")
        return actor
    return dependency


def require_idempotency_key(
    key: Annotated[str, Header(alias="Idempotency-Key")],
) -> str:
    if key is None or not key.strip():
        # PROPOSED missing-key mapping; contract supplies no distinct missing-key code.
        raise ApiError(400, "VALIDATION_ERROR", "Idempotency-Key is required")
    return key


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise ApiError(409, "VERSION_CONFLICT", "The resource version has changed")
