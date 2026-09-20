from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path
from typing import get_args, get_origin

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
    "prediction",
    "details",
    "references",
    "official_reference",
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
    assert response.api_version == "1.0"
    assert response.request_id
    assert response.session_id
    assert response.status in {"completed", "clarification_required", "partial", "processing", "failed"}
    assert response.response.type in {"markdown", "table", "chart"}
    assert isinstance(response.response.content, str)
    assert isinstance(response.response.limitations, list)
    assert isinstance(response.message.content, list)
    assert response.message.role == "assistant"
    assert isinstance(response.citations, list)
    assert isinstance(response.suggestions, list)
    assert isinstance(response.clarifications, list)
    assert isinstance(response.errors, list)
    assert isinstance(response.metrics, dict)
    assert all(block.type in SUPPORTED_BLOCK_TYPES for block in response.message.content)


def test_normalized_response_status_schema_keeps_existing_backend_statuses_only():
    annotation = NormalizedChatResponse.model_fields["status"].annotation

    assert get_origin(annotation).__name__ == "Literal"
    assert set(get_args(annotation)) == {
        "processing",
        "completed",
        "clarification_required",
        "partial",
        "failed",
    }


# Calculator fixtures must keep service identity and the rich block order expected by the frontend renderers.
def test_calculator_normalized_response_contract():
    response = normalize_chat_response(load_fixture("calculator_oxen.json"))

    assert response.service == "calculator"
    assert response.response.content == "Estimated total import tax for oxen is 572,300 KHR."
    assert [block.type for block in response.message.content] == ["summary", "key_value", "key_value", "table", "references"]
    assert not any(getattr(block, "text", None) == response.response.content for block in response.message.content)
    assert_frontend_message_contract(response)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "calculator_petroleum_success.json",
        "calculator_general_product_success.json",
        "calculator_missing_fields.json",
        "calculator_failed.json",
        "calculator_malformed.json",
        "calculator_plain_text_fallback.json",
        "calculator_business_inconsistency.json",
    ],
)
def test_calculator_fixture_variants_share_one_normalized_contract(fixture_name: str):
    response = normalize_chat_response(load_fixture(fixture_name))

    assert response.service == "calculator"
    assert response.intent == "calculation"
    assert_frontend_message_contract(response)


# Trade fixtures must keep service identity and stable table/reference ordering.
def test_trade_normalized_response_contract():
    response = normalize_chat_response(load_fixture("trade_top_export_partners.json"))

    assert response.service == "trade"
    assert response.response.content == "Cambodia's top export partners in 2024 are available."
    assert [block.type for block in response.message.content] == ["markdown", "summary", "table", "references"]
    assert response.message.content[2].title == "Top Export Partners"
    assert_frontend_message_contract(response)


def test_trade_orchestrator_contract_synthetic_fixture_normalizes_to_blocks():
    response = normalize_chat_response(load_fixture("trade_orchestrator_contract_synthetic.json"))

    assert response.service == "trade"
    assert response.intent == "trade_query"
    assert response.response.content == "Cambodia's top export partners in 2024 are shown below."
    assert [block.type for block in response.message.content] == ["markdown", "table", "suggestions"]
    assert response.message.content[0].text == response.response.content
    assert response.message.content[1].title == "Top Export Partners"
    assert response.message.content[1].rows == [
        {"partner_country": "Vietnam", "value_usd": 1200000},
        {"partner_country": "Thailand", "value_usd": 900000},
    ]
    assert response.message.content[2].items == [
        "Show export values by year",
        "Compare exports with imports",
    ]
    assert_frontend_message_contract(response)


def test_trade_query_intent_maps_to_trade_service_without_rewriting_intent():
    response = normalize_chat_response({
        "intent": "trade_query",
        "answer": "Trade answer.",
    })

    assert response.service == "trade"
    assert response.intent == "trade_query"
    assert response.response.content == "Trade answer."
    assert [block.type for block in response.message.content] == ["markdown"]
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
    assert response.confidence is None
    assert response.response.confidence is None
    assert [block.type for block in response.message.content] == ["markdown"]
    assert_frontend_message_contract(response)


def test_hs_code_lookup_intent_maps_to_retrieval_service_without_rewriting_intent():
    payload = {
        "request_id": "fixture-hs-code-lookup",
        "session_id": "fixture-session-retrieval",
        "question": "What is the HS code for cotton fabric?",
        "answer": "The service needs more detail about the cotton fabric.",
        "intent": "hs_code_lookup",
        "status": "clarification_required",
        "citations": [],
        "clarifications": [
            "Is the cotton fabric woven, knitted, or crocheted?"
        ],
        "errors": [],
        "latency_ms": 10976,
        "metadata": {},
        "table": None,
        "visualization": None,
        "message": "The service needs more detail about the cotton fabric.",
        "suggestion": [],
    }

    response = normalize_chat_response(payload)

    assert response.service == "retrieval"
    assert response.intent == "hs_code_lookup"
    assert response.status == "clarification_required"
    assert response.query == "What is the HS code for cotton fabric?"
    assert response.response.content == payload["answer"]
    assert [block.type for block in response.message.content] == ["markdown", "clarification"]
    assert response.message.content[0].text == payload["answer"]
    assert response.message.content[1].questions == [
        "Is the cotton fabric woven, knitted, or crocheted?"
    ]
    assert response.metrics["latency_ms"] == 10976
    assert_frontend_message_contract(response)


