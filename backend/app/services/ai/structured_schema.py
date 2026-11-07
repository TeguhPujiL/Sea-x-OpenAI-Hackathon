"""Adapt provider schemas while preserving the internal UUID4 contract."""
from pydantic import BaseModel

UUID4_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"


def structured_output_schema(model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()

    def visit(value):
        if isinstance(value, dict):
            if value.get("format") == "uuid4":
                # Structured Outputs accepts the standard uuid format, not
                # Pydantic's uuid4 extension. Retain v4 in the pattern as well.
                value["format"] = "uuid"
                value["pattern"] = UUID4_PATTERN
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(schema)
    return schema
