"""Provider schema compatibility; local Pydantic validation stays authoritative."""


def structured_output_schema(model):
    """Translate Pydantic's uuid4 format to the provider-supported uuid format."""
    schema = model.model_json_schema()

    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "string" and node.get("format") == "uuid4":
                node["format"] = "uuid"
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema
