"""Compatibility import for local QA; dev owns the canonical provider schema."""
from app.services.ai.schema import UUID4_PATTERN, structured_output_schema as provider_output_schema

__all__ = ["UUID4_PATTERN", "provider_output_schema"]
