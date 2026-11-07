"""Shared primitives only. Wire schemas await API Contract v1.1 verification."""
from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


IdrAmount = Annotated[int, Field(strict=True)]
PositiveVersion = Annotated[int, Field(strict=True, ge=1)]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_z(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware timestamp is required")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

# No business enums or request schemas until the primary contract is available.
