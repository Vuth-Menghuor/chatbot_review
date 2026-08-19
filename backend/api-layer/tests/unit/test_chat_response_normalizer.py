from __future__ import annotations

import json
import logging
from pathlib import Path

from app.services.chat_response_normalizer import normalize_chat_response


# This file protects the API-to-frontend chat response contract before refactoring the large normalizer.

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "service_responses"


def load_fixture(name: str):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


# Read block types without repeating the same list comprehension in every normalizer test.
def block_types(response):
    return [block.type for block in response.message.content]


# Find a block by title so calculator tests can assert behavior without depending on local variable positions.
def block_by_title(response, title):
    return next(block for block in response.message.content if getattr(block, "title", None) == title)


# Plain orchestrator text must remain a markdown block so legacy answers still render.
def test_normalizes_plain_text_answer_to_markdown_block():
    response = normalize_chat_response(
        {
            "request_id": "req-1",
            "session_id": "sess-1",
            "intent": "general",
            "answer": "Hello from the orchestrator.",
            "confidence": "high",
        }
    )

    assert response.request_id == "req-1"
    assert response.session_id == "sess-1"
    assert response.status == "completed"
    assert response.service == "general"
    assert response.intent == "general"
    assert response.confidence == "high"
    assert response.response.content == "Hello from the orchestrator."
    assert block_types(response) == ["markdown"]
    assert response.message.content[0].text == "Hello from the orchestrator."


# Structured oxen calculator payloads must keep the existing rich UI block order and values.
def test_structured_oxen_calculation_produces_expected_ui_blocks():
    response = normalize_chat_response(
        {
            "request_id": "req-calc",
            "session_id": "sess-calc",
            "intent": "calculator",
            "answer": "Calculation complete.",
            "calculator_result": {
                "summary": {"total_tax": 572300, "currency": "KHR"},
                "product": {"hs_code": "0102.29.11", "description": "Oxen"},
                "inputs": {"cif_value": "800 USD", "origin_country": "China"},
                "tax_breakdown": [
                    {
                        "component": "Import Tax (COP)",
                        "tax_base": "3,232,800 KHR",
                        "rate": "7%",
                        "amount": 226300,
                        "currency": "KHR",
                    },
                    {
                        "component": "VAT",
                        "tax_base": "3,458,800 KHR",
                        "rate": "10%",
                        "amount": 346000,
                        "currency": "KHR",
                    }
                ],
                "references": [
                    {"id": "law-1", "title": "Customs Tariff", "url": "https://example.test/tariff"}
                ],
            },
        }
    )

    assert response.response.content == "Calculation complete."
    assert response.service == "calculator"
    assert block_types(response) == ["summary", "key_value", "key_value", "table", "references"]
    assert response.message.content[0].title == "Import Tax Calculation"
    assert response.message.content[0].data["total_tax"] == 572300
    assert response.message.content[1].items[0].value == "0102.29.11"
    assert response.message.content[3].title == "Tax Breakdown"
    assert response.message.content[3].rows[0]["component"] == "Import Tax (COP)"


# Structured petroleum payloads with phases must keep calculation details and assumptions blocks intact.
def test_structured_petroleum_two_phase_calculation_keeps_phases_and_assumptions():
    response = normalize_chat_response(
        {
            "request_id": "req-petro",
            "session_id": "sess-petro",
            "intent": "calculator",
            "answer": "Petroleum calculation complete.",
            "calculator_result": {
                "summary": {"total_tax": 2500000, "currency": "KHR", "phase_gap": "100,000 KHR"},
                "product": {"hs_code": "2710.12.21", "description": "Petroleum"},
                "inputs": {"declared_value": "500 USD/MT", "quantity": "10 MT"},
                "tax_breakdown": [
                    {"component": "Phase 1", "tax_base": "DV", "rate": "35%", "amount": 1200000, "currency": "KHR"},
                    {"component": "Phase 2", "tax_base": "State charge", "rate": "10%", "amount": 1300000, "currency": "KHR"},
                ],
                "phases": [
                    {
                        "name": "Phase 1",
                        "basis": "Declared value",
                        "total": 1200000,
                        "currency": "KHR",
                        "lines": [{"component": "CPP", "amount": 700000}],
                    },
                    {
                        "name": "Phase 2",
                        "basis": "State charge",
                        "total": 1300000,
                        "currency": "KHR",
                        "lines": [{"component": "VPP", "amount": 600000}],
                    },
                ],
                "assumptions": [
                    {"title": "Declared value", "content": "Provided by the user"},
                    "Importer pays Phase 1 amount.",
                ],
            },
        }
    )

    assert block_types(response) == ["summary", "key_value", "key_value", "table", "details", "details"]
    assert response.service == "calculator"
    assert block_by_title(response, "Calculation Details").items[0].title == "Phase 1"
    assert "basis: Declared value" in block_by_title(response, "Calculation Details").items[0].content
    assert block_by_title(response, "Assumptions & Notes").items[1].content == "Importer pays Phase 1 amount."


# Legacy calculator text must still be parsed into the same rich block sequence.
def test_legacy_calculator_text_keeps_existing_block_order_and_table_formatting():
    content = """------------
IMPORT TAX CALCULATION
------------

PRODUCT INFORMATION:
* HS Code: 0102.29.11 (Oxen)
* Origin Country: China

INPUT PARAMETERS:
* CIF Value: 800 USD
* Exchange Rate: 4,041 KHR/USD
* Customs Regime: Import

STEP 1: Currency Conversion
800 USD x 4,041 KHR = 3,232,800 KHR

FINAL TAX BREAKDOWN
| Tax Component | Tax Base | Rate | Amount KHR |
|---------------|----------|------|------------|
| Import Tax (COP) | 3,232,800 KHR | 7 | 226,300 |
| TOTAL TAX | | | 572,300 |

SUMMARY:
The estimated import tax is 572,300 KHR.

ASSUMPTIONS & NOTES:
* Exchange rate: 4,041 KHR/USD
* Import tax rate (COP): 7%

REFERENCES & CITATIONS:
* Customs Tariff (ID: tariff-1) | Effective: 2024-01-01
"""

    response = normalize_chat_response({"intent": "calculator", "answer": content})

    assert response.service == "calculator"
    assert block_types(response) == ["summary", "key_value", "key_value", "table", "details", "details"]
    assert response.message.content[0].data["total_tax"] == "572,300"
    assert response.message.content[3].rows[0]["rate"] == "7%"
    assert block_by_title(response, "Calculation Details").items[0].title == "Step 1: Currency Conversion"


# Explicit structured calculator results must win over other display hints.
def test_calculator_structured_result_has_priority_over_upstream_table():
    response = normalize_chat_response(
        {
            "intent": "calculation",
            "answer": "Use structured result.",
            "calculator_result": {
                "summary": {"total_tax": 777, "currency": "KHR"},
                "tax_breakdown": [{"component": "Service VAT", "amount": 777, "currency": "KHR"}],
            },
            "table": {
                "title": "Upstream Table",
                "rows": [{"component": "Ignored table value", "amount": 1}],
            },
        }
    )

    assert block_types(response) == ["summary", "table"]
    assert response.message.content[0].data["total_tax"] == 777
    assert block_by_title(response, "Tax Breakdown").rows[0]["component"] == "Service VAT"