@pytest.mark.parametrize(
    ("upstream_status", "normalized_status"),
    [
        ("clarification_required", "completed"),
        ("completed", "completed"),
        ("failed", "failed"),
        ("unexpected_future_status", "completed"),
    ],
)
def test_retrieval_status_preserves_supported_workflow_states_and_safely_falls_back(upstream_status: str, normalized_status: str):
    response = normalize_chat_response({
        "request_id": f"fixture-retrieval-status-{upstream_status}",
        "session_id": "fixture-session-retrieval",
        "intent": "hs_code_lookup",
        "status": upstream_status,
        "answer": "Retrieval answer from the upstream service.",
    })

    assert response.service == "retrieval"
    assert response.status == normalized_status
    assert_frontend_message_contract(response)


def test_current_cotton_fabric_payload_matches_required_normalized_output():
    upstream = load_fixture("retrieval_cotton_fabric_clarification_required.json")
    chat = SimpleNamespace(id="bruno-local-session", project_id=None)

    assert isinstance(upstream["message"], str)
    assert upstream["message"] == upstream["answer"]
    assert "content" not in upstream["message"]
    assert "5208.39.00" in upstream["answer"]
    assert "5408.10.90" in upstream["answer"]
    assert "5408.10.10" in upstream["answer"]

    response = normalize_chat_response(upstream, chat=chat)

    assert response.api_version == "1.0"
    assert response.request_id == "cf827455-bd51-4424-a944-a3a3582244b7"
    assert response.session_id == "bruno-local-session"
    assert response.chat_id == "bruno-local-session"
    assert response.status == "clarification_required"
    assert response.service == "retrieval"
    assert response.intent == "hs_code_lookup"
    assert response.query == "What is the HS code for cotton fabric?"
    assert response.language == "en"
    assert response.coverage == "unknown"
    assert response.confidence is None
    assert response.response.type == "markdown"
    assert response.response.coverage == "unknown"
    assert response.response.confidence is None
    assert upstream["metadata"]["candidate_confidence"] == "low"
    assert upstream["metadata"]["llm_confidence"] == 0.99
    assert response.confidence != "high"
    assert response.response.confidence != "high"
    expected_answer = upstream["answer"].split("\n\n Verify on the official GDCE tariff lookup:", 1)[0]
    assert response.response.content == expected_answer
    assert "Verify on the official GDCE tariff lookup" not in response.response.content
    assert "5208.39.00" in response.response.content
    assert "5408.10.90" in response.response.content
    assert "5408.10.10" in response.response.content
    assert response.response.limitations == []
    assert response.message.role == "assistant"
    assert [block.type for block in response.message.content] == [
        "markdown",
        "prediction",
        "table",
        "official_reference",
        "clarification",
        "suggestions",
    ]
    assert response.message.content[0].text == expected_answer
    assert response.message.content[1].title == "Preliminary HS Code"
    assert response.message.content[1].data["hsCode"] == "5208.39.00"
    assert "confidence" not in response.message.content[1].data
    assert response.message.content[2].title == "Possible HS Code Matches"
    assert [row["hs_code"] for row in response.message.content[2].rows] == [
        "5208.39.00",
        "5408.10.90",
        "5408.10.10",
    ]
    assert response.message.content[3].title == "Official GDCE tariff lookup"
    assert response.message.content[3].label == "Verify on the official GDCE tariff lookup"
    assert response.message.content[3].url == "https://customs.gov.kh/en/publications/14037-customs-tariff-of-cambodia-km-2022"
    assert response.message.content[3].agency == "GDCE"
    assert response.message.content[3].source_type == "official_tariff"
    assert response.message.content[4].title == "More information is needed"
    assert response.message.content[4].questions == [
        "What is the exact fiber composition (e.g., 100% cotton vs. blended with artificial filaments)?",
        "Is the fabric dyed, unbleached, bleached, printed, or made of yarns of different colors?",
        "What is the weight of the fabric per square meter (e.g., more or less than 200 g/m²)?",
    ]
    assert response.message.content[5].title == "Related questions"
    assert response.message.content[5].items == [
        "How do I import cotton fabric?",
        "What's the import duty on cotton fabric?",
        "Any trade data for cotton fabric?",
    ]
    assert response.clarifications == upstream["clarifications"]
    assert response.suggestions == upstream["suggestion"]
    assert len(response.citations) == 3
    assert [citation.document_id for citation in response.citations] == ["4769", "4959", "4958"]
    assert all(citation.title == "Customs reference" for citation in response.citations)
    assert [citation.score for citation in response.citations] == [0.95, 0.57070094, 0.56904304]
    assert [citation.snippet for citation in response.citations] == [
        "Woven fabrics of cotton, containing 85 % or more by weight of cotton, weighing not more than 200 g/m2. > Dyed : > Other Fabrics    5208.39.00",
        "Woven fabrics of artificial filament yarn, including woven fabrics obtained from materials of heading 54.05. > Woven fabrics obtained from high tenacity yarn of viscose rayon : > Other",
        "Woven fabrics of artificial filament yarn, including woven fabrics obtained from materials of heading 54.05. > Woven fabrics obtained from high tenacity yarn of viscose rayon : > Unbleached",
    ]
    response_json = response.model_dump(mode="json")
    assert "gemini_llm" not in str(response_json)
    assert "prefix_scan_with_semantic_fill_2" not in str(response_json)
    assert "what is the hs code for cotton fabric?" not in str(response_json)
    assert "nlu_unified_result" not in str(response_json)
    assert "import cotton fabric latest" not in str(response_json)
    assert "rewritten_after_llm" not in str(response_json)
    assert "service_latencies_s" not in str(response_json)
    assert response.errors == []
    assert response.metrics == {"latency_ms": 10976.346492767334}
    assert_frontend_message_contract(response)


def test_hs_code_lookup_clarifications_render_after_markdown_and_remain_top_level():
    answer = "The service needs more detail before confirming the HS code."
    questions = [
        "What is the exact fiber composition?",
        "Is the fabric dyed or unbleached?",
        "What is the weight in g/m²?",
    ]

    response = normalize_chat_response({
        "request_id": "fixture-hs-code-clarifications",
        "session_id": "fixture-session-retrieval",
        "question": "What is the HS code for cotton fabric?",
        "answer": answer,
        "intent": "hs_code_lookup",
        "status": "clarification_required",
        "clarifications": questions,
    })

    assert response.service == "retrieval"
    assert response.intent == "hs_code_lookup"
    assert response.status == "clarification_required"
    assert response.response.content == answer
    assert response.clarifications == questions
    assert [block.type for block in response.message.content] == ["markdown", "clarification"]
    assert response.message.content[0].text == answer
    assert response.message.content[1].title == "More information is needed"
    assert response.message.content[1].questions == questions


def test_hs_code_lookup_explicit_message_content_blocks_prevent_duplicate_clarification_block():
    answer = "The service needs more detail before confirming the HS code."
    questions = [
        "What is the exact fiber composition?",
        "Is the fabric dyed or unbleached?",
        "What is the weight in g/m²?",
    ]

    response = normalize_chat_response({
        "request_id": "fixture-hs-code-explicit-blocks",
        "session_id": "fixture-session-retrieval",
        "answer": answer,
        "intent": "hs_code_lookup",
        "status": "clarification_required",
        "clarifications": questions,
        "message": {
            "role": "assistant",
            "content": [
                {"type": "markdown", "text": answer},
                {
                    "type": "clarification",
                    "title": "More information is needed",
                    "questions": questions,
                },
            ],
        },
    })

    assert response.response.content == answer
    assert response.clarifications == questions
    assert [block.type for block in response.message.content] == ["markdown", "clarification"]
    assert len([block for block in response.message.content if block.type == "clarification"]) == 1
    assert response.message.content[1].questions == questions


def test_hs_code_lookup_preserves_exact_service_generated_answer_candidates_and_reasoning():
    answer = """Candidate HS codes for cotton fabric:

1. 5208.11.00 - Woven fabrics of cotton, unbleached, plain weave.
Reasoning: Candidate returned first by the retrieval service. [Document 1]

2. 5209.11.00 - Woven fabrics of cotton, bleached, plain weave.
Reasoning: Candidate returned second by the retrieval service. [Document 2]

3. 5210.11.00 - Woven fabrics of cotton mixed with man-made fibres.
Reasoning: Candidate returned third by the retrieval service. [Document 3]

Please provide fabric weight and composition to confirm classification."""

    payload = {
        "request_id": "fixture-hs-code-candidates",
        "session_id": "fixture-session-retrieval",
        "question": "What is the HS code for cotton fabric?",
        "answer": answer,
        "final_answer": "This replacement final answer must not win.",
        "message": "This replacement message must not win.",
        "response": {
            "content": "This response content must not win.",
            "summary": "This generated summary must not win.",
        },
        "intent": "hs_code_lookup",
        "status": "clarification_required",
        "clarifications": ["What is the fabric weight and cotton composition?"],
        "citations": [
            {"document_id": "doc-1", "title": "Document 1"},
            {"document_id": "doc-2", "title": "Document 2"},
            {"document_id": "doc-3", "title": "Document 3"},
        ],
    }

    response = normalize_chat_response(payload)

    assert response.service == "retrieval"
    assert response.intent == "hs_code_lookup"
    assert response.status == "clarification_required"
    assert response.response.content == answer
    assert response.message.content[0].type == "markdown"
    assert response.message.content[0].text == answer
    assert [block.type for block in response.message.content] == ["markdown", "prediction", "table", "clarification"]
    assert response.message.content[1].title == "Preliminary HS Code"
    assert response.message.content[1].data["hsCode"] == "5208.11.00"
    assert response.message.content[2].title == "Possible HS Code Matches"
    assert [row["hs_code"] for row in response.message.content[2].rows] == [
        "5208.11.00",
        "5209.11.00",
        "5210.11.00",
    ]
    assert "5208.11.00" in response.response.content
    assert "5209.11.00" in response.response.content
    assert "5210.11.00" in response.response.content
    assert response.response.content.index("5208.11.00") < response.response.content.index("5209.11.00")
    assert response.response.content.index("5209.11.00") < response.response.content.index("5210.11.00")
    assert "[Document 1]" in response.message.content[0].text
    assert "[Document 2]" in response.message.content[0].text
    assert "[Document 3]" in response.message.content[0].text
    assert response.response.summary == "This generated summary must not win."
    assert [citation.document_id for citation in response.citations] == ["doc-1", "doc-2", "doc-3"]


def test_hs_code_lookup_does_not_parse_prose_codes_into_structured_blocks():
    answer = """The text below intentionally contains HS-like codes that are not a structured result.

Example only: 5208.11.00 may appear in training examples.
Excluded classification: 5209.11.00 is not applicable for this product.
Comparison reference: 5210.11.00 is shown only for contrast.
Low-ranking candidate: 5211.20.00 may be mentioned but should not become a table row."""

    response = normalize_chat_response({
        "request_id": "fixture-hs-prose-only",
        "session_id": "fixture-session-retrieval",
        "question": "What is the HS code?",
        "answer": answer,
        "intent": "hs_code_lookup",
        "table": None,
        "visualization": None,
        "citations": [{"document_id": "doc-1", "title": "Customs reference"}],
    })

    assert response.service == "retrieval"
    assert response.response.content == answer
    assert [block.type for block in response.message.content] == ["markdown"]
    assert response.message.content[0].text == answer
    assert not any(block.type in {"table", "chart", "prediction", "card"} for block in response.message.content)
    assert [citation.document_id for citation in response.citations] == ["doc-1"]


def test_hs_code_lookup_keeps_clarification_and_suggestions_without_parsing_prose_codes():
    answer = """The service answer mentions several HS-like strings but provides no structured result.

Example only: 5208.11.00.
Excluded classification: 5209.11.00.
Comparison reference: 5210.11.00."""
    questions = ["What is the exact fabric composition?"]
    suggestions = ["Ask about cotton fabric import documents"]

    response = normalize_chat_response({
        "request_id": "fixture-hs-prose-only-with-prompts",
        "session_id": "fixture-session-retrieval",
        "question": "What is the HS code?",
        "answer": answer,
        "intent": "hs_code_lookup",
        "clarifications": questions,
        "suggestion": suggestions,
        "table": None,
        "visualization": None,
    })

    assert response.service == "retrieval"
    assert response.response.content == answer
    assert [block.type for block in response.message.content] == ["markdown", "clarification", "suggestions"]
    assert response.message.content[0].text == answer
    assert response.message.content[1].questions == questions
    assert response.message.content[2].items == suggestions
    assert not any(block.type in {"table", "chart", "prediction", "card"} for block in response.message.content)
    assert_frontend_message_contract(response)


def test_hs_code_lookup_keeps_candidate_llm_and_citation_confidence_meanings_separate():
    response = normalize_chat_response({
        "request_id": "fixture-hs-confidence",
        "session_id": "fixture-session-retrieval",
        "question": "What is the HS code for cotton fabric?",
        "answer": "Candidate 1: 5208.11.00. Candidate 2: 5209.11.00.",
        "intent": "hs_code_lookup",
        "candidate_confidence": "low",
        "llm_confidence": 0.99,
        "confidence": "high",
        "citations": [
            {
                "document_id": "doc-1",
                "title": "Cotton Fabric Reference",
                "score": 0.95,
            }
        ],
    })

    assert response.service == "retrieval"
    assert response.intent == "hs_code_lookup"
    assert response.confidence is None
    assert response.response.confidence is None
    assert response.citations[0].score == 0.95
    assert response.response.content == "Candidate 1: 5208.11.00. Candidate 2: 5209.11.00."
    assert response.message.content[0].text == response.response.content


def test_llm_confidence_and_citation_score_do_not_create_classification_confidence():
    response = normalize_chat_response({
        "request_id": "fixture-hs-llm-only",
        "session_id": "fixture-session-retrieval",
        "answer": "Candidate 1: 5208.11.00.",
        "intent": "hs_code_lookup",
        "llm_confidence": 0.99,
        "citations": [
            {
                "document_id": "doc-1",
                "title": "Cotton Fabric Reference",
                "score": 0.95,
            }
        ],
    })

    assert response.service == "retrieval"
    assert response.confidence is None
    assert response.response.confidence is None
    assert response.citations[0].score == 0.95


def test_retrieval_plain_answer_priority_uses_final_answer_then_string_message():
    final_answer_response = normalize_chat_response({
        "intent": "hs_code_lookup",
        "answer": {"unexpected": "object"},
        "final_answer": "Final answer from retrieval service.",
        "message": "Message fallback should not win.",
    })
    message_response = normalize_chat_response({
        "intent": "hs_code_lookup",
        "answer": {"unexpected": "object"},
        "message": "String message from retrieval service.",
    })

    assert final_answer_response.response.content == "Final answer from retrieval service."
    assert final_answer_response.message.content[0].text == "Final answer from retrieval service."
    assert message_response.response.content == "String message from retrieval service."
    assert message_response.message.content[0].text == "String message from retrieval service."


