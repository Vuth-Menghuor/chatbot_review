from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas.normalized_chat import NormalizedChatResponse
from app.services.chat_response_normalizer import normalize_chat_response


# These tests pin the API-layer response shape consumed by the frontend adapter.

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "service_responses"
SUPPORTED_BLOCK_TYPES = {
    "markdown",
    "summary",
    "key_value",
    "table",
    "details",
    "references",
    "clarification",
    "error",
    "chart",
    "suggestions",
    "coverage",
}


# Load captured service-style payloads from disk so contract tests are easy to compare with real services later.
def load_fixture(name: str):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


# Treat response.content as message text and message.content as blocks; this matches the current backend/frontend contract.
def assert_frontend_message_contract(response: NormalizedChatResponse) -> None:
    assert isinstance(response.response.content, str)
    assert isinstance(response.message.content, list)
    assert response.message.role == "assistant"
    assert all(block.type in SUPPORTED_BLOCK_TYPES for block in response.message.content)


# Calculator fixtures must keep service identity and the rich block order expected by the frontend renderers.
def test_calculator_normalized_response_contract():
    response = normalize_chat_response(load_fixture("calculator_oxen.json"))

    assert response.service == "calculator"
    assert response.response.content == "Estimated total import tax for oxen is 572,300 KHR."
    assert [block.type for block in response.message.content] == ["summary", "key_value", "key_value", "table", "references"]
    assert_frontend_message_contract(response)


# Trade fixtures must keep service identity and stable table/reference ordering.
def test_trade_normalized_response_contract():
    response = normalize_chat_response(load_fixture("trade_top_export_partners.json"))

    assert response.service == "trade"
    assert response.response.content == "Cambodia's top export partners in 2024 are available."
    assert [block.type for block in response.message.content] == ["markdown", "summary", "table", "references"]
    assert response.message.content[2].title == "Top Export Partners"
    assert_frontend_message_contract(response)


# Plain fallback responses should be safe, simple markdown plus suggestions, and should identify general service hints.
def test_fallback_normalized_response_contract():
    response = normalize_chat_response(load_fixture("fallback_plain_text.json"))

    assert response.service == "general"
    assert response.response.content == "Use the import declaration form for customs clearance."
    assert [block.type for block in response.message.content] == ["markdown", "suggestions"]
    assert_frontend_message_contract(response)


# Retrieval success fixtures should remain fallback markdown until a real RetrievalNormalizer is added.
def test_retrieval_success_contract_uses_safe_markdown_fallback():
    response = normalize_chat_response(load_fixture("retrieval_success.json"))

    assert response.service == "retrieval"
    assert response.response.content == "Importers must submit an import declaration, invoice, packing list, and transport document."
    assert response.coverage == "complete"
    assert response.confidence == "high"
    assert [block.type for block in response.message.content] == ["markdown"]
    assert_frontend_message_contract(response)


# General success fixtures should remain markdown fallback until a real GeneralNormalizer is added.
def test_general_success_contract_uses_safe_markdown_fallback():
    response = normalize_chat_response(load_fixture("general_success.json"))

    assert response.service == "general"
    assert response.response.content == "The GDCE chatbot can help with customs procedures, document requirements, and service routing."
    assert response.coverage == "complete"
    assert response.confidence == "medium"
    assert [block.type for block in response.message.content] == ["markdown"]
    assert_frontend_message_contract(response)


# General suggestions should use the existing suggestions block after markdown.
def test_general_suggestions_contract_keeps_suggestions_block():
    response = normalize_chat_response(load_fixture("general_with_suggestions.json"))

    assert response.service == "general"
    assert [block.type for block in response.message.content] == ["markdown", "suggestions"]
    assert response.message.content[1].items == [
        "What documents are needed for import?",
        "Calculate import tax",
        "Show Cambodia export partners",
    ]
    assert_frontend_message_contract(response)


# General clarification payloads should keep the existing clarification block contract.
def test_general_clarification_contract_keeps_clarification_block():
    response = normalize_chat_response(load_fixture("general_with_clarification.json"))

    assert response.service == "general"
    assert [block.type for block in response.message.content] == ["markdown", "clarification"]
    assert response.message.content[1].questions == [
        "Are you asking about import, export, tax calculation, or trade statistics?",
        "Which product or HS code should I use?",
    ]
    assert_frontend_message_contract(response)