# Explicit upstream table objects should render before message blocks or text parsing.
def test_calculator_upstream_table_has_priority_over_message_blocks():
    response = normalize_chat_response(
        {
            "intent": "calculation",
            "answer": "IMPORT TAX CALCULATION\nSUMMARY:\nUse text parser later.",
            "table": {
                "title": "Calculator Service Table",
                "columns": [{"key": "component", "label": "Component"}, {"key": "amount", "label": "Amount"}],
                "rows": [{"component": "Upstream table value", "amount": "123 KHR"}],
            },
            "message": {
                "role": "assistant",
                "content": [{"type": "markdown", "text": "Message block should not be used."}],
            },
        }
    )

    assert block_types(response) == ["table"]
    assert response.message.content[0].title == "Calculator Service Table"
    assert response.message.content[0].rows[0]["component"] == "Upstream table value"


# Explicit upstream message blocks should render before conservative text parsing.
def test_calculator_message_blocks_have_priority_over_legacy_text_parser():
    response = normalize_chat_response(
        {
            "intent": "calculation",
            "answer": "IMPORT TAX CALCULATION\nSUMMARY:\nParser should not win.",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "summary", "title": "Service Summary", "data": {"total_tax": "from message"}},
                    {"type": "markdown", "text": "Service-authored markdown block."},
                ],
            },
        }
    )

    assert block_types(response) == ["summary", "markdown"]
    assert response.message.content[0].title == "Service Summary"
    assert response.message.content[0].data["total_tax"] == "from message"
    assert response.message.content[1].text == "Service-authored markdown block."


# Calculator text that does not match known sections must fall back to the exact upstream answer.
def test_calculator_unparseable_text_falls_back_to_original_markdown():
    answer = "Petroleum estimate returned as plain text only.\nNo structured sections were supplied."

    response = normalize_chat_response({"intent": "calculation", "answer": answer})

    assert block_types(response) == ["markdown"]
    assert response.message.content[0].text == answer


# Empty structured calculator hints must not suppress the original upstream answer.
def test_calculator_empty_structured_hint_falls_back_to_original_answer():
    answer = "Calculator returned text after an unusable structured object."

    response = normalize_chat_response({"intent": "calculation", "answer": answer, "calculator_result": {"metadata": {}}})

    assert block_types(response) == ["markdown"]
    assert response.message.content[0].text == answer


# Legacy assumptions must preserve the upstream text instead of deriving customs assumptions or rate codes.
def test_legacy_assumptions_and_notes_preserve_upstream_values_unchanged():
    content = """IMPORT TAX CALCULATION
INPUT PARAMETERS:
* Declared Value: 500 USD per metric ton
* Exchange Rate: 4,100 KHR/USD
* Customs Regime: Petroleum two-phase

ASSUMPTIONS & NOTES:
* === APPLICABLE RATES ===
* Import tax rate: 35%
* VOP rate: 10%
* Source: official tariff table
"""

    response = normalize_chat_response({"intent": "calculator", "answer": content})
    assumptions = block_by_title(response, "Assumptions & Notes")

    assert assumptions.data == {}
    assert assumptions.items[0].content == "\n".join(
        [
            "Import tax rate: 35%",
            "VOP rate: 10%",
            "Source: official tariff table",
        ]
    )


# Structured calculator values from the service must pass through unchanged, even when totals are inconsistent.
def test_structured_calculator_values_are_not_recalculated_or_corrected():
    response = normalize_chat_response(
        {
            "request_id": "req-pass-through",
            "session_id": "sess-pass-through",
            "intent": "calculator",
            "answer": "Use the upstream calculator values.",
            "calculator_result": {
                "summary": {"total_tax": 999, "currency": "KHR", "phase_gap": "service says odd gap"},
                "tax_breakdown": [
                    {"component": "Customs Duty", "tax_base": "100 KHR", "rate": "7%", "amount": 10, "currency": "KHR"},
                    {"component": "VAT", "tax_base": "110 KHR", "rate": "10%", "amount": 20, "currency": "KHR"},
                ],
                "phases": [
                    {
                        "name": "Phase 1",
                        "basis": "service basis",
                        "total": 123,
                        "currency": "KHR",
                        "lines": [{"component": "Service line", "amount": 456}],
                    }
                ],
            },
        }
    )

    summary = response.message.content[0]
    table = block_by_title(response, "Tax Breakdown")
    details = block_by_title(response, "Calculation Details")

    assert summary.data["total_tax"] == 999
    assert summary.data["phase_gap"] == "service says odd gap"
    assert table.rows[0]["amount"] == 10
    assert table.rows[1]["amount"] == 20
    assert "total: 123" in details.items[0].content
    assert "currency: KHR" in details.items[0].content
    assert "component: Service line" in details.items[0].content
    assert "amount: 456" in details.items[0].content


# Calculator table values and labels from upstream must remain exactly as provided.
def test_structured_calculator_tax_breakdown_preserves_raw_labels_and_formatted_values():
    response = normalize_chat_response(
        {
            "intent": "calculation",
            "answer": "Use upstream formatted tax values.",
            "calculator_result": {
                "summary": {"total_tax": "446,614,600 KHR"},
                "product": {"hs_code": "2710.12.21", "unit_rate": "0.02 $/L"},
                "tax_breakdown": [
                    {
                        "tax_component": "Special Tax (SPP)",
                        "tax_base_khr": "1,488,715,093",
                        "rate": "30.00%",
                        "amount_khr": "446,614,600",
                    }
                ],
                "phases": [
                    {
                        "name": "Phase 1",
                        "rate_label": "0.02 $/L",
                        "amount_khr": "446,614,600",
                        "lines": [
                            {
                                "tax_component": "Special Tax (SPP)",
                                "amount_khr": "446,614,600",
                            }
                        ],
                    }
                ],
            },
        }
    )

    product = block_by_title(response, "Product Information")
    table = block_by_title(response, "Tax Breakdown")
    details = block_by_title(response, "Calculation Details")

    assert [column.key for column in table.columns] == ["tax_component", "tax_base_khr", "rate", "amount_khr"]
    assert [column.label for column in table.columns] == ["tax_component", "tax_base_khr", "rate", "amount_khr"]
    assert table.rows[0] == {
        "tax_component": "Special Tax (SPP)",
        "tax_base_khr": "1,488,715,093",
        "rate": "30.00%",
        "amount_khr": "446,614,600",
    }
    assert next(item for item in product.items if item.key == "unit_rate").value == "0.02 $/L"
    assert "rate_label: 0.02 $/L" in details.items[0].content
    assert "amount_khr: 446,614,600" in details.items[0].content
    assert "tax_component: Special Tax (SPP)" in details.items[0].content


# Upstream business inconsistencies should be logged for development without changing the user-facing response.
def test_calculator_business_inconsistency_logs_warning_and_preserves_upstream_values(caplog):
    payload = load_fixture("calculator_business_inconsistency.json")

    with caplog.at_level(logging.WARNING, logger="app.services.normalizers.calculator.validation"):
        response = normalize_chat_response(payload)

    table = block_by_title(response, "Tax Breakdown")

    assert response.response.content == payload["answer"]
    assert response.message.content[0].data["largest_component"] == "Special Tax (SPP)"
    assert table.rows[0]["tax_component"] == "Special Tariff (SOP)"
    assert any(
        "calculator_upstream_business_inconsistency" in record.message
        and "claimed=SPP" in record.message
        and "table=SOP" in record.message
        for record in caplog.records
    )


# Trade payloads should expose the service label through the TradeNormalizer path.
def test_trade_response_sets_service_field():
    response = normalize_chat_response({"service": "trade", "intent": "trade", "answer": "Trade route answer."})

    assert response.service == "trade"
    assert block_types(response) == ["markdown"]


def test_trade_orchestrator_query_response_is_primary_contract():
    response = normalize_chat_response(
        {
            "request_id": "trade-req-1",
            "session_id": "trade-session-1",
            "question": "What were Cambodia exports in 2024?",
            "answer": "Trade answer from orchestrator.",
            "intent": "trade_query",
            "status": "completed",
            "citations": [],
            "clarifications": [],
            "errors": [],
            "latency_ms": 0,
            "metadata": {},
            "table": None,
            "visualization": None,
            "message": "Trade answer from orchestrator.",
            "suggestion": [],
            "summary": None,
            "summary_metrics": None,
        }
    )

    assert response.request_id == "trade-req-1"
    assert response.session_id == "trade-session-1"
    assert response.service == "trade"
    assert response.intent == "trade_query"
    assert response.status == "completed"
    assert response.query == "What were Cambodia exports in 2024?"
    assert response.response.content == "Trade answer from orchestrator."
    assert block_types(response) == ["markdown"]
    assert response.message.content[0].text == "Trade answer from orchestrator."


def test_trade_response_content_wins_over_generic_top_level_answer():
    response = normalize_chat_response(
        {
            "request_id": "trade-req-generic-answer",
            "service": "trade",
            "intent": "trade_query",
            "answer": (
                "SUMMARY OF KEY FINDINGS:\n\n"
                "The provided trade data contains specific figures and statistics."
            ),
            "response": {
                "type": "table",
                "coverage": "unknown",
                "content": "Cambodia's imports by partner country in 2026 are shown below.",
                "limitations": [],
            },
            "table": {
                "columns": [
                    {"key": "period", "label": "period"},
                    {"key": "partner_country", "label": "partner_country"},
                    {"key": "display", "label": "display"},
                ],
                "rows": [
                    {"period": "2026", "partner_country": "China", "display": "$3.28 billion"},
                ],
            },
        }
    )

    assert response.response.content == "Cambodia's imports by partner country in 2026 are shown below."
    assert block_types(response) == ["markdown", "table"]
    assert response.message.content[0].text == response.response.content
    assert "SUMMARY OF KEY FINDINGS" not in response.message.content[0].text


def test_trade_top_level_table_is_primary_and_suppresses_structured_compatibility_table():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Use the orchestrator table first.",
            "table": {
                "title": "Orchestrator Trade Table",
                "rows": [{"flow": "Export", "value_usd": 1000, "period": 2024}],
            },
            "trade_result": {
                "top_export_partners": [
                    {"rank": 1, "partner_country": "Vietnam", "value_usd": 1200000, "period": 2024},
                ],
            },
        }
    )

    assert response.service == "trade"
    assert response.intent == "trade_query"
    assert block_types(response) == ["markdown", "table"]
    assert response.message.content[1].title == "Orchestrator Trade Table"
    assert response.message.content[1].rows[0]["flow"] == "Export"
    assert "Top Export Partners" not in [getattr(block, "title", None) for block in response.message.content]


def test_trade_upstream_table_prevents_duplicate_compatibility_trade_table():
    response = normalize_chat_response({
        "intent": "trade_query",
        "answer": "Trade data.",
        "table": {
            "columns": ["Partner", "Value"],
            "rows": [
                ["Vietnam", 1200000],
            ],
        },
        "trade_result": {
            "top_export_partners": [
                {
                    "rank": 1,
                    "partner_country": "Vietnam",
                    "value_usd": 1200000,
                }
            ]
        },
    })

    table_blocks = [block for block in response.message.content if block.type == "table"]

    assert len(table_blocks) == 1
    assert table_blocks[0].columns[0].key == "Partner"
    assert table_blocks[0].columns[1].key == "Value"
    assert table_blocks[0].rows == [{"Partner": "Vietnam", "Value": 1200000}]
    assert "Top Export Partners" not in [getattr(block, "title", None) for block in response.message.content]


def test_trade_does_not_parse_answer_text_into_table_rows():
    answer = (
        "1. Vietnam exported 1,200,000 USD, representing 24.5% in 2024.\n"
        "2. Thailand exported 900,000 USD, representing 18.0% in 2024.\n"
        "HS 1006 appears in the narrative only."
    )

    response = normalize_chat_response({"intent": "trade_query", "answer": answer})

    assert response.service == "trade"
    assert response.response.content == answer
    assert block_types(response) == ["markdown"]
    assert response.message.content[0].text == answer


def test_trade_structured_compatibility_payload_shapes_still_route_to_trade():
    for payload in (
        {"trade_result": {"ranking": [{"rank": 1, "commodity": "Garments"}]}},
        {"trade_data": {"ranking": [{"rank": 1, "commodity": "Garments"}]}},
        {"result": {"ranking": [{"rank": 1, "commodity": "Garments"}]}},
        {"result": {"result": {"ranking": [{"rank": 1, "commodity": "Garments"}]}}},
    ):
        response = normalize_chat_response({"answer": "Compatibility answer.", **payload})

        assert response.service == "trade"
        assert block_types(response) == ["markdown", "table"]
        assert block_by_title(response, "Trade Ranking").rows[0]["commodity"] == "Garments"


def test_trade_preserves_exact_upstream_answer_before_structured_or_message_hints():
    upstream = {
        "intent": "trade_query",
        "answer": (
            "1. Vietnam - 24.5% - 1,200,000 USD - 2024\n"
            "2. Thailand - 18.0% - 900,000 USD - 2024\n"
            "Trade balance: -300,000 USD."
        ),
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "markdown",
                    "text": "Rewritten answer that must not replace the Trade service answer.",
                }
            ],
        },
        "summary": "Shortened summary that must not replace the Trade service answer.",
        "summary_metrics": {"trade_balance_usd": 300000},
        "trade_result": {
            "ranking": [
                {"rank": 1, "partner_country": "Thailand", "value_usd": 900000, "period": 2024},
                {"rank": 2, "partner_country": "Vietnam", "value_usd": 1200000, "period": 2024},
            ],
        },
    }

    response = normalize_chat_response(upstream)

    assert response.service == "trade"
    assert response.intent == "trade_query"
    assert response.response.content == upstream["answer"]
    assert response.message.content[0].text == upstream["answer"]
    assert response.message.content[0].text.index("Vietnam") < response.message.content[0].text.index("Thailand")
    assert "-300,000 USD" in response.message.content[0].text
    assert "2024" in response.message.content[0].text


def test_trade_plain_answer_priority_uses_answer_then_final_answer_then_string_message():
    answer_response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Answer wins.",
            "final_answer": "Final answer loses.",
            "message": "String message loses.",
        }
    )
    final_answer_response = normalize_chat_response(
        {
            "intent": "trade_query",
            "final_answer": "Final answer wins.",
            "message": "String message loses.",
        }
    )
    message_response = normalize_chat_response(
        {
            "intent": "trade_query",
            "message": "String message wins.",
        }
    )

    assert answer_response.response.content == "Answer wins."
    assert answer_response.message.content[0].text == "Answer wins."
    assert final_answer_response.response.content == "Final answer wins."
    assert final_answer_response.message.content[0].text == "Final answer wins."
    assert message_response.response.content == "String message wins."
    assert message_response.message.content[0].text == "String message wins."


def test_trade_answer_allows_only_outer_trim_crlf_normalization_and_unsafe_html_sanitization():
    crlf_response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": " \r\nCambodia exports:\r\n1. Rice - 10%\r\n ",
        }
    )
    unsafe_response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": 'Exports increased. <script>alert("x")</script><a onclick="steal()" href="javascript:bad()">source</a>',
        }
    )

    assert crlf_response.response.content == "Cambodia exports:\n1. Rice - 10%"
    assert crlf_response.message.content[0].text == "Cambodia exports:\n1. Rice - 10%"
    assert unsafe_response.response.content == 'Exports increased. <a href="bad()">source</a>'
    assert unsafe_response.message.content[0].text == 'Exports increased. <a href="bad()">source</a>'


def test_trade_content_blocks_use_deterministic_deduplicated_order():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "status": "failed",
            "answer": "Trade answer.",
            "summary_metrics": {"period": 2024},
            "table": {
                "title": "Trade Values",
                "rows": [{"flow": "Export", "value_usd": 1000}],
            },
            "tables": [
                {
                    "title": "Ignored Trade Values",
                    "rows": [{"flow": "Import", "value_usd": 2000}],
                }
            ],
            "visualization": {
                "title": "Trade Values Chart",
                "labels": ["Export"],
                "datasets": [{"label": "Value USD", "data": [1000]}],
            },
            "missing": ["Monthly data is unavailable."],
            "clarifications": ["Which partner country should be used?"],
            "suggestion": ["Compare exports by country"],
            "errors": ["Partial upstream warning."],
        }
    )

    assert response.service == "trade"
    assert block_types(response) == [
        "markdown",
        "table",
        "table",
        "chart",
        "coverage",
        "clarification",
        "suggestions",
        "error",
    ]
    assert response.message.content[1].title == "Summary Metrics"
    assert response.message.content[2].title == "Trade Values"
    assert len([block for block in response.message.content if getattr(block, "title", None) == "Trade Values"]) == 1
    assert "Ignored Trade Values" not in [getattr(block, "title", None) for block in response.message.content]
    assert response.message.content[3].title == "Trade Values Chart"
    assert response.message.content[4].title == "Important limitation"
    assert response.message.content[5].questions == ["Which partner country should be used?"]
    assert response.message.content[6].items == ["Compare exports by country"]
    assert response.message.content[7].message == "The request could not be completed."


def test_trade_top_level_summary_is_displayed_without_recalculation():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data.",
            "summary": {
                "currency": "USD",
                "total_trade_value": 12345678,
                "subset_count": 1,
                "growth_rate_pct": -4.5,
            },
            "trade_result": {
                "records": [
                    {"partner_country": "Vietnam", "value_usd": 1},
                    {"partner_country": "Thailand", "value_usd": 999999999},
                ],
                "summary": {
                    "currency": "KHR",
                    "total_trade_value": 999999999,
                },
            },
        }
    )

    summary_blocks = [block for block in response.message.content if block.type == "summary"]

    assert response.service == "trade"
    assert summary_blocks[0].title == "Trade Data Summary"
    assert summary_blocks[0].data == {
        "currency": "USD",
        "total_trade_value": 12345678,
        "subset_count": 1,
        "growth_rate_pct": -4.5,
    }
    assert summary_blocks[0].data["total_trade_value"] != 1000000000


def test_trade_records_do_not_generate_business_calculations_without_upstream_metrics():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data.",
            "trade_result": {
                "records": [
                    {"period": 2023, "value_usd": 100},
                    {"period": 2024, "value_usd": 200},
                ],
            },
        }
    )

    summary_blocks = [block for block in response.message.content if block.type == "summary"]
    table_blocks = [block for block in response.message.content if block.type == "table"]

    assert response.service == "trade"
    assert block_types(response) == ["markdown", "table"]
    assert summary_blocks == []
    assert table_blocks[0].title == "Trade Ranking"
    assert table_blocks[0].rows == [
        {"period": 2023, "value_usd": 100},
        {"period": 2024, "value_usd": 200},
    ]
    assert all("growth_rate_pct" not in row for row in table_blocks[0].rows)
    assert all("total_trade_value" not in row for row in table_blocks[0].rows)
    assert all("share_percent" not in row for row in table_blocks[0].rows)
    assert all("trade_balance" not in row for row in table_blocks[0].rows)
    assert all("trade_balance_usd" not in row for row in table_blocks[0].rows)


def test_trade_explicit_upstream_business_metrics_are_displayed_without_backend_recalculation():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data.",
            "summary": {
                "total_trade_value": 999,
                "growth_rate_pct": 12.5,
                "trade_balance": -40,
            },
            "trade_result": {
                "top_export_partners": [
                    {"partner_country": "Vietnam", "value_usd": 100, "share_percent": 60},
                    {"partner_country": "Thailand", "value_usd": 200, "share_percent": 40},
                ],
            },
        }
    )

    summary_block = next(block for block in response.message.content if block.type == "summary")
    table_block = next(block for block in response.message.content if block.type == "table")

    assert summary_block.data == {
        "total_trade_value": 999,
        "growth_rate_pct": 12.5,
        "trade_balance": -40,
    }
    assert summary_block.data["total_trade_value"] != 300
    assert summary_block.data["growth_rate_pct"] != 100
    assert table_block.rows == [
        {"partner_country": "Vietnam", "value_usd": 100, "share_percent": 60},
        {"partner_country": "Thailand", "value_usd": 200, "share_percent": 40},
    ]


def test_trade_summary_data_quality_notes_render_as_coverage_not_raw_summary_data():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data.",
            "summary": {
                "currency": "USD",
                "total_trade_value": 12345678,
                "data_quality": {
                    "is_partial_period": True,
                    "partial_year_note": "The 2026 data is not complete yet.",
                    "has_more": True,
                    "truncation_note": "Showing 10 results - the total shown may not represent the full market.",
                    "period_coverage_note": "Only January through March are available.",
                    "period_mismatch_note": "",
                    "period_note": None,
                },
            },
        }
    )

    summary_block = next(block for block in response.message.content if block.type == "summary")
    coverage_block = next(block for block in response.message.content if block.type == "coverage")

    assert summary_block.data == {
        "currency": "USD",
        "total_trade_value": 12345678,
    }
    assert "data_quality" not in summary_block.data
    assert coverage_block.title == "Data availability"
    assert coverage_block.tone == "warning"
    assert coverage_block.items == [
        "Showing 10 results - the total shown may not represent the full market.",
        "The 2026 data is not complete yet.",
        "Only January through March are available.",
    ]


def test_trade_partial_data_quality_renders_only_service_supplied_coverage_notes():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "status": "partial",
            "answer": "Trade results are available.",
            "summary": {
                "data_quality": {
                    "is_partial_period": True,
                    "partial_year_note": "The 2026 data is not complete yet.",
                    "has_more": True,
                    "truncation_note": "Showing 10 results — the total shown may not represent the full market.",
                }
            },
        }
    )

    assert response.service == "trade"
    assert response.status == "partial"
    assert block_types(response) == ["markdown", "coverage"]
    assert response.message.content[0].text == "Trade results are available."
    assert response.message.content[1].title == "Data availability"
    assert response.message.content[1].tone == "warning"
    assert response.message.content[1].items == [
        "Showing 10 results — the total shown may not represent the full market.",
        "The 2026 data is not complete yet.",
    ]


def test_trade_data_quality_boolean_flags_do_not_generate_backend_warnings_without_notes():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data.",
            "summary": {
                "currency": "USD",
                "data_quality": {
                    "is_partial_period": True,
                    "has_more": True,
                },
            },
        }
    )

    assert block_types(response) == ["markdown", "summary"]
    assert response.message.content[1].data == {"currency": "USD"}


def test_trade_summary_metrics_are_compatibility_only_when_summary_exists():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data.",
            "summary": {
                "currency": "USD",
                "total_trade_value": 12345678,
                "data_quality": {
                    "truncation_note": "Showing 10 results - the total shown may not represent the full market.",
                },
            },
            "summary_metrics": {
                "currency": "KHR",
                "total_trade_value": 99999999,
                "data_quality": {
                    "truncation_note": "Showing 10 results - the total shown may not represent the full market.",
                },
            },
            "trade_result": {
                "summary": {
                    "currency": "EUR",
                    "total_trade_value": 555,
                },
            },
        }
    )

    summary_blocks = [block for block in response.message.content if block.type == "summary"]
    summary_metric_blocks = [
        block
        for block in response.message.content
        if block.type == "table" and block.title == "Summary Metrics"
    ]
    coverage_blocks = [block for block in response.message.content if block.type == "coverage"]

    assert len(summary_blocks) == 1
    assert summary_blocks[0].data == {
        "currency": "USD",
        "total_trade_value": 12345678,
    }
    assert summary_metric_blocks == []
    assert len(coverage_blocks) == 1
    assert coverage_blocks[0].items == [
        "Showing 10 results - the total shown may not represent the full market."
    ]


def test_trade_summary_metrics_remain_legacy_fallback_without_summary():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data.",
            "summary_metrics": {
                "currency": "USD",
                "total_trade_value": 12345678,
                "data_quality": {
                    "period_note": "The requested period was adjusted by the Trade service.",
                },
            },
        }
    )

    assert block_types(response) == ["markdown", "table", "coverage"]
    assert response.message.content[1].title == "Summary Metrics"
    assert response.message.content[1].rows == [
        {"metric": "Currency", "value": "USD"},
        {"metric": "Total Trade Value", "value": 12345678},
    ]
    assert response.message.content[2].title == "Data availability"
    assert response.message.content[2].items == [
        "The requested period was adjusted by the Trade service."
    ]


def test_trade_uses_valid_upstream_visualization_for_chart_block():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade chart data.",
            "visualization": {
                "type": "bar",
                "title": "Exports by Partner",
                "labels": ["Vietnam", "Thailand"],
                "datasets": [{"label": "Value USD", "data": [1200000, 900000]}],
            },
        }
    )

    assert response.service == "trade"
    assert block_types(response) == ["markdown", "chart"]
    chart = response.message.content[1]
    assert chart.title == "Exports by Partner"
    assert chart.data["chartType"] == "bar"
    assert chart.data["data"][0]["label"] == "Vietnam"
    assert chart.data["data"][0]["value_usd"] == 1200000


def test_trade_synthetic_orchestrator_payload_with_table_and_visualization_preserves_chart_values():
    upstream_visualization = {
        "type": "bar",
        "title": "Exports by Partner",
        "labels": ["Vietnam", "Thailand"],
        "datasets": [{"label": "Value USD", "data": [1200000, 900000]}],
    }
    response = normalize_chat_response(
        {
            "request_id": "fixture-trade-chart-request",
            "session_id": "fixture-trade-chart-session",
            "question": "Show Cambodia's top export partners in 2024 as a chart.",
            "answer": "Cambodia's top export partners in 2024 are shown below.",
            "intent": "trade_query",
            "status": "completed",
            "citations": [],
            "clarifications": [],
            "errors": [],
            "latency_ms": 500,
            "metadata": {"language": "en"},
            "table": {
                "title": "Top Export Partners",
                "columns": [
                    {"key": "partner_country", "label": "Partner Country"},
                    {"key": "value_usd", "label": "Value USD"},
                ],
                "rows": [
                    {"partner_country": "Vietnam", "value_usd": 1200000},
                    {"partner_country": "Thailand", "value_usd": 900000},
                ],
            },
            "visualization": upstream_visualization,
            "message": "Cambodia's top export partners in 2024 are shown below.",
            "suggestion": [],
            "summary": None,
            "summary_metrics": None,
        }
    )

    assert response.service == "trade"
    assert response.intent == "trade_query"
    assert block_types(response) == ["markdown", "table", "chart"]
    chart = response.message.content[2]
    assert chart.title == upstream_visualization["title"]
    assert chart.data["chartType"] == upstream_visualization["type"]
    assert chart.data["data"] == [
        {"label": "Vietnam", "value_usd": 1200000},
        {"label": "Thailand", "value_usd": 900000},
    ]
    assert chart.data["series"][0]["key"] == "value_usd"
    assert chart.data["series"][0]["name"] == upstream_visualization["datasets"][0]["label"]


def test_trade_single_upstream_visualization_produces_at_most_one_chart_block():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade chart data.",
            "visualization": {
                "type": "bar",
                "title": "Exports by Partner",
                "labels": ["Vietnam"],
                "datasets": [{"label": "Value USD", "data": [1200000]}],
            },
            "trade_result": {
                "top_export_partners": [
                    {
                        "rank": 1,
                        "partner_country": "Vietnam",
                        "value_usd": 1200000,
                    }
                ]
            },
        }
    )

    chart_blocks = [
        block
        for block in response.message.content
        if block.type == "chart"
    ]

    assert len(chart_blocks) <= 1


def test_trade_top_level_visualization_suppresses_compatibility_visualization_duplicate():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade chart data.",
            "visualization": {
                "type": "bar",
                "title": "Orchestrator Visualization",
                "labels": ["Vietnam"],
                "datasets": [{"label": "Value USD", "data": [1200000]}],
            },
            "trade_result": {
                "visualization": {
                    "type": "bar",
                    "title": "Compatibility Visualization",
                    "labels": ["Vietnam"],
                    "datasets": [{"label": "Value USD", "data": [1200000]}],
                },
                "chart": {
                    "type": "bar",
                    "title": "Compatibility Chart",
                    "labels": ["Vietnam"],
                    "datasets": [{"label": "Value USD", "data": [1200000]}],
                },
            },
        }
    )

    chart_blocks = [block for block in response.message.content if block.type == "chart"]

    assert len(chart_blocks) == 1
    assert chart_blocks[0].title == "Orchestrator Visualization"
    assert "Compatibility Visualization" not in [getattr(block, "title", None) for block in response.message.content]
    assert "Compatibility Chart" not in [getattr(block, "title", None) for block in response.message.content]


def test_trade_does_not_generate_chart_for_empty_or_invalid_visualization():
    null_response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "No chart data.",
            "visualization": None,
        }
    )
    empty_response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "No chart data.",
            "visualization": {
                "type": "bar",
                "labels": [],
                "datasets": [],
            },
        }
    )
    narrative_response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "No chart data.",
            "visualization": {"title": "Narrative only", "description": "No quantitative data."},
        }
    )

    assert block_types(null_response) == ["markdown"]
    assert block_types(empty_response) == ["markdown"]
    assert block_types(narrative_response) == ["markdown"]


def test_trade_malformed_or_future_payload_fields_stay_frontend_safe():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "status": "completed",
            "table": "not a table",
            "visualization": "not a chart",
            "summary": ["not", "a", "summary"],
            "suggestion": "Ask another trade question",
            "citations": [
                None,
                {"source_id": "public-source", "title": "Public Trade Source"},
            ],
            "trade_result": {
                "records": [
                    "not a record",
                    None,
                    {"period": 2024, "value_usd": None},
                ],
            },
            "future_trade_contract": {"unexpected": {"nested": ["shape"]}},
            "metadata": {
                "language": "en",
                "dal_source_url": "http://dal.internal/query",
                "query_params": {"sql": "SELECT * FROM trade_records"},
                "execution_plan": "internal plan",
            },
        }
    )

    response_json = response.model_dump(mode="json", exclude_none=True)

    assert response.service == "trade"
    assert response.intent == "trade_query"
    assert response.status == "completed"
    assert response.language == "en"
    assert response.response.content == ""
    assert response.errors == []
    assert [citation.title for citation in response.citations] == ["Public Trade Source"]
    assert block_types(response) == ["table", "suggestions"]
    assert response.message.content[0].title == "Trade Ranking"
    assert response.message.content[0].rows == [{"period": 2024, "value_usd": None}]
    assert response.message.content[1].items == ["Ask another trade question"]
    assert "not a table" not in str(response_json)
    assert "not a chart" not in str(response_json)
    assert "dal.internal" not in str(response_json)
    assert "SELECT" not in str(response_json)
    assert "execution_plan" not in str(response_json)


