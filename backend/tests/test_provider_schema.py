import json
import re
from types import SimpleNamespace
from uuid import uuid1, uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.p0 import AnalysisOutput, Citation
from app.schemas.decisions import ChallengeOutput, RepairOutput
from app.services.ai.provider import OpenAIAnalysisProvider
from app.services.ai.decisions import OpenAIDecisionProvider
from app.services.ai.provider_schema import provider_output_schema, UUID4_PATTERN


@pytest.mark.parametrize("output", [AnalysisOutput, ChallengeOutput, RepairOutput])
def test_provider_schema_supports_uuid_without_weakening_uuid4(output):
    original = output.model_json_schema()
    schema = provider_output_schema(output)
    citation = schema["$defs"]["Citation"]["properties"]["document_id"]
    assert citation["format"] == "uuid"
    assert citation["pattern"] == UUID4_PATTERN
    assert re.fullmatch(citation["pattern"], str(uuid4()))
    assert re.fullmatch(citation["pattern"], str(uuid4()).upper())
    assert not re.fullmatch(citation["pattern"], str(uuid1()))
    assert original == output.model_json_schema()
    assert original["$defs"]["Citation"]["properties"]["document_id"]["format"] == "uuid4"
    assert '"format": "uuid4"' not in json.dumps(schema)
    with pytest.raises(ValidationError):
        Citation(document_id=uuid1(), page_number=1, excerpt="Test only")


@pytest.mark.parametrize("kind", ["analysis", "challenge", "repair"])
def test_each_adapter_sends_supported_schema_to_responses(kind):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text="{}", model="test-runtime-model", usage=None, status="completed")
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    settings = Settings(_env_file=None, openai_api_key="test-only-not-used")
    if kind == "analysis":
        OpenAIAnalysisProvider(settings, client=client).analyze([], [])
    else:
        OpenAIDecisionProvider(settings, client=client).generate(kind, {})
    schema = calls[0]["text"]["format"]["schema"]
    assert calls[0]["text"]["format"]["strict"] is True
    assert schema["$defs"]["Citation"]["properties"]["document_id"]["format"] == "uuid"
