from __future__ import annotations

import json
import logging
from pathlib import Path

from app.services.chat_response_normalizer import normalize_chat_response

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "service_responses"


def load_fixture(name: str):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def block_types(response):
    return [block.type for block in response.message.content]


def block_by_title(response, title):
    return next(block for block in response.message.content if getattr(block, "title", None) == title)


def test_successful_structured_calculator_response_contract_and_value_preservation():
    payload = load_fixture("calculator_petroleum_success.json")

    response = normalize_chat_response(payload)

    assert response.service == "calculator"
    assert response.intent == "calculation"
    assert response.status == "completed"
    assert block_types(response) == ["summary", "key_value", "key_value", "table", "details", "details"]

    summary = response.message.content[0]
    product = block_by_title(response, "Product Information")
    inputs = block_by_title(response, "Input Parameters")
    table = block_by_title(response, "Tax Breakdown")
    details = block_by_title(response, "Calculation Details")

    upstream = payload["calculator_result"]
    assert summary.data["total_tax"] == upstream["summary"]["total_tax"]
    assert summary.data["phase_gap"] == upstream["summary"]["phase_gap"]
    assert next(item for item in product.items if item.key == "hs_code").value == upstream["product"]["hs_code"]
    assert next(item for item in inputs.items if item.key == "declared_value").value == upstream["inputs"]["declared_value"]
    assert table.rows == upstream["tax_breakdown"]
    assert table.rows[0]["amount"] == upstream["tax_breakdown"][0]["amount"]
    assert table.rows[0]["rate"] == upstream["tax_breakdown"][0]["rate"]
    assert table.rows[1]["amount"] == upstream["tax_breakdown"][1]["amount"]
    assert "basis: Declared value" in details.items[0].content
    assert "total: 1200000" in details.items[0].content
    assert "component: CPP" in details.items[0].content


def test_plain_text_calculator_fallback_from_answer_contains_one_markdown_block():
    payload = load_fixture("calculator_plain_text_fallback.json")

    response = normalize_chat_response(payload)

    assert response.service == "calculator"
    assert response.intent == "calculation"
    assert block_types(response) == ["markdown"]
    assert response.message.content[0].text == payload["answer"]


def test_plain_text_calculator_fallback_from_message_contains_one_markdown_block():
    payload = {
        "request_id": "fixture-calculator-message-only",
        "session_id": "fixture-session-calculator-message-only",
        "intent": "calculation",
        "status": "completed",
        "message": "Calculator returned message-only text.",
    }

    response = normalize_chat_response(payload)

    assert response.service == "calculator"
    assert response.intent == "calculation"
    assert block_types(response) == ["markdown"]
    assert response.message.content[0].text == payload["message"]


def test_calculator_clarification_required_adds_clarification_block():
    payload = {
        "request_id": "fixture-calculator-clarification",
        "session_id": "fixture-session-calculator-clarification",
        "intent": "calculation",
        "status": "completed",
        "answer": "More information is needed.",
        "clarifications": ["What is the CIF value?", "What is the origin country?"],
    }

    response = normalize_chat_response(payload)

    assert response.service == "calculator"
    assert response.intent == "calculation"
    assert "clarification" in block_types(response)
    assert block_by_type(response, "clarification").questions == payload["clarifications"]


def test_calculator_clarification_required_does_not_render_error_block():
    payload = {
        "request_id": "fixture-calculator-engine-clarification",
        "session_id": "fixture-session-calculator-engine-clarification",
        "intent": "calculation",
        "status": "clarification_required",
        "clarification_required": True,
        "answer": "Please provide the engine displacement in cubic centimeters (cc).",
        "missing_fields": ["engine_cc"],
        "errors": ["Calculator service error"],
    }

    response = normalize_chat_response(payload)

    assert response.service == "calculator"
    assert response.intent == "calculation"
    assert response.status == "clarification_required"
    assert block_types(response) == ["markdown"]
    assert response.message.content[0].text == payload["answer"]
    assert response.errors == []


def test_failed_calculator_response_adds_error_block_and_failed_status():
    payload = load_fixture("calculator_failed.json")

    response = normalize_chat_response(payload)

    assert response.service == "calculator"
    assert response.intent == "calculation"
    assert response.status == "failed"
    assert block_types(response) == ["error"]
    assert response.message.content[0].message == "The calculator service is temporarily unavailable."
    assert response.errors[0].code == "CALCULATOR_SERVICE_UNAVAILABLE"
    assert response.errors[0].message == "The calculator service is temporarily unavailable."
    assert response.errors[0].retryable is True


def test_failed_calculator_response_logs_raw_error_without_exposing_internal_details(caplog):
    payload = {
        "request_id": "req-internal-calculator-error",
        "session_id": "sess-internal-calculator-error",
        "intent": "calculation",
        "status": "failed",
        "error": {
            "code": "UPSTREAM_CONNECTION_ERROR",
            "message": (
                "Traceback at http://calculator-service:8000/query using "
                "postgresql://api_user:secret@calculator-db/calculator"
            ),
        },
    }

    with caplog.at_level(logging.WARNING, logger="app.services.normalizers.calculator.errors"):
        response = normalize_chat_response(payload)

    assert response.status == "failed"
    assert response.errors[0].code == "CALCULATOR_SERVICE_UNAVAILABLE"
    assert response.message.content[0].message == "The calculator service is temporarily unavailable."
    public_text = f"{response.errors[0].message} {response.message.content[0].message}"
    assert "Traceback" not in public_text
    assert "calculator-service" not in public_text
    assert "postgresql://" not in public_text
    assert any(
        record.message.startswith("calculator_upstream_error")
        and "req-internal-calculator-error" in record.message
        and "Traceback" in record.message
        for record in caplog.records
    )


