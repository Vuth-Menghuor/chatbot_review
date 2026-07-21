from types import SimpleNamespace
from uuid import uuid4

from app.services.chat_response_normalizer import normalize_chat_response


def block_by_type(response, block_type: str):
    return next(block for block in response.message.content if block.type == block_type)


def assert_response_content_is_first_markdown(response):
    assert response.message.content[0].type == "markdown"
    assert response.message.content[0].text == response.response.content


def test_normalizes_general_answer_with_citations():
    response = normalize_chat_response(
        {
            "request_id": "req-general",
            "session_id": "session-general",
            "status": "success",
            "intent": "general",
            "answer": "Importers must submit the required customs declaration documents.",
            "citations": [
                {
                    "doc_id": "doc-1",
                    "title": "Import procedure",
                    "snippet": "Customs declaration documents are required.",
                    "score": 0.92,
                }
            ],
        }
    )

    assert response.request_id == "req-general"
    assert response.status == "completed"
    assert response.response.type == "markdown"
    assert response.response.content == "Importers must submit the required customs declaration documents."
    assert_response_content_is_first_markdown(response)
    assert response.coverage == "unknown"
    assert block_by_type(response, "markdown").text.startswith("Importers must submit")
    assert response.citations[0].id == "doc-1"
    assert response.citations[0].label == "Source 1"
    assert response.citations[0].score == 0.92


def test_normalizes_hs_lookup_documents_and_clarifications():
    chat_id = uuid4()
    response = normalize_chat_response(
        {
            "request_id": "req-hs",
            "status": "success",
            "intent": "hs_code_lookup",
            "final_answer": "Cotton fabric needs more detail before selecting one HS code.",
            "documents": [
                {
                    "id": "4757",
                    "content": "Woven cotton fabric, unbleached, plain weave",
                    "score": 1,
                    "metadata": {"hs_code": "5208.11.00"},
                },
                {
                    "id": "5362",
                    "content": "Knitted or crocheted cotton fabric, dyed",
                    "score": 0.72,
                    "metadata": {"hs_code": "6006.22.00"},
                },
            ],
            "clarifying_questions": [
                "Is the fabric woven or knitted?",
                "Is it bleached, unbleached, or dyed?",
            ],
            "metadata": {"candidate_confidence": "low"},
        },
        chat=SimpleNamespace(id=chat_id),
        include_debug=True,
    )

    table = block_by_type(response, "table")
    clarification = block_by_type(response, "clarification")

    assert response.session_id
    assert response.chat_id == str(chat_id)
    assert response.session_id == str(chat_id)
    assert response.intent == "hs_code_lookup"
    assert table.title == "Possible HS Codes"
    assert table.rows[0]["hs_code"] == "5208.11.00"
    assert clarification.questions == [
        "Is the fabric woven or knitted?",
        "Is it bleached, unbleached, or dyed?",
    ]
    assert response.debug is not None
    assert response.debug.confidence == "low"


def test_normalizes_calculator_breakdown_and_line_items():
    response = normalize_chat_response(
        {
            "request_id": "req-calc",
            "session_id": "session-calc",
            "status": "ok",
            "intent": "calculation",
            "human_readable": "Total import tax is 714,600 KHR.",
            "breakdown": {
                "cif_value": 4037000,
                "cop_amount": 282600,
                "vop_amount": 432000,
            },
            "line_items": [
                {"name": "Import Taxes (COP)", "rate": 7, "base": 4037000, "amount": 282600, "currency": "KHR"},
                {"name": "VOP", "rate": 10, "base": 4319600, "amount": 432000, "currency": "KHR"},
            ],
            "references": [{"doc_id": "gdce_calculator.duty_rates:5208.11.00", "title": "Duty Rates"}],
        }
    )

    tables = [block for block in response.message.content if block.type == "table"]

    assert response.status == "completed"
    assert block_by_type(response, "markdown").text == "Total import tax is 714,600 KHR."
    assert tables[0].title == "Calculation Breakdown"
    assert tables[0].rows[1]["component"] == "cop_amount"
    assert tables[1].title == "Tax Line Items"
    assert tables[1].rows[0]["amount"] == 282600
    assert response.citations[0].title == "Duty Rates"


