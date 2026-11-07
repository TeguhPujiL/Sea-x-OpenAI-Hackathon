import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.response import ApiError
from app.core.config import Settings
from app.main import create_app
from app.schemas import shared
from app.services.assurance.schemas import ReviewCreate
from conftest import assert_envelope, post_review

DOCS = Path(__file__).resolve().parents[2] / "docs"
CONTRACT = json.loads((DOCS / "contract_snapshot.json").read_text())
ASSURANCE = json.loads((DOCS / "assurance_contract_snapshot.json").read_text())


def test_openapi_routes_and_success_codes_match_source_snapshot():
    schema = create_app().openapi()
    inventory = {(r["method"], "/api/v1" + r["path"]): r for r in CONTRACT["endpoints"]}
    implemented = {(method.upper(), path): op for path, operations in schema["paths"].items()
                   if path != "/api/v1/health" for method, op in operations.items()}
    owned = {(m, "/api/v1" + p) for m, p in ASSURANCE["owned_endpoints"]}
    assert owned <= set(implemented) <= set(inventory)
    for key, op in implemented.items():
        contract = inventory[key]
        assert [int(s) for s in op["responses"] if s.startswith("2")] == [contract["success_code"]]
        header = next((p for p in op["parameters"] if p["name"] == "Idempotency-Key"), None)
        if contract["idempotency_key_required"]:
            assert header["in"] == "header" and header["required"] is True
        # Framework validation is explicitly documented as 400; the declared
        # 422 is evidence validation, never a framework validation envelope.
        assert "HTTPValidationError" not in str(op["responses"])
        success = op["responses"][str(contract["success_code"])]
        ref = success["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
        envelope = schema["components"]["schemas"][ref]
        assert set(envelope["properties"]) == set(ASSURANCE["success_envelope"])


def test_openapi_request_response_fields_enums_and_closed_models():
    schemas = create_app().openapi()["components"]["schemas"]
    request = schemas[ASSURANCE["request_schema"]]
    assert set(request["properties"]) == set(ASSURANCE["request_properties"])
    assert set(request["required"]) == set(ASSURANCE["request_properties"])
    assert request["additionalProperties"] is False
    for name, expected in ASSURANCE["request_properties"].items():
        actual = request["properties"][name]
        for field, value in expected.items():
            if field == "enum_ref":
                assert actual["$ref"] == f"#/components/schemas/{value}"
            else:
                assert actual[field] == value
    for name, expected in ASSURANCE["response_properties"].items():
        assert set(schemas[name]["properties"]) == set(expected)
        assert set(schemas[name]["required"]) == set(expected)
        assert schemas[name]["additionalProperties"] is False
    assert schemas["ReviewView"]["properties"]["review_status"]["const"] == "COMPLETED"
    assert set(schemas["Pagination"]["properties"]) == set(ASSURANCE["pagination"])
    assert set(schemas["ErrorBody"]["properties"]) == set(ASSURANCE["error_fields"])
    for name, values in CONTRACT["enums"].items():
        assert [v.value for v in getattr(shared, name)] == values
        if name in schemas:
            assert schemas[name]["enum"] == values


def test_approve_case_is_rejected_with_valid_repair_and_envelope(qa):
    response = post_review(qa, payload={**qa.payload, "decision": "APPROVE_CASE"})
    assert_envelope(response, 400, "VALIDATION_ERROR")
    assert "APPROVE_CASE" not in [x.value for x in shared.ReviewDecision]


@pytest.mark.parametrize("entry", CONTRACT["error_catalog"], ids=lambda x: x["code"])
def test_appendix_b_error_envelopes_remain_stable(entry):
    # Fault injection verifies HTTP serialization/catalog stability. This does
    # not represent a live provider, upload or extraction integration test.
    app = create_app(Settings(database_url="sqlite:///:memory:"))
    @app.get("/test-injected-error")
    def injected():
        raise ApiError(entry["http_status"], entry["code"], "Synthetic contract fault",
                       retryable=entry["code"] in {"RATE_LIMITED", "AI_PROVIDER_TIMEOUT"})
    with TestClient(app) as client:
        assert_envelope(client.get("/test-injected-error"), entry["http_status"], entry["code"])


def test_bad_json_uuid_and_missing_read_resources(qa):
    assert_envelope(qa.client.post(qa.path, content='{invalid', headers={"Content-Type": "application/json", "Idempotency-Key": "bad"}), 400, "VALIDATION_ERROR")
    assert_envelope(qa.client.get("/api/v1/reviews/not-a-uuid"), 400, "VALIDATION_ERROR")
    for prefix in ("reviews", "audit-events"):
        assert_envelope(qa.client.get(f"/api/v1/{prefix}/00000000-0000-4000-8000-000000000000"), 404, "RESOURCE_NOT_FOUND")
