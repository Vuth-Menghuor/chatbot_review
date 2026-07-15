from types import SimpleNamespace
from uuid import uuid4

from app.services.chat_response_normalizer import normalize_chat_response


def block_by_type(response, block_type: str):
    return next(block for block in response.message.content if block.type == block_type)


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
    assert block_by_type(response, "markdown").text.startswith("Importers must submit")
    assert response.citations[0].id == "doc-1"
    assert response.citations[0].label == "Source 1"
    assert response.citations[0].score == 0.92


def test_normalizes_hs_lookup_documents_and_clarifications():
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
        chat=SimpleNamespace(id=uuid4()),
        include_debug=True,
    )

    table = block_by_type(response, "table")
    clarification = block_by_type(response, "clarification")

    assert response.session_id
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
            "visualization": {"title": "Export Partners", "type": "bar", "x": "country", "y": "value"},
            "summary_metrics": {"total_value": 1000, "row_count": 1},
        }
    )

    table = block_by_type(response, "table")
    chart = block_by_type(response, "chart")
    summary = [block for block in response.message.content if block.type == "table" and block.title == "Summary Metrics"][0]

    assert table.rows == [{"country": "United States", "value": 1000}]
    assert chart.title == "Export Partners"
    assert summary.rows == [{"metric": "Total Value", "value": 1000}, {"metric": "Row Count", "value": 1}]


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
