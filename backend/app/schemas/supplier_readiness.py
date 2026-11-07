"""PROPOSED P1.1 supplier analysis requests; no new P0 EvidenceStatus values."""
from typing import Annotated
from pydantic import Field, UUID4
from app.schemas.shared import StrictModel, PositiveVersion
from app.schemas.evaluation import SupplierRef, Ids


class ReadinessCreate(StrictModel):
    supplier_ref: SupplierRef
    requirement_document_ids: Ids
    supplier_document_ids: Annotated[list[UUID4], Field(max_length=50)]
    include_remediation_guidance: bool = True


class RevalidationCreate(ReadinessCreate):
    expected_version: PositiveVersion
