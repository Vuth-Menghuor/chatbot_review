from __future__ import annotations

from app.services.chat_response_normalizer import normalize_chat_response


# This file protects the API-to-frontend chat response contract before refactoring the large normalizer.


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
    assert "Basis: Declared value" in block_by_title(response, "Calculation Details").items[0].content
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


# Legacy assumptions must expose structured data used by the frontend assumptions section.
def test_legacy_assumptions_and_notes_include_structured_assumption_data():
    content = """IMPORT TAX CALCULATION
INPUT PARAMETERS:
* Declared Value: 500 USD per metric ton
* Exchange Rate: 4,100 KHR/USD
* Customs Regime: Petroleum two-phase

ASSUMPTIONS & NOTES:
* Import tax rate: 35%
* VOP rate: 10%
* Source: official tariff table
"""

    response = normalize_chat_response({"intent": "calculator", "answer": content})
    assumptions = block_by_title(response, "Assumptions & Notes")

    assert assumptions.data["assumptions"] == [
        {"label": "Declared value", "value": "500 USD per metric ton", "note": "Provided by the user"},
        {"label": "Exchange rate", "value": "4,100 KHR/USD"},
        {"label": "Calculation method", "value": "Petroleum two-phase"},
    ]
    assert assumptions.data["ratesApplied"] == [{"code": "CPP", "rate": "35%"}, {"code": "VPP", "rate": "10%"}]


# Trade payloads should expose the service label through the TradeNormalizer path.
def test_trade_response_sets_service_field():
    response = normalize_chat_response({"service": "trade", "intent": "trade", "answer": "Trade route answer."})

    assert response.service == "trade"
    assert block_types(response) == ["markdown"]


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
        "Trade Metadata",
    ]


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