def test_hs_code_lookup_suggestions_aliases_render_related_questions_and_remain_top_level():
    aliases = ("suggestions", "suggestion", "followups", "follow_ups")
    suggestion_items = [
        "What documents are needed for cotton fabric imports?",
        "How do I calculate import duties?",
    ]

    for alias in aliases:
        response = normalize_chat_response({
            "request_id": f"fixture-hs-suggestions-{alias}",
            "session_id": "fixture-session-retrieval",
            "answer": "Candidate 1: 5208.11.00.",
            "intent": "hs_code_lookup",
            alias: suggestion_items,
        })

        assert response.service == "retrieval"
        assert response.suggestions == suggestion_items
        assert [block.type for block in response.message.content] == ["markdown", "suggestions"]
        assert response.message.content[1].title == "Related questions"
        assert response.message.content[1].items == suggestion_items


def test_hs_code_lookup_explicit_message_content_blocks_prevent_duplicate_suggestions_block():
    suggestion_items = [
        "What documents are needed for cotton fabric imports?",
        "How do I calculate import duties?",
    ]
    response = normalize_chat_response({
        "request_id": "fixture-hs-explicit-suggestions",
        "session_id": "fixture-session-retrieval",
        "answer": "Candidate 1: 5208.11.00.",
        "intent": "hs_code_lookup",
        "suggestions": suggestion_items,
        "message": {
            "role": "assistant",
            "content": [
                {"type": "markdown", "text": "Candidate 1: 5208.11.00."},
                {
                    "type": "suggestions",
                    "title": "Related questions",
                    "items": suggestion_items,
                },
            ],
        },
    })

    assert response.service == "retrieval"
    assert response.suggestions == suggestion_items
    assert [block.type for block in response.message.content] == ["markdown", "suggestions"]
    assert len([block for block in response.message.content if block.type == "suggestions"]) == 1
    assert response.message.content[1].items == suggestion_items


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
    assert response.errors[0].code == "GENERAL_SERVICE_UNAVAILABLE"
    assert response.message.content[0].message == "The general service is temporarily unavailable."
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
    assert [block.type for block in response.message.content] == ["markdown", "table"]
    assert response.message.content[1].title == "Possible HS Codes"
    assert response.message.content[1].rows[0]["hs_code"] == "0102.29.11"
    assert_frontend_message_contract(response)


# Malformed retrieval fixtures should still identify retrieval and produce a valid envelope.
def test_retrieval_malformed_contract_stays_frontend_safe():
    response = normalize_chat_response(load_fixture("retrieval_malformed.json"))

    assert response.service == "retrieval"
    assert response.status == "completed"
    assert response.response.content == ""
    assert response.message.content == []
    assert_frontend_message_contract(response)


def test_retrieval_null_table_and_visualization_generate_only_markdown_clarification_suggestions():
    answer = "The service needs more detail before confirming the HS code."
    questions = [
        "What is the exact fiber composition?",
        "Is the fabric dyed or unbleached?",
    ]
    suggestions = [
        "Ask about cotton fabric import documents",
        "Calculate import tax after confirming the HS code",
    ]
    response = normalize_chat_response({
        "request_id": "fixture-retrieval-null-structures",
        "session_id": "fixture-session-retrieval",
        "intent": "hs_code_lookup",
        "status": "clarification_required",
        "answer": answer,
        "table": None,
        "visualization": None,
        "clarifications": questions,
        "suggestions": suggestions,
        "citations": [{"document_id": "4769", "title": "Customs reference"}],
    })

    assert response.service == "retrieval"
    assert response.response.content == answer
    assert [block.type for block in response.message.content] == ["markdown", "clarification", "suggestions"]
    assert response.message.content[0].text == answer
    assert response.message.content[1].questions == questions
    assert response.message.content[2].title == "Related questions"
    assert response.message.content[2].items == suggestions
    assert [citation.document_id for citation in response.citations] == ["4769"]
    assert "references" not in [block.type for block in response.message.content]
    assert_frontend_message_contract(response)


def test_retrieval_block_generation_order_uses_only_structured_table_and_quantitative_chart_data():
    response = normalize_chat_response({
        "request_id": "fixture-retrieval-block-order",
        "session_id": "fixture-session-retrieval",
        "intent": "hs_code_lookup",
        "status": "partial",
        "answer": "Candidate HS codes are returned exactly as service text.",
        "table": {
            "title": "Candidate HS Codes",
            "rows": [{"hs_code": "5208.11.00", "description": "Cotton fabric"}],
        },
        "visualization": {
            "title": "Candidate Counts",
            "labels": ["Cotton"],
            "datasets": [{"label": "Candidates", "data": [1]}],
        },
        "clarifications": ["What is the fabric weight?"],
        "follow_ups": ["Ask about required import documents"],
        "limitations": ["Some classification details are still missing."],
    })

    assert response.service == "retrieval"
    assert [block.type for block in response.message.content] == [
        "markdown",
        "table",
        "chart",
        "clarification",
        "suggestions",
        "coverage",
    ]
    assert response.message.content[1].title == "Candidate HS Codes"
    assert response.message.content[2].title == "Candidate Counts"
    assert response.message.content[3].questions == ["What is the fabric weight?"]
    assert response.message.content[4].items == ["Ask about required import documents"]
    assert response.message.content[5].items == ["Some classification details are still missing."]
    assert_frontend_message_contract(response)


def test_retrieval_structured_hs_code_result_maps_prediction_and_candidate_table_without_reordering():
    answer = "The HS classification is preliminary and needs confirmation."
    response = normalize_chat_response({
        "request_id": "fixture-structured-hs-result",
        "session_id": "fixture-session-retrieval",
        "question": "What is the HS code for dyed cotton fabric?",
        "answer": answer,
        "result": {
            "kind": "hs_code_lookup",
            "primary_candidate": {
                "hs_code": "5208.39.00",
                "description": "Other dyed woven cotton fabrics",
                "confidence": "low",
                "citation_ids": ["4769"],
            },
            "candidates": [
                {
                    "rank": 1,
                    "hs_code": "5208.39.00",
                    "description": "Other dyed woven cotton fabrics",
                    "retrieval_score": 0.95,
                    "citation_ids": ["4769"],
                },
                {
                    "rank": 2,
                    "hs_code": "5208.32.00",
                    "description": "Plain weave dyed woven cotton fabrics",
                    "retrieval_score": 0.87,
                    "citation_ids": ["4770"],
                },
            ],
            "is_preliminary": True,
            "missing_attributes": [
                "fiber_composition",
                "finish",
                "weight_gsm",
            ],
        },
        "citations": [{"document_id": "4769", "title": "Customs reference"}],
    })

    assert response.service == "retrieval"
    assert response.intent == "hs_code_lookup"
    assert response.response.content == answer
    assert [block.type for block in response.message.content] == ["markdown", "prediction", "table"]
    prediction = response.message.content[1]
    assert prediction.title == "Preliminary HS Code"
    assert prediction.data == {
        "hsCode": "5208.39.00",
        "description": "Other dyed woven cotton fabrics",
        "preliminary": True,
    }
    table = response.message.content[2]
    assert table.title == "Possible HS Code Matches"
    assert [(column.key, column.label) for column in table.columns] == [
        ("rank", "Rank"),
        ("hs_code", "HS Code"),
        ("description", "Description"),
        ("retrieval_score", "Match Score"),
    ]
    assert table.rows == [
        {
            "rank": 1,
            "hs_code": "5208.39.00",
            "description": "Other dyed woven cotton fabrics",
            "retrieval_score": 0.95,
        },
        {
            "rank": 2,
            "hs_code": "5208.32.00",
            "description": "Plain weave dyed woven cotton fabrics",
            "retrieval_score": 0.87,
        },
    ]
    assert [citation.document_id for citation in response.citations] == ["4769"]
    assert_frontend_message_contract(response)


def test_retrieval_explicit_markdown_hs_candidates_are_enhanced_with_prediction_and_table():
    answer = (
        "Dyed cotton fabric used for shirts typically falls under woven cotton fabrics weighing not more than "
        "200 g/m², with 5208.32.00 being the most standard classification for typical shirting fabric.\n"
        "1. 5208.32.00 - Woven dyed cotton fabric containing 85% or more cotton, plain weave, weighing between "
        "100 g/m² and 200 g/m²\n"
        "2. 5212.13.00 - Other dyed woven cotton fabrics weighing not more than 200 g/m²\n"
        "3. 5212.23.00 - Other dyed woven cotton fabrics weighing more than 200 g/m²\n\n"
        "This is a best-guess classification based on standard shirt fabrics, but exact coding depends on cotton "
        "percentage, weave type, and fabric weight."
    )
    response = normalize_chat_response({
        "request_id": "fixture-explicit-hs-markdown",
        "session_id": "fixture-session-retrieval",
        "status": "clarification_required",
        "service": "retrieval",
        "intent": "hs_code_lookup",
        "query": "Find the HS code for dyed cotton fabric used for shirts. Show possible matches with confidence.",
        "confidence": "low",
        "response": {
            "type": "markdown",
            "coverage": "unknown",
            "confidence": "low",
            "content": answer,
            "limitations": [],
        },
        "message": {
            "role": "assistant",
            "content": [
                {"type": "markdown", "text": answer},
                {
                    "type": "clarification",
                    "title": "More information is needed",
                    "questions": [
                        "What is the exact cotton content percentage (e.g., 85% or more by weight)?",
                        "What is the weight of the fabric in grams per square meter (g/m²)?",
                        "What type of weave is used (e.g., plain weave vs. other weaves)?",
                    ],
                },
                {
                    "type": "suggestions",
                    "title": "Related questions",
                    "items": [
                        "How do I import dyed cotton fabric?",
                        "What's the import duty on dyed cotton fabric?",
                        "Any trade data for dyed cotton fabric?",
                    ],
                },
            ],
        },
    })

    assert response.service == "retrieval"
    assert response.intent == "hs_code_lookup"
    assert response.status == "clarification_required"
    assert response.response.content == answer
    assert [block.type for block in response.message.content] == [
        "markdown",
        "prediction",
        "table",
        "clarification",
        "suggestions",
    ]
    prediction = response.message.content[1]
    assert prediction.title == "Preliminary HS Code"
    assert prediction.data == {
        "hsCode": "5208.32.00",
        "description": "Woven dyed cotton fabric containing 85% or more cotton, plain weave, weighing between 100 g/m² and 200 g/m²",
        "preliminary": True,
    }
    table = response.message.content[2]
    assert table.title == "Possible HS Code Matches"
    assert [(column.key, column.label) for column in table.columns] == [
        ("rank", "Rank"),
        ("hs_code", "HS Code"),
        ("description", "Description"),
    ]
    assert table.rows == [
        {
            "rank": 1,
            "hs_code": "5208.32.00",
            "description": "Woven dyed cotton fabric containing 85% or more cotton, plain weave, weighing between 100 g/m² and 200 g/m²",
        },
        {
            "rank": 2,
            "hs_code": "5212.13.00",
            "description": "Other dyed woven cotton fabrics weighing not more than 200 g/m²",
        },
        {
            "rank": 3,
            "hs_code": "5212.23.00",
            "description": "Other dyed woven cotton fabrics weighing more than 200 g/m²",
        },
    ]
    assert response.message.content[3].questions == [
        "What is the exact cotton content percentage (e.g., 85% or more by weight)?",
        "What is the weight of the fabric in grams per square meter (g/m²)?",
        "What type of weave is used (e.g., plain weave vs. other weaves)?",
    ]
    assert response.message.content[4].items == [
        "How do I import dyed cotton fabric?",
        "What's the import duty on dyed cotton fabric?",
        "Any trade data for dyed cotton fabric?",
    ]
    assert_frontend_message_contract(response)