# Failed general payloads should render an error block and keep service identity.
def test_general_failed_contract_keeps_error_block():
    response = normalize_chat_response(load_fixture("general_failed.json"))

    assert response.service == "general"
    assert response.status == "failed"
    assert response.response.content == ""
    assert [block.type for block in response.message.content] == ["error"]
    assert response.message.content[0].message == "General service is unavailable"
    assert_frontend_message_contract(response)


# Malformed general fixtures should still identify general and produce safe blocks.
def test_general_malformed_contract_stays_frontend_safe():
    response = normalize_chat_response(load_fixture("general_malformed.json"))

    assert response.service == "general"
    assert response.status == "completed"
    assert response.response.content == ""
    assert [block.type for block in response.message.content] == ["suggestions"]
    assert response.message.content[0].items == ["Try asking a customs question"]
    assert_frontend_message_contract(response)


# Partial retrieval fixtures should preserve limitations as the existing warning coverage block.
def test_retrieval_partial_contract_keeps_limitation_warning():
    response = normalize_chat_response(load_fixture("retrieval_partial_with_missing.json"))

    assert response.service == "retrieval"
    assert response.coverage == "partial"
    assert [block.type for block in response.message.content] == ["markdown", "coverage"]
    assert response.message.content[1].type == "coverage"
    assert response.message.content[1].tone == "warning"
    assert response.message.content[1].items == [
        "The available sources do not specify every permit required for the requested goods."
    ]
    assert_frontend_message_contract(response)


# Retrieval citations should normalize and deduplicate at the response source level.
def test_retrieval_citation_contract_deduplicates_sources():
    response = normalize_chat_response(load_fixture("retrieval_with_citations.json"))

    assert response.service == "retrieval"
    assert [block.type for block in response.message.content] == ["markdown"]
    assert [citation.title for citation in response.citations] == [
        "Import Declaration Guidance",
        "Transport Document Guidance",
    ]
    assert response.citations[0].document_id == "import-guidance"
    assert response.citations[0].chunk_index == 2
    assert_frontend_message_contract(response)


# Retrieval document fixtures can render both source references and the existing document table.
def test_retrieval_documents_contract_renders_references_and_document_table():
    response = normalize_chat_response(load_fixture("retrieval_with_documents.json"))

    assert response.service == "retrieval"
    assert [block.type for block in response.message.content] == ["markdown", "references", "table"]
    assert response.message.content[1].title == "References"
    assert response.message.content[1].items[0]["filename"] == "tariff.pdf"
    assert response.message.content[2].title == "Possible HS Codes"
    assert response.message.content[2].rows[0]["hs_code"] == "0102.29.11"
    assert_frontend_message_contract(response)


# Malformed retrieval fixtures should still identify retrieval and produce a valid envelope.
def test_retrieval_malformed_contract_stays_frontend_safe():
    response = normalize_chat_response(load_fixture("retrieval_malformed.json"))

    assert response.service == "retrieval"
    assert response.status == "completed"
    assert response.response.content == ""
    assert [block.type for block in response.message.content] == ["markdown"]
    assert response.message.content[0].text == ""
    assert_frontend_message_contract(response)


# Malformed payloads should normalize into a valid, frontend-safe response instead of throwing.
def test_malformed_payload_falls_back_to_safe_response():
    response = normalize_chat_response(load_fixture("malformed_payload.json"))

    assert response.service == "unknown"
    assert response.status == "completed"
    assert response.response.content == ""
    assert [block.type for block in response.message.content] == ["markdown"]
    assert_frontend_message_contract(response)


# Unknown raw values should still produce valid envelopes with a safe unknown service label.
@pytest.mark.parametrize("raw", [None, "", [], {"answer": ""}])
def test_unknown_payload_safety(raw):
    response = normalize_chat_response(raw)

    assert response.service == "unknown"
    assert response.status == "completed"
    assert_frontend_message_contract(response)
