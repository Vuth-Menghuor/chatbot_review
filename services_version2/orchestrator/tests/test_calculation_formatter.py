import pytest

from services_version2.orchestrator.formatter_service.core.calculation_formatter import (
    format_calculation_response,
)
from services_version2.orchestrator.formatter_service.providers.gemini import (
    GeminiFormatterProvider,
)


def sample_calc_result():
    return {
        "total": 120000,
        "currency": "KHR",
        "breakdown": {"cif_value": 100000},
        "line_items": [
            {"tax_type": "CD", "amount": 0, "rate": 0},
            {"tax_type": "ST", "amount": 20000, "rate": 20},
            {"tax_type": "VAT", "amount": 10000, "rate": 10},
        ],
        "assumptions": ["HS Code: 8703", "Product: Car engine", "Origin: China"],
        "references": [{"doc_id": "hs_8703:desc", "title": "HS 8703 reference"}],
        "exchange_rate_usd_to_khr": 4000,
        "original_cif_value": 100,
        "original_currency": "USD",
    }


def test_format_calculation_response_basic():
    res = sample_calc_result()
    out = format_calculation_response(res, question="calculate import tax for car from china")
    assert isinstance(out, str)
    assert "STEP 1" in out or "STEP 2" in out
    assert "FINAL TAX BREAKDOWN" in out
    assert "COP" in out or "CD" in out


def test_gemini_prompt_includes_step_by_step():
    # Ensure the Gemini provider's calculation prompt asks for step-by-step breakdown
    provider = GeminiFormatterProvider(config=type("C", (), {"gemini_api_key": None, "gemini_model": None, "timeout": 10}))
    prompt = provider._prompt_calculation("RAW", "question text", "")
    assert "step-by-step" in prompt.lower() or "step by step" in prompt.lower()


def test_gemini_prompt_hs_code_lookup():
    provider = GeminiFormatterProvider(config=type("C", (), {"gemini_api_key": None, "gemini_model": None, "timeout": 10}))
    prompt = provider._prompt_hs_code("RAW", "question text", "")
    assert "hs code" in prompt.lower()


@pytest.mark.asyncio
async def test_formatter_intent_mapping():
    from services_version2.orchestrator.formatter_service.core.models import FormatterIntent
    from services_version2.orchestrator.formatter_service.service import OrchestratorFormatterService
    from unittest.mock import AsyncMock

    config = type("C", (), {
        "provider": "gemini",
        "gemini_api_key": "dummy",
        "gemini_model": "dummy-model",
        "timeout": 10
    })()
    
    service = OrchestratorFormatterService(config)
    service._provider.format_response = AsyncMock(return_value="FORMATTED")
    
    res = await service.format_response("RAW_ANSWER", "question text", "hs_code_lookup")
    assert res == "FORMATTED"
    service._provider.format_response.assert_called_once_with(
        response_text="RAW_ANSWER",
        intent=FormatterIntent.HS_CODE_LOOKUP,
        original_question="question text",
        context={}
    )

    # Test policy_query maps to GENERAL
    await service.format_response("RAW_ANSWER", "question text", "policy_query")
    service._provider.format_response.assert_called_with(
        response_text="RAW_ANSWER",
        intent=FormatterIntent.GENERAL,
        original_question="question text",
        context={}
    )