def test_retrieval_does_not_generate_hs_blocks_when_structured_candidate_data_is_absent():
    response = normalize_chat_response({
        "request_id": "fixture-structured-hs-result-without-candidates",
        "session_id": "fixture-session-retrieval",
        "answer": "The service returned prose only for this lookup.",
        "result": {
            "kind": "hs_code_lookup",
            "is_preliminary": True,
            "missing_attributes": ["fiber_composition"],
        },
    })

    assert response.service == "retrieval"
    assert response.intent == "hs_code_lookup"
    assert [block.type for block in response.message.content] == ["markdown"]
    assert not any(block.type in {"prediction", "table", "card"} for block in response.message.content)
    assert_frontend_message_contract(response)


def test_retrieval_does_not_create_chart_from_non_quantitative_visualization():
    response = normalize_chat_response({
        "request_id": "fixture-retrieval-non-quant-chart",
        "session_id": "fixture-session-retrieval",
        "intent": "hs_code_lookup",
        "answer": "Candidate HS codes are returned exactly as service text.",
        "visualization": {"title": "Narrative only", "description": "No quantitative chart data."},
    })

    assert response.service == "retrieval"
    assert [block.type for block in response.message.content] == ["markdown"]
    assert_frontend_message_contract(response)


def test_retrieval_chart_request_without_quantitative_data_returns_chart_unavailable_coverage():
    answer = "The service returned a preliminary text classification result."
    response = normalize_chat_response(
        {
            "request_id": "fixture-retrieval-chart-request-no-data",
            "session_id": "fixture-session-retrieval",
            "intent": "hs_code_lookup",
            "answer": answer,
            "visualization": None,
        },
        request_presentation={"preferred_blocks": ["chart"], "fallback": "markdown"},
    )

    assert response.service == "retrieval"
    assert response.response.content == answer
    assert [block.type for block in response.message.content] == ["markdown", "coverage"]
    assert response.message.content[1].title == "Chart data unavailable"
    assert response.message.content[1].tone == "warning"
    assert response.message.content[1].items == [
        "The service returned a text classification result but no quantitative dataset for a chart."
    ]
    assert_frontend_message_contract(response)


def test_retrieval_chart_request_with_quantitative_data_renders_chart_without_unavailable_warning():
    response = normalize_chat_response(
        {
            "request_id": "fixture-retrieval-chart-request-with-data",
            "session_id": "fixture-session-retrieval",
            "intent": "hs_code_lookup",
            "answer": "The service returned candidate score data.",
            "visualization": {
                "title": "Candidate Score Comparison",
                "labels": ["5208.39.00", "5208.32.00"],
                "datasets": [{"label": "Match Score", "data": [0.95, 0.87]}],
            },
        },
        request_presentation={"preferred_blocks": ["chart"], "fallback": "markdown"},
    )

    assert response.service == "retrieval"
    assert [block.type for block in response.message.content] == ["markdown", "chart"]
    assert response.message.content[1].title == "Candidate Score Comparison"
    assert "Chart data unavailable" not in [getattr(block, "title", None) for block in response.message.content]
    assert_frontend_message_contract(response)