def test_trade_does_not_infer_chart_from_numeric_answer_text():
    answer = (
        "Vietnam: 1,200,000 USD and 24.5%.\n"
        "Thailand: 900,000 USD and 18.0%."
    )

    response = normalize_chat_response({"intent": "trade_query", "answer": answer})

    assert response.response.content == answer
    assert block_types(response) == ["markdown"]


def test_trade_chart_presentation_request_uses_markdown_and_coverage_when_visualization_missing():
    answer = (
        "Vietnam: 1,200,000 USD and 24.5%.\n"
        "Thailand: 900,000 USD and 18.0%."
    )

    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": answer,
            "visualization": None,
        },
        request_presentation={"preferred_blocks": ["chart"], "fallback": "markdown"},
    )

    assert response.response.content == answer
    assert block_types(response) == ["markdown", "coverage"]
    assert response.message.content[0].text == answer
    assert response.message.content[1].title == "Chart data unavailable"
    assert response.message.content[1].items == [
        "The service returned a text trade answer but no quantitative dataset for a chart."
    ]


def test_trade_chart_presentation_request_renders_upstream_visualization_when_available():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade chart data.",
            "visualization": {
                "type": "bar",
                "title": "Vietnam and Thailand Exports",
                "labels": ["Vietnam", "Thailand"],
                "datasets": [{"label": "Value USD", "data": [1200000, 900000]}],
            },
        },
        request_presentation={"preferred_blocks": ["chart"], "fallback": "markdown"},
    )

    assert block_types(response) == ["markdown", "chart"]
    assert response.message.content[1].title == "Vietnam and Thailand Exports"
    assert "Chart data unavailable" not in [getattr(block, "title", None) for block in response.message.content]


def test_trade_public_metrics_include_only_top_level_latency():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data.",
            "latency_ms": 1234.5,
            "metadata": {
                "language": "en",
                "dal_latency_ms": 99.9,
                "service_latencies_s": {"dal": 0.099},
            },
        }
    )

    assert response.metrics == {"latency_ms": 1234.5}


# Structured trade partner rows should render as a reusable table block after the answer markdown.
def test_trade_top_export_partners_render_table():
    response = normalize_chat_response(
        {
            "service": "trade",
            "answer": "Top Cambodia export partners in 2024.",
            "trade_result": {
                "summary": {"period": 2024, "flow": "Export"},
                "top_export_partners": [
                    {"rank": 1, "partner_country": "Vietnam", "value_usd": 1200000, "share_percent": 24.5, "period": 2024},
                    {"rank": 2, "partner_country": "Thailand", "value_usd": 900000, "share_percent": 18.0, "period": 2024},
                ],
            },
        }
    )

    assert response.service == "trade"
    assert block_types(response) == ["markdown", "summary", "table"]
    assert block_by_title(response, "Top Export Partners").rows[0]["partner_country"] == "Vietnam"
    assert block_by_title(response, "Top Export Partners").columns[2].key == "value_usd"


# Import/export value payloads should become a trade values table without frontend-specific new block types.
def test_trade_import_export_values_render_table():
    response = normalize_chat_response(
        {
            "intent": "trade",
            "answer": "Cambodia import and export values.",
            "trade_result": {
                "import_export_values": [
                    {"flow": "Import", "value_usd": 5000000, "period": 2023},
                    {"flow": "Export", "value_usd": 3500000, "period": 2023},
                ],
            },
        }
    )

    assert response.service == "trade"
    assert block_types(response) == ["markdown", "table"]
    assert block_by_title(response, "Import/Export Values").rows[1]["flow"] == "Export"


# Generic ranking records should render in a stable trade ranking table.
def test_trade_ranking_records_render_table():
    response = normalize_chat_response(
        {
            "answer": "Top trade commodities.",
            "result": {
                "ranking": [
                    {"rank": 1, "commodity": "Garments", "flow": "Export", "value_usd": 8000000, "period": 2024},
                    {"rank": 2, "commodity": "Rice", "flow": "Export", "value_usd": 2000000, "period": 2024},
                ],
            },
        }
    )

    assert response.service == "trade"
    assert block_types(response) == ["markdown", "table"]
    assert block_by_title(response, "Trade Ranking").rows[0]["commodity"] == "Garments"


# Missing trade data should render as the existing warning coverage block.
def test_trade_missing_data_renders_warning_coverage_block():
    response = normalize_chat_response(
        {
            "service": "trade",
            "answer": "Some requested trade data is missing.",
            "trade_result": {
                "missing_data": ["No monthly data is available for 2024.", "Partner country filter returned no rows."],
            },
        }
    )

    assert response.service == "trade"
    assert block_types(response) == ["markdown", "coverage"]
    assert block_by_title(response, "Missing Trade Data").tone == "warning"
    assert "No monthly data is available for 2024." in block_by_title(response, "Missing Trade Data").items


def test_trade_failed_response_uses_public_safe_error_and_logs_raw_details(caplog):
    raw_error = (
        "Traceback TradeDALException: SELECT * FROM trade_records "
        "at http://trade.internal/query using password=secret"
    )

    with caplog.at_level(logging.WARNING, logger="app.services.chat_response_normalizer"):
        response = normalize_chat_response(
            {
                "request_id": "fixture-trade-failed",
                "session_id": "fixture-session-trade",
                "intent": "trade_query",
                "status": "failed",
                "error": {"message": raw_error},
            }
        )

    response_json = response.model_dump(mode="json")

    assert response.service == "trade"
    assert response.status == "failed"
    assert response.errors[0].code == "INTERNAL_API_ERROR"
    assert response.errors[0].message == "The request could not be completed."
    assert block_types(response) == ["error"]
    assert response.message.content[0].message == "The request could not be completed."
    assert "Traceback" not in str(response_json)
    assert "SELECT" not in str(response_json)
    assert "trade.internal" not in str(response_json)
    assert "password=secret" not in str(response_json)
    assert "fixture-trade-failed" in caplog.text
    assert raw_error in caplog.text


def test_trade_public_error_classification_uses_trade_specific_messages():
    cases = [
        (
            {"error": {"code": "TRADE_SERVICE_UNAVAILABLE", "message": "raw http://trade.internal 503"}},
            "TRADE_SERVICE_UNAVAILABLE",
            "The trade data service is temporarily unavailable.",
            True,
        ),
        (
            {"error": {"message": "Trade request timed out while calling DAL"}},
            "TRADE_TIMEOUT",
            "The trade data request timed out.",
            True,
        ),
        (
            {"error": {"message": "No trade data found for criteria"}},
            "TRADE_NO_RESULTS",
            "No trade data was found for the requested criteria.",
            False,
        ),
        (
            {"error": {"message": "validation failed for period filter"}},
            "TRADE_VALIDATION_ERROR",
            "The trade data request could not be processed.",
            False,
        ),
        (
            {"error": {"message": "malformed upstream payload"}},
            "INVALID_TRADE_RESPONSE",
            "The trade data service returned an invalid response.",
            False,
        ),
    ]

    for payload, expected_code, expected_message, retryable in cases:
        response = normalize_chat_response(
            {
                "intent": "trade_query",
                "status": "failed",
                **payload,
            }
        )

        assert response.errors[0].code == expected_code
        assert response.errors[0].message == expected_message
        assert response.errors[0].retryable is retryable
        assert response.message.content[0].message == expected_message