def test_normalizes_trade_table_visualization_and_summary_metrics():
    response = normalize_chat_response(
        {
            "request_id": "req-trade",
            "session_id": "session-trade",
            "status": "completed",
            "intent": "trade_data",
            "message": "Top Cambodia export partners by value.",
            "table": {
                "columns": [{"key": "country", "label": "Country"}, {"key": "value", "label": "Value"}],
                "rows": [{"country": "United States", "value": 1000}],
            },
            "visualization": {
                "title": "Export Partners",
                "type": "line",
                "labels": ["2024"],
                "datasets": [{"label": "Trade Value (USD)", "data": [1000]}],
            },
            "summary_metrics": {
                "total_value": 1000,
                "row_count": 1,
                "data_quality": {"truncation_note": "Showing one result."},
            },
            "suggestions": ["Show monthly trend"],
        }
    )

    table = block_by_type(response, "table")
    chart = block_by_type(response, "chart")
    summary = [block for block in response.message.content if block.type == "table" and block.title == "Summary Metrics"][0]
    suggestions = block_by_type(response, "suggestions")

    assert table.rows == [{"country": "United States", "value": 1000}]
    assert response.response.type == "table"
    assert chart.title == "Export Partners"
    assert chart.data["chartType"] == "bar"
    assert chart.data["xKey"] == "label"
    assert chart.data["data"] == [{"label": "2024", "trade_value_usd": 1000}]
    assert chart.data["series"][0]["key"] == "trade_value_usd"
    assert summary.rows == [
        {"metric": "Total Value", "value": 1000},
        {"metric": "Row Count", "value": 1},
        {"metric": "Data Quality", "value": "Showing one result."},
    ]
    assert suggestions.items == ["Show monthly trend"]
    assert response.suggestions == ["Show monthly trend"]


def test_normalizes_current_orchestrator_payload_without_inventing_fields():
    response = normalize_chat_response(
        {
            "request_id": "ae3059bf-a8a2-4201-a49d-e2cb3aa022fe",
            "session_id": "bruno-local-session",
            "status": "completed",
            "intent": "general",
            "query": "What documents do I need to import goods into Cambodia?",
            "answer": "To import goods into Cambodia, the following information is available from the provided documents.",
            "citations": [
                {
                    "doc_id": "789",
                    "snippet": "### Appendix A. The Law and Regulation relating to Customs Clearance...",
                    "score": 1,
                },
                {
                    "doc_id": "1184",
                    "snippet": "| Field No | Field Label | Action | Description and / or Usage |...",
                    "score": 1,
                },
            ],
            "suggestions": [
                "How do I classify import goods?",
                "How is customs import duty calculated?",
                "What are the general import procedures?",
            ],
            "latency_ms": 3345.81,
            "metadata": {
                "answer_source": "gemini_llm_cached",
                "semantic_count": 5,
                "structured_count": 0,
                "total_count": 2,
                "query_strategy": "rewritten_after_llm",
            },
        },
        include_debug=True,
    )

    assert response.response.type == "markdown"
    assert response.response.content == (
        "To import goods into Cambodia, the following information is available from the provided documents."
    )
    assert response.response.coverage == "unknown"
    assert response.response.limitations == []
    assert_response_content_is_first_markdown(response)
    assert response.citations[0].id == "789"
    assert response.citations[0].citation_id == "789"
    assert response.citations[0].label == "Source 1"
    assert response.citations[0].title == "Laws and Regulations Relating to Customs Clearance"
    assert response.citations[1].title == "SAD Import Declaration Requirements"
    assert block_by_type(response, "suggestions").title == "Suggested follow-ups"
    assert response.metrics["latency_ms"] == 3345.81
    assert response.debug is not None
    assert response.debug.answer_source == "gemini_llm_cached"
    assert response.debug.semantic_count == 5
    assert response.debug.structured_count == 0
    assert response.debug.total_count == 2
    assert response.debug.query_strategy == "rewritten_after_llm"
    assert "metadata" not in response.debug.metadata