def test_malformed_calculator_response_is_stable_and_does_not_expose_internal_exception():
    payload = load_fixture("calculator_malformed.json")

    response = normalize_chat_response(payload)

    assert response.request_id == str(payload["request_id"])
    assert response.service == "calculator"
    assert response.status == "completed"
    assert block_types(response) == ["clarification", "error"]
    assert "Traceback" not in response.response.content
    assert "Exception" not in response.response.content
    assert all("Traceback" not in getattr(block, "message", "") for block in response.message.content)
    assert all("Exception" not in getattr(block, "message", "") for block in response.message.content)


def test_unknown_calculator_fields_do_not_break_normalization():
    payload = load_fixture("calculator_petroleum_success.json")
    payload["unexpected_top_level"] = {"nested": ["value"]}
    payload["calculator_result"]["unexpected_structured_field"] = {
        "not_part_of_contract": True,
        "value": "preserve upstream elsewhere but do not render by guessing",
    }

    response = normalize_chat_response(payload)

    assert response.service == "calculator"
    assert response.intent == "calculation"
    assert response.status == "completed"
    assert block_types(response) == ["summary", "key_value", "key_value", "table", "details", "details"]


def test_calculator_top_level_citations_prevent_duplicate_references_block():
    response = normalize_chat_response(
        {
            "request_id": "req-calculator-citations",
            "session_id": "sess-calculator-citations",
            "intent": "calculation",
            "answer": "Calculation complete.",
            "citations": [
                {
                    "id": "tariff-1",
                    "title": "Customs Tariff",
                    "url": "https://example.test/tariff",
                }
            ],
            "calculator_result": {
                "summary": {"total_tax": "100 KHR"},
                "references": [
                    {
                        "id": "tariff-1",
                        "title": "Customs Tariff",
                        "url": "https://example.test/tariff",
                    }
                ],
            },
        }
    )

    assert [citation.title for citation in response.citations] == ["Customs Tariff"]
    assert "references" not in block_types(response)


def test_calculator_top_level_string_citations_prevent_duplicate_references_block():
    response = normalize_chat_response(
        {
            "request_id": "req-calculator-string-citations",
            "session_id": "sess-calculator-string-citations",
            "intent": "calculation",
            "answer": "Calculation complete.",
            "citations": ["Customs Tariff 2022"],
            "calculator_result": {
                "summary": {"total_tax": "100 KHR"},
                "references": [
                    {
                        "id": "tariff-1",
                        "title": "Customs Tariff 2022",
                        "url": "https://example.test/tariff",
                    }
                ],
            },
        }
    )

    assert [citation.title for citation in response.citations] == ["Customs Tariff 2022"]
    assert "references" not in block_types(response)


def test_calculator_empty_string_citations_do_not_suppress_internal_references_block():
    response = normalize_chat_response(
        {
            "request_id": "req-calculator-empty-string-citations",
            "session_id": "sess-calculator-empty-string-citations",
            "intent": "calculation",
            "answer": "Calculation complete.",
            "citations": ["", "   "],
            "calculator_result": {
                "summary": {"total_tax": "100 KHR"},
                "references": [
                    {
                        "id": "tariff-1",
                        "title": "Customs Tariff",
                        "url": "https://example.test/tariff",
                    }
                ],
            },
        }
    )

    assert "references" in block_types(response)
    assert block_by_title(response, "References").items[0]["title"] == "Customs Tariff"


def test_legacy_calculator_preserves_real_upstream_values_and_steps():
    payload = load_fixture("calculator_general_product_success.json")

    response = normalize_chat_response(payload)

    product = block_by_title(response, "Product Information")
    inputs = block_by_title(response, "Input Parameters")
    table = block_by_title(response, "Tax Breakdown")
    details = block_by_title(response, "Calculation Details")

    assert next(item for item in product.items if item.key == "HS Code").value == (
        "8702.40.49 (Motor vehicles for the transport of ten or more persons, including the driver. > "
        "With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other)"
    )
    assert next(item for item in product.items if item.key == "Origin Country").value == "CN"
    assert next(item for item in inputs.items if item.key == "CIF Value").value == "400,000,000 KHR"
    assert next(item for item in inputs.items if item.key == "Exchange Rate").value == "1 KHR = 1.00 KHR"
    assert table.rows[0]["tax_component"] == "Import Taxes (COP)"
    assert table.rows[0]["tax_base_khr"] == "400,000,000"
    assert table.rows[0]["rate"] == "15.00%"
    assert table.rows[0]["amount_khr"] == "60,000,000"
    assert table.rows[1]["amount_khr"] == "46,000,000"
    assert table.rows[2]["amount_khr"] == "50,600,000"
    assert table.rows[4]["amount_khr"] == "156,660,000"
    assert details.items[0].title == "Step 1: Currency Confirmation (KHR)"
    assert "CIF Value = 400,000,000 KHR (already in local currency)" in details.items[0].content
    assert "Import Taxes (COP) = Customs Value x Import Tax Rate" in details.items[1].content


def block_by_type(response, block_type):
    return next(block for block in response.message.content if block.type == block_type)
