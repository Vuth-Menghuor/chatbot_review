import json
from pathlib import Path

import pytest

from app.schemas.normalized_chat import NormalizedChatResponse
from app.services.chat_response_normalizer import normalize_chat_response


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "service_responses"


def test_normalized_response_includes_api_contract_version_from_fixture():
    payload = json.loads((FIXTURE_DIR / "general_success.json").read_text())

    response = normalize_chat_response(payload)

    assert response.api_version == "1.0"
    assert response.model_dump(mode="json")["api_version"] == "1.0"


def test_response_schema_documents_api_version():
    schema = NormalizedChatResponse.model_json_schema()

    assert schema["properties"]["api_version"]["const"] == "1.0"


def test_openapi_documents_chat_send_api_version_when_app_dependencies_are_available():
    pytest.importorskip("passlib")
    from app.main import app

    schema = app.openapi()

    normalized_response_schema = schema["components"]["schemas"]["NormalizedChatResponse"]
    api_version = normalized_response_schema["properties"]["api_version"]

    assert "/api/v1/chat/send" in schema["paths"]
    assert api_version["const"] == "1.0"