def test_string_answer_is_exact_source_of_truth_even_when_other_answer_fields_exist():
    orchestrator_answer = "To import goods into Cambodia, you are subject to the legal framework established by the Law on Customs..."
    response = normalize_chat_response(
        {
            "request_id": "req-exact-answer",
            "session_id": "session-exact-answer",
            "status": "completed",
            "intent": "general",
            "answer": orchestrator_answer,
            "final_answer": "To import goods into Cambodia, you are required to complete a Customs declaration...",
            "message": "Older cached answer that must not be used.",
            "response": {
                "content": "Nested normalized content that must not override orchestrator answer.",
                "coverage": "partial",
            },
            "suggestions": ["Show import procedure"],
        }
    )

    assert response.response.content == orchestrator_answer
    assert_response_content_is_first_markdown(response)


def test_empty_string_answer_is_preserved_and_not_replaced_by_fallbacks():
    response = normalize_chat_response(
        {
            "request_id": "req-empty-answer",
            "session_id": "session-empty-answer",
            "status": "completed",
            "intent": "general",
            "answer": "",
            "final_answer": "Fallback answer that must not be used.",
            "message": "Fallback message that must not be used.",
        }
    )

    assert response.response.content == ""
    assert_response_content_is_first_markdown(response)


def test_normalizes_partial_answer_coverage_blocks():
    response = normalize_chat_response(
        {
            "request_id": "req-import-docs",
            "session_id": "{{session_id}}",
            "status": "partial_answer",
            "intent": "general",
            "coverage": "partial",
            "confidence": "medium",
            "query": "What documents do I need to import goods into Cambodia?",
            "answer": {
                "summary": "A complete document checklist was not found.",
                "found": [
                    "Imports require a Single Administrative Document (SAD).",
                    "Use IM declaration codes.",
                    "Governed by the Law on Customs (2007).",
                    "Circular No.3 covers tax-exempt imports.",
                ],
                "missing": [
                    "Commercial Invoice",
                    "Packing List",
                    "Certificate of Origin",
                    "Bill of Lading",
                    "Import License",
                ],
            },
            "citations": [
                {
                    "id": "1184",
                    "document_id": "DOC_005",
                    "filename": "DOC_005.md",
                    "title": "Single Administrative Document (SAD)",
                    "chunk_index": 386,
                    "snippet": "IM4 = Direct Import",
                    "retrieval_method": "keyword_fallback",
                }
            ],
            "suggestions": [
                "How do I classify import goods?",
                "How is customs import duty calculated?",
                "What are the general import procedures?",
            ],
        },
        chat=SimpleNamespace(id="bruno-local-session"),
    )

    coverage_blocks = [block for block in response.message.content if block.type == "coverage"]
    suggestions = block_by_type(response, "suggestions")

    assert response.status == "completed"
    assert response.session_id == "bruno-local-session"
    assert response.chat_id == "bruno-local-session"
    assert response.coverage == "partial"
    assert response.confidence == "medium"
    assert response.response.coverage == "partial"
    assert response.response.confidence == "medium"
    assert response.response.limitations[0].message == "Commercial Invoice"
    assert_response_content_is_first_markdown(response)
    assert block_by_type(response, "markdown").text == "A complete document checklist was not found."
    assert coverage_blocks[0].title == "What was found"
    assert coverage_blocks[0].tone == "info"
    assert coverage_blocks[0].items[0] == "Imports require a Single Administrative Document (SAD)."
    assert coverage_blocks[1].title == "Information limitation"
    assert coverage_blocks[1].tone == "warning"
    assert coverage_blocks[1].items == [
        "Commercial Invoice",
        "Packing List",
        "Certificate of Origin",
        "Bill of Lading",
        "Import License",
    ]
    assert coverage_blocks[1].note == "The available sources do not provide a complete answer for every requested detail."
    assert response.citations[0].title == "Single Administrative Document (SAD)"
    assert response.citations[0].citation_id == "1184"
    assert response.citations[0].document_id == "DOC_005"
    assert response.citations[0].filename == "DOC_005.md"
    assert response.citations[0].chunk_index == 386
    assert response.citations[0].retrieval_method == "keyword_fallback"
    assert suggestions.items[0] == "How do I classify import goods?"


def test_normalizes_failed_response_to_error_block():
    response = normalize_chat_response(
        {
            "request_id": "req-error",
            "session_id": "session-error",
            "status": "failed",
            "intent": "error",
            "error": {"code": "SERVICE_UNAVAILABLE", "message": "Retrieval service is unavailable"},
        }
    )

    error = block_by_type(response, "error")

    assert response.status == "failed"
    assert error.message == "Retrieval service is unavailable"
    assert response.debug is None
