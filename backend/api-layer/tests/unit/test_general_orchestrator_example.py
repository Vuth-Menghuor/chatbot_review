import json
from pathlib import Path

from app.services.chat_response_normalizer import normalize_chat_response


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "service_responses"


def test_exact_general_orchestrator_example_normalizes_to_frontend_contract():
    raw_payload = json.loads((FIXTURE_DIR / "general_orchestrator_example.json").read_text())

    response = normalize_chat_response(raw_payload)

    assert response.api_version == "1.0"
    assert response.service == "general"
    assert response.intent == "general"
    assert response.status == "completed"
    assert response.message.content[0].type == "markdown"
    assert response.message.content[0].text == raw_payload["answer"]
    assert response.response.content == raw_payload["answer"]
    assert len(response.citations) == 1
    assert response.citations[0].id == "1021"
    assert response.suggestions == raw_payload["suggestion"]
    assert response.metrics["latency_ms"] == raw_payload["latency_ms"]
    assert response.debug is None


def test_exact_general_orchestrator_example_preserves_original_answer_text():
    raw_payload = json.loads((FIXTURE_DIR / "general_orchestrator_example.json").read_text())

    response = normalize_chat_response(raw_payload)

    assert response.response.content == raw_payload["answer"]
    assert response.message.content[0].text == raw_payload["answer"]