def test_trade_public_errors_never_expose_raw_internal_text():
    cases = [
        (
            {"error": {"message": "TimeoutError: DAL request timed out at http://dal.internal/query"}},
            "TRADE_TIMEOUT",
            "The trade data request timed out.",
        ),
        (
            {"error": {"message": "ConnectionError: trade-service unavailable at http://trade.internal:8004"}},
            "TRADE_SERVICE_UNAVAILABLE",
            "The trade data service is temporarily unavailable.",
        ),
        (
            {"error": {"message": "ValidationError: invalid query_params flow=DROP TABLE"}},
            "TRADE_VALIDATION_ERROR",
            "The trade data request could not be processed.",
        ),
        (
            {"error": {"message": "No trade data found for SQL filter partner_country='Atlantis'"}},
            "TRADE_NO_RESULTS",
            "No trade data was found for the requested criteria.",
        ),
        (
            {"error": {"message": "Invalid response from provider: {'secret': 'raw'}"}},
            "INVALID_TRADE_RESPONSE",
            "The trade data service returned an invalid response.",
        ),
        (
            {"error": {"message": "Traceback TradeDALException: SELECT * FROM trade_records password=secret"}},
            "INTERNAL_API_ERROR",
            "The request could not be completed.",
        ),
    ]
    forbidden_terms = [
        "TimeoutError",
        "ConnectionError",
        "ValidationError",
        "SQL",
        "DROP TABLE",
        "Atlantis",
        "provider",
        "secret",
        "Traceback",
        "TradeDALException",
        "SELECT",
        "password=secret",
        "dal.internal",
        "trade.internal",
    ]

    for payload, expected_code, expected_message in cases:
        response = normalize_chat_response(
            {
                "intent": "trade_query",
                "status": "failed",
                **payload,
            }
        )
        response_json = response.model_dump(mode="json", exclude_none=True)
        public_text = json.dumps(
            {
                "response_content": response.response.content,
                "message_content": response_json["message"]["content"],
                "errors": response_json["errors"],
            },
            sort_keys=True,
        )

        assert response.errors[0].code == expected_code
        assert response.errors[0].message == expected_message
        assert response.response.content == ""
        assert block_types(response) == ["error"]
        assert response.message.content[0].message == expected_message
        for forbidden in forbidden_terms:
            assert forbidden not in public_text


def test_trade_no_results_with_success_status_renders_coverage_not_error():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "status": "completed",
            "answer": "No matching trade rows were returned.",
            "errors": ["No trade data found for criteria"],
        }
    )

    assert response.status == "completed"
    assert response.service == "trade"
    assert response.errors == []
    assert block_types(response) == ["markdown", "coverage"]
    assert response.message.content[1].title == "Data availability"
    assert response.message.content[1].items == [
        "No trade data was found for the requested criteria."
    ]


def test_trade_no_results_with_partial_status_stays_partial_not_failed():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "status": "partial",
            "answer": "Some criteria returned no rows.",
            "error": {"code": "TRADE_NO_RESULTS", "message": "No trade data found for one requested filter"},
        }
    )

    assert response.status == "partial"
    assert response.errors == []
    assert block_types(response) == ["markdown", "coverage"]
    assert response.message.content[1].items == [
        "No trade data was found for the requested criteria."
    ]


def test_trade_no_results_with_failed_status_remains_failure():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "status": "failed",
            "error": {"code": "TRADE_NO_RESULTS", "message": "No trade data found for criteria"},
        }
    )

    assert response.status == "failed"
    assert response.errors[0].code == "TRADE_NO_RESULTS"
    assert response.message.content[0].type == "error"
    assert response.message.content[0].message == "No trade data was found for the requested criteria."


def test_trade_preserves_standard_workflow_status_values():
    for upstream_status in (
        "completed",
        "clarification_required",
        "partial",
        "processing",
        "failed",
    ):
        payload = {
            "intent": "trade_query",
            "status": upstream_status,
            "answer": "Trade workflow status.",
        }
        if upstream_status == "failed":
            payload["error"] = {"message": "Trade service unavailable"}

        response = normalize_chat_response(payload)

        assert response.status == upstream_status


def test_trade_clarification_required_preserves_questions_without_answering_them():
    payload = {
        "intent": "trade_query",
        "status": "clarification_required",
        "answer": "Please clarify the trade query before I retrieve the data.",
        "clarifications": [
            "Which year should be used?",
            "Should the flow be import or export?",
            "Which partner country should be used?",
            "Should products be classified by HS or SITC?",
            "Which metric should be shown?",
        ],
    }

    response = normalize_chat_response(payload)

    assert response.status == "clarification_required"
    assert response.service == "trade"
    assert response.response.content == payload["answer"]
    assert block_types(response) == ["markdown", "clarification"]
    assert response.message.content[0].text == payload["answer"]
    assert response.message.content[1].questions == payload["clarifications"]
    assert response.clarifications == payload["clarifications"]


def test_trade_clarifications_render_standard_block_and_top_level_contract():
    questions = [
        "Which year should I use?",
        "Do you want imports, exports, or both?",
    ]

    response = normalize_chat_response(
        {
            "request_id": "fixture-trade-clarification",
            "session_id": "fixture-session-trade",
            "intent": "trade_query",
            "status": "clarification_required",
            "answer": "More information is needed before querying trade data.",
            "clarifications": questions,
        }
    )

    assert response.status == "clarification_required"
    assert response.service == "trade"
    assert response.intent == "trade_query"
    assert response.session_id == "fixture-session-trade"
    assert response.clarifications == questions
    assert block_types(response) == ["markdown", "clarification"]
    assert response.message.content[1].title == "More information is needed"
    assert response.message.content[1].questions == questions


def test_trade_suggestions_support_aliases_and_dedupe_top_level_and_block():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data.",
            "suggestion": [
                "Show exports by partner country",
                "Compare imports and exports",
            ],
            "suggestions": [
                "Show exports by partner country",
                "Show trade balance",
            ],
            "followups": [
                {"question": "Show trade balance"},
                {"message": "Show growth rate"},
            ],
            "follow_ups": [
                "Compare imports and exports",
                "Show total weight",
            ],
        }
    )

    expected = [
        "Show exports by partner country",
        "Compare imports and exports",
        "Show trade balance",
        "Show growth rate",
        "Show total weight",
    ]

    assert response.service == "trade"
    assert response.suggestions == expected
    assert block_types(response) == ["markdown", "suggestions"]
    assert response.message.content[1].title == "Related questions"
    assert response.message.content[1].items == expected


# Trade references should render as a references block and deduplicate repeated sources.
def test_trade_citations_render_references_block():
    response = normalize_chat_response(
        {
            "service": "trade",
            "answer": "Trade data source included.",
            "trade_result": {
                "references": [
                    {"source_id": "trade-volume", "title": "Trade Volume Dataset", "url": "https://example.test/trade"},
                    {"source_id": "trade-volume", "title": "Trade Volume Dataset Copy", "url": "https://example.test/trade-copy"},
                    {"source_id": "metadata", "title": "Trade Metadata", "url": "https://example.test/meta"},
                ],
            },
        }
    )

    assert response.service == "trade"
    assert block_types(response) == ["markdown", "references"]
    assert [item["title"] for item in block_by_title(response, "References").items] == [
        "Trade Volume Dataset",
        "Trade Volume Dataset Copy",
        "Trade Metadata",
    ]


