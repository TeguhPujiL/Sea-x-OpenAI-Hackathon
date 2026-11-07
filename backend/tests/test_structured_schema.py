import json
import re
from uuid import uuid1, uuid4
import pytest
from pydantic import ValidationError
from app.schemas.p0 import AnalysisOutput, Citation
from app.schemas.decisions import ChallengeOutput, RepairOutput
from app.services.ai.structured_schema import structured_output_schema, UUID4_PATTERN


@pytest.mark.parametrize('model', [AnalysisOutput, ChallengeOutput, RepairOutput])
def test_provider_schema_uses_standard_uuid_without_changing_contract(model):
    original = model.model_json_schema()
    provider = structured_output_schema(model)
    assert '"format": "uuid4"' in json.dumps(original)
    assert '"format": "uuid4"' not in json.dumps(provider)
    assert provider['$defs']['Citation']['properties']['document_id']['format'] == 'uuid'
    assert provider['$defs']['Citation']['properties']['document_id']['pattern'] == UUID4_PATTERN
    assert provider['additionalProperties'] is False
    assert model.model_json_schema() == original


def test_v4_constraint_is_preserved_by_pattern_and_backend():
    value = {'document_id': str(uuid4()), 'page_number': 1, 'excerpt': 'Synthetic evidence'}
    assert Citation.model_validate(value).document_id.version == 4
    assert re.fullmatch(UUID4_PATTERN, value['document_id'])
    value['document_id'] = str(uuid1())
    assert not re.fullmatch(UUID4_PATTERN, value['document_id'])
    with pytest.raises(ValidationError):
        Citation.model_validate(value)