def test_retrieval_failed_response_uses_safe_public_error_without_raw_internal_details(caplog):
    raw_error = (
        "Traceback: exception at http://retrieval.internal/query "
        "with provider gemini and database vector_db"
    )
    response = normalize_chat_response({
        "request_id": "fixture-retrieval-failed",
        "session_id": "fixture-session-retrieval",
        "intent": "hs_code_lookup",
        "status": "failed",
        "error": {"message": raw_error},
    })
    response_json = response.model_dump(mode="json")

    assert response.service == "retrieval"
    assert response.status == "failed"
    assert response.errors[0].code == "INTERNAL_API_ERROR"
    assert response.errors[0].message == "The request could not be completed."
    assert [block.type for block in response.message.content] == ["error"]
    assert response.message.content[0].message == "The request could not be completed."
    assert raw_error not in str(response_json)
    assert "http://retrieval.internal" not in str(response_json)
    assert "Traceback" not in str(response_json)
    assert "fixture-retrieval-failed" in caplog.text


def test_retrieval_missing_input_error_uses_safe_public_code_and_logs_raw_error(caplog):
    raw_error = "Missing input: fabric composition and weight_gsm are required fields."
    response = normalize_chat_response({
        "request_id": "fixture-retrieval-missing-input",
        "session_id": "fixture-session-retrieval",
        "intent": "hs_code_lookup",
        "status": "failed",
        "error": {"message": raw_error},
    })
    response_json = response.model_dump(mode="json")

    assert response.service == "retrieval"
    assert response.status == "failed"
    assert response.errors[0].code == "RETRIEVAL_MISSING_INPUT"
    assert response.errors[0].message == "More information is required to complete the retrieval request."
    assert response.errors[0].retryable is False
    assert [block.type for block in response.message.content] == ["error"]
    assert response.message.content[0].message == "More information is required to complete the retrieval request."
    assert raw_error not in str(response_json)
    assert "fabric composition" not in str(response_json)
    assert "fixture-retrieval-missing-input" in caplog.text
    assert raw_error in caplog.text


def test_retrieval_explicit_public_error_code_is_preserved_without_raw_message_exposure():
    raw_error = "internal retrieval http://retrieval.internal validation stack trace"
    response = normalize_chat_response({
        "request_id": "fixture-retrieval-explicit-unavailable",
        "session_id": "fixture-session-retrieval",
        "intent": "hs_code_lookup",
        "status": "failed",
        "error": {
            "code": "RETRIEVAL_SERVICE_UNAVAILABLE",
            "message": raw_error,
        },
    })
    response_json = response.model_dump(mode="json")

    assert response.errors[0].code == "RETRIEVAL_SERVICE_UNAVAILABLE"
    assert response.errors[0].message == "The retrieval service is temporarily unavailable."
    assert response.errors[0].retryable is True
    assert response.message.content[0].message == "The retrieval service is temporarily unavailable."
    assert raw_error not in str(response_json)
    assert "retrieval.internal" not in str(response_json)


def test_retrieval_malformed_optional_fields_do_not_crash_or_expose_internal_metadata():
    response = normalize_chat_response({
        "request_id": "fixture-retrieval-malformed-optionals",
        "session_id": "fixture-session-retrieval",
        "intent": "hs_code_lookup",
        "status": "clarification_required",
        "clarifications": "What is the fabric composition?",
        "suggestion": "Ask about import documents",
        "citations": [
            None,
            "",
            {"metadata": "not-a-dict"},
            {"document_id": "4769", "title": "Customs reference"},
            {"document_id": {"bad": "value"}, "snippet": "# Snippet Title\n\nUseful source text."},
        ],
        "table": {"rows": "not-a-list"},
        "visualization": {"title": "Invalid chart", "datasets": "not-a-list"},
        "message": {
            "role": "assistant",
            "content": [{"type": "future_retrieval_block", "value": "new upstream shape"}],
        },
        "metadata": {
            "rewritten_query": "internal expanded query",
            "retrieval_strategy": "hybrid_debug",
            "provider": "internal-provider",
            "internal_url": "http://retrieval.internal/query",
            "stack_trace": "Traceback...",
        },
    })
    response_json = response.model_dump(mode="json")

    assert response.service == "retrieval"
    assert response.status == "clarification_required"
    assert response.response.content == ""
    assert [block.type for block in response.message.content] == ["clarification", "suggestions"]
    assert response.message.content[0].questions == ["What is the fabric composition?"]
    assert response.message.content[1].items == ["Ask about import documents"]
    assert not any(block.type in {"table", "chart", "prediction", "card"} for block in response.message.content)
    assert [citation.title for citation in response.citations] == [
        "Customs reference",
        "Customs reference",
        "Snippet Title",
    ]
    assert response.citations[0].document_id is None
    assert response.citations[1].document_id == "4769"
    assert "future_retrieval_block" not in str(response_json)
    assert "rewritten_query" not in str(response_json)
    assert "retrieval_strategy" not in str(response_json)
    assert "internal-provider" not in str(response_json)
    assert "retrieval.internal" not in str(response_json)
    assert "Traceback" not in str(response_json)
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