def test_trade_top_level_citations_do_not_duplicate_as_references_block():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data source included.",
            "citations": [
                {
                    "source_id": "trade-volume",
                    "title": "Trade Volume Dataset",
                    "url": "https://example.test/trade",
                }
            ],
            "trade_result": {
                "references": [
                    {
                        "source_id": "trade-volume",
                        "title": "Trade Volume Dataset",
                        "url": "https://example.test/trade",
                    }
                ],
            },
        }
    )

    assert response.service == "trade"
    assert [citation.document_id for citation in response.citations] == ["trade-volume"]
    assert [citation.title for citation in response.citations] == ["Trade Volume Dataset"]
    assert [block.type for block in response.message.content] == ["markdown"]


def test_trade_nested_references_render_only_when_no_equivalent_top_level_citation_exists():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data source included.",
            "citations": [
                {
                    "source_id": "top-level-source",
                    "title": "Top Level Dataset",
                    "url": "https://example.test/top-level",
                }
            ],
            "trade_result": {
                "references": [
                    {
                        "source_id": "trade-volume",
                        "title": "Trade Volume Dataset",
                        "url": "https://example.test/trade",
                    }
                ],
            },
        }
    )

    assert [citation.document_id for citation in response.citations] == ["top-level-source"]
    assert block_types(response) == ["markdown", "references"]
    assert block_by_title(response, "References").items == [
        {
            "id": 1,
            "title": "Trade Volume Dataset",
            "url": "https://example.test/trade",
            "dataset": None,
            "period": None,
            "chunk_index": None,
            "source_id": "trade-volume",
        }
    ]


def test_trade_reference_dedupe_keeps_same_title_for_distinct_dataset_period_or_chunk():
    response = normalize_chat_response(
        {
            "intent": "trade_query",
            "answer": "Trade data source included.",
            "trade_result": {
                "references": [
                    {
                        "title": "Trade Volume Dataset",
                        "dataset": "exports",
                        "period": "2024",
                        "chunk_index": 1,
                    },
                    {
                        "title": "Trade Volume Dataset",
                        "dataset": "imports",
                        "period": "2024",
                        "chunk_index": 1,
                    },
                    {
                        "title": "Trade Volume Dataset",
                        "dataset": "exports",
                        "period": "2024",
                        "chunk_index": 2,
                    },
                    {
                        "title": "Trade Volume Dataset",
                        "url": "https://example.test/trade-volume",
                        "dataset": "exports",
                        "period": "2024",
                    },
                    {
                        "title": "Trade Volume Dataset Copy",
                        "url": "https://example.test/trade-volume",
                        "dataset": "exports-copy",
                        "period": "2025",
                    },
                ],
            },
        }
    )

    references = block_by_title(response, "References").items

    assert len(references) == 4
    assert [(item["dataset"], item["period"], item["chunk_index"]) for item in references[:3]] == [
        ("exports", "2024", 1),
        ("imports", "2024", 1),
        ("exports", "2024", 2),
    ]
    assert references[3]["url"] == "https://example.test/trade-volume"


# Plain-text trade responses should only add the service label and continue rendering as markdown.
def test_plain_text_trade_fallback_stays_markdown():
    response = normalize_chat_response({"intent": "trade", "answer": "Trade answer without structured rows."})

    assert response.service == "trade"
    assert response.response.content == "Trade answer without structured rows."
    assert block_types(response) == ["markdown"]


# Unknown payloads should stay explicit instead of being mislabeled as general.
def test_unknown_response_sets_service_field_to_unknown():
    response = normalize_chat_response({"answer": "I do not have a service hint."})

    assert response.service == "unknown"
    assert response.intent == "general"


# Structured calculator references must deduplicate repeated source IDs, URLs, and titles.
def test_structured_calculator_reference_items_are_deduplicated():
    response = normalize_chat_response(
        {
            "answer": "Calculation complete.",
            "calculator_result": {
                "summary": {"total_tax": 1},
                "references": [
                    {"id": "tariff-1", "title": "Customs Tariff", "url": "https://example.test/tariff"},
                    {"id": "tariff-1", "title": "Customs Tariff Copy", "url": "https://example.test/tariff-copy"},
                    {"id": "tariff-2", "title": "Customs Tariff", "url": "https://example.test/other"},
                    {"id": "vat-1", "title": "VAT Rule", "url": "https://example.test/vat"},
                ],
            },
        }
    )

    references = block_by_title(response, "References")

    assert [item["id"] for item in references.items] == [1, 2]
    assert [item["title"] for item in references.items] == ["Customs Tariff", "VAT Rule"]


# Duplicate citations should be removed so the frontend does not show repeated sources.
def test_deduplicates_citations_by_url():
    response = normalize_chat_response(
        {
            "answer": "Use the cited source.",
            "citations": [
                {"id": "a", "title": "First", "url": "https://example.test/source"},
                {"id": "b", "title": "Duplicate", "url": "https://example.test/source"},
                {"id": "c", "title": "Other", "url": "https://example.test/other"},
            ],
        }
    )

    assert [citation.id for citation in response.citations] == ["a", "c"]


# Failed upstream responses must become an error block instead of a blank assistant message.
def test_failed_status_adds_error_block():
    response = normalize_chat_response(
        {
            "status": "failed",
            "error": {"message": "Main chatbot service is unavailable"},
        }
    )

    assert response.status == "failed"
    assert block_types(response) == ["error"]
    assert response.message.content[0].message == "Main chatbot service is unavailable"


# Debug metadata should be present only when explicitly requested.
def test_include_debug_collects_internal_metadata():
    response = normalize_chat_response(
        {
            "answer": "Debug me.",
            "latency_ms": 42.5,
            "metadata": {"candidate_confidence": "medium", "language": "en"},
        },
        include_debug=True,
    )

    assert response.debug is not None
    assert response.debug.latency_ms == 42.5
    assert response.debug.confidence == "medium"
    assert response.debug.metadata["language"] == "en"

def test_retrieval_clarification_required_without_questions_becomes_completed():
    response = normalize_chat_response({
        "service": "retrieval",
        "intent": "hs_code_lookup",
        "status": "clarification_required",
        "answer": "HS 8471.30.20",
        "clarifications": [],
    })

    assert response.status == "completed"
    assert response.clarifications == []

def test_khmer_gdce_tariff_url_creates_official_reference_block():
    response = normalize_chat_response({
        "service": "retrieval",
        "intent": "hs_code_lookup",
        "status": "completed",
        "language": "km",
        "answer": (
            "ចម្លើយជាភាសាខ្មែរ...\n\n"
            "សូមពិនិត្យផ្ទៀងផ្ទាត់លើគេហទំព័រផ្លូវការរបស់ GDCE៖ "
            "https://customs.gov.kh/en/publications/"
            "14037-customs-tariff-of-cambodia-km-2022"
        ),
    })

    assert [block.type for block in response.message.content] == [
        "markdown",
        "official_reference",
    ]

    official_block = response.message.content[1]

    assert official_block.title == "Official GDCE tariff lookup"
    assert official_block.agency == "GDCE"
    assert official_block.source_type == "official_tariff"
