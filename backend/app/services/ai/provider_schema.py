"""Translate Pydantic-only UUID4 format to supported Structured Outputs JSON.

This is an outbound provider adapter; public schemas and local UUID4 response
validation retain their exact contract behavior.
"""
from pydantic import BaseModel

UUID4_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"


def provider_output_schema(output: type[BaseModel]) -> dict:
    schema = output.model_json_schema()

    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "string" and node.get("format") == "uuid4":
                node["format"] = "uuid"
                node["pattern"] = UUID4_PATTERN
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema
