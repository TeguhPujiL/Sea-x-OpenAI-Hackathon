from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class DemoActor:
    actor_id: UUID


def get_demo_actor(settings: Settings = Depends(get_settings)) -> DemoActor:
    """Trusted server configuration only; never accept identity from the client.

    Demo identity is not production authentication or resource authorization.
    """
    if settings.demo_actor_id is None:
        raise HTTPException(status_code=503, detail="Demo actor is not configured")
    return DemoActor(actor_id=settings.demo_actor_id)
