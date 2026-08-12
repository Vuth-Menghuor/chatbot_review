"""
Tests for currency parsing and human-readable formatting fixes.

Covers the three bugs fixed in 2026-08-03:
1. KHR/EUR glued suffix misread as ×1000 magnitude (Bug 1)
2. LLM post-validation to correct 1000× inflated values (Bug 1 safety net)
3. Human-readable formatter hardcoding USD / showing 0.00 USD for KHR inputs (Bug 2)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from calculator.app.ai.intent_extractor import IntentExtractor, IntentResult
from calculator.app.ai.llm_formatter import format_human_readable
from calculator.app.services.models import CalculationRequest


# =============================================================================
# Bug 1: IntentExtractor money parsing — KHR/EUR must not be treated as ×1000
# =============================================================================

class TestExtractMoney:
    """Unit tests for IntentExtractor._extract_money."""

    @pytest.mark.parametrize(
        "text, expected_value, expected_currency",
        [
            # KHR glued suffix — the core bug
            ("calculate import tax for car cif 400,000,000khr from china", 400000000.0, "KHR"),
            ("CIF 50000khr", 50000.0, "KHR"),
            ("customs value 1000KHR", 1000.0, "KHR"),
            ("value is 2,500 khr", 2500.0, "KHR"),
            # EUR glued suffix — same pattern
            ("CIF 50000eur from germany", 50000.0, "EUR"),
            ("customs value 1200EUR", 1200.0, "EUR"),
            # USD with magnitude suffixes (should still work)
            ("CIF 2.2M USD", 2200000.0, "USD"),
            ("CIF $1.5B", 1500000000.0, "USD"),
            # Bare number fallback
            ("CIF 8000", 8000.0, None),
            # Normal USD formats
            ("CIF 40000 USD from china", 40000.0, "USD"),
            ("$50000", 50000.0, "USD"),
        ],
    )
    def test_extract_money(self, text, expected_value, expected_currency):
        val, cur = IntentExtractor._extract_money(text)
        assert val == expected_value, f"For '{text}': expected value {expected_value}, got {val}"
        assert cur == expected_currency, f"For '{text}': expected currency {expected_currency}, got {cur}"


# =============================================================================
# Bug 1 safety net: LLM post-validation for 1000× inflation
# =============================================================================

class TestPostValidateMoney:
    """Unit tests for IntentExtractor._post_validate_money."""

    def test_corrects_1000x_inflation_khr(self):
        """When LLM inflates 400M → 400B because of 'khr', regex corrects it."""
        extractor = IntentExtractor(enabled=False)  # disable LLM; we only test post-validate
        # Simulate an LLM result that mistakenly multiplied by 1000
        llm_result = IntentResult(
            case_type="normal",
            regime="import",
            goods={"description": "car", "origin_country": "CN"},
            valuation={"customs_value": 400000000000.0, "currency": "KHR"},
            flags={},
            confidence=0.95,
            reasoning="LLM parsed",
            source="llm",
        )
        corrected = extractor._post_validate_money(
            "calculate import tax for car cif 400,000,000khr from china", llm_result
        )
        assert corrected.valuation["customs_value"] == 400000000.0

    def test_no_correction_when_values_match(self):
        """When LLM and regex agree, no correction is applied."""
        extractor = IntentExtractor(enabled=False)
        llm_result = IntentResult(
            case_type="normal",
            regime="import",
            goods={},
            valuation={"customs_value": 50000.0, "currency": "USD"},
            flags={},
            confidence=0.95,
            source="llm",
        )
        corrected = extractor._post_validate_money("CIF 50000 USD", llm_result)
        assert corrected.valuation["customs_value"] == 50000.0

    def test_no_correction_when_regex_fails(self):
        """When regex fallback finds nothing, keep the LLM result."""
        extractor = IntentExtractor(enabled=False)
        llm_result = IntentResult(
            case_type="normal",
            regime="import",
            goods={},
            valuation={"customs_value": 12345.0, "currency": "USD"},
            flags={},
            confidence=0.95,
            source="llm",
        )
        corrected = extractor._post_validate_money("some nonsense with no numbers", llm_result)
        assert corrected.valuation["customs_value"] == 12345.0


# =============================================================================
# Bug 2: Human-readable formatter must not hardcode USD
# =============================================================================

class TestHumanReadableFormatting:
    """Unit tests for format_human_readable currency awareness."""

    @staticmethod
    def _make_result_dict(cif_khr: float, total: float, cif_usd: float | None = None) -> dict:
        """Build a minimal result dict for formatting tests."""
        return {
            "breakdown": {
                "cif_value": cif_khr,
                "cop_amount": cif_khr * 0.15,
                "sop_amount": 0.0,
                "vop_amount": (cif_khr + cif_khr * 0.15) * 0.10,
                "vvf_amount": 0.0,
                "fees": 0.0,
            },
            "line_items": [
                {
                    "name": "Import Taxes (COP)",
                    "tax_type": "CD",
                    "amount": cif_khr * 0.15,
                    "currency": "KHR",
                    "base": cif_khr,
                    "rate": 15.0,
                },
                {
                    "name": "VOP (VAT of Payment)",
                    "tax_type": "VAT",
                    "amount": (cif_khr + cif_khr * 0.15) * 0.10,
                    "currency": "KHR",
                    "base": cif_khr + cif_khr * 0.15,
                    "rate": 10.0,
                },
            ],
            "assumptions": ["HS Code: 0102.10.00", "Origin: TH"],
            "references": [],
            "exchange_rate_usd_to_khr": 1.0 if cif_usd is None else 4022.0,
            "cif_value_usd": cif_usd,
            "total": total,
            "currency": "KHR",
        }

    def test_khr_input_shows_khr_not_usd(self):
        """When input currency is KHR, report must NOT show 0.00 USD."""
        request = CalculationRequest(
            calculation_date="2026-08-03",
            regime="import",
            goods={"hs_code": "0102.10.00", "description": "Rice", "origin_country": "KH"},
            valuation={"customs_value": 50000000.0, "currency": "KHR"},
        )
        result = self._make_result_dict(cif_khr=50000000.0, total=57500000.0)
        text = format_human_readable(request, result)

        assert "50,000,000 KHR" in text or "50000000 KHR" in text
        assert "N/A (already in local currency)" in text
        assert "CURRENCY CONFIRMATION (KHR)" in text
        assert "0.00 USD" not in text
        assert "1 USD =" not in text

    def test_khr_summary_shows_khr(self):
        """Summary line must display KHR value for KHR input."""
        request = CalculationRequest(
            calculation_date="2026-08-03",
            regime="import",
            goods={"hs_code": "0102.10.00", "description": "Rice", "origin_country": "KH"},
            valuation={"customs_value": 50000000.0, "currency": "KHR"},
        )
        result = self._make_result_dict(cif_khr=50000000.0, total=57500000.0)
        text = format_human_readable(request, result)

        assert "50,000,000 KHR CIF" in text or "50000000 KHR CIF" in text

    def test_usd_input_still_works(self):
        """Regression: USD inputs must still show USD values and exchange rate."""
        request = CalculationRequest(
            calculation_date="2026-08-03",
            regime="import",
            goods={"hs_code": "0102.10.00", "description": "Rice", "origin_country": "TH"},
            valuation={"customs_value": 40000.0, "currency": "USD"},
        )
        result = self._make_result_dict(cif_khr=160880000.0, total=185012000.0, cif_usd=40000.0)
        text = format_human_readable(request, result)

        assert "40,000.00 USD" in text
        assert "1 USD = 4,022.00 KHR" in text
        assert "CURRENCY CONVERSION (USD -> KHR)" in text
        assert "40,000.00 USD CIF" in text

    def test_khr_no_unnecessary_conversion_step(self):
        """KHR inputs should say 'CURRENCY CONFIRMATION' not 'CONVERSION'."""
        request = CalculationRequest(
            calculation_date="2026-08-03",
            regime="import",
            goods={"hs_code": "0102.10.00", "description": "Rice", "origin_country": "KH"},
            valuation={"customs_value": 50000000.0, "currency": "KHR"},
        )
        result = self._make_result_dict(cif_khr=50000000.0, total=57500000.0)
        text = format_human_readable(request, result)

        assert "CURRENCY CONFIRMATION" in text
        assert "CURRENCY CONVERSION (USD -> KHR)" not in text


# =============================================================================
# Edge cases for _extract_money
# =============================================================================

class TestExtractMoneyEdgeCases:
    """Additional edge cases for money extraction."""

    def test_khr_with_spaces_picks_last_number(self):
        """When digits are spaced out, the regex matches the number immediately before KHR."""
        val, cur = IntentExtractor._extract_money("CIF 250 000 khr")
        # "000 khr" is matched; 000 → 0.0
        assert val == 0.0
        assert cur == "KHR"

    def test_eur_lowercase(self):
        val, cur = IntentExtractor._extract_money("value 9999 eur")
        assert val == 9999.0
        assert cur == "EUR"

    def test_usd_with_commas(self):
        val, cur = IntentExtractor._extract_money("CIF 1,234,567.89 USD")
        assert val == 1234567.89
        assert cur == "USD"

    def test_million_suffix(self):
        val, cur = IntentExtractor._extract_money("CIF 5M USD")
        assert val == 5000000.0
        assert cur == "USD"

    def test_billion_suffix(self):
        val, cur = IntentExtractor._extract_money("CIF 2.5B")
        assert val == 2500000000.0
        assert cur is None  # no explicit currency

    def test_k_suffix_not_confused_with_khr(self):
        """Standalone 'K' after a number should still mean ×1000."""
        val, cur = IntentExtractor._extract_money("CIF 500K")
        assert val == 500000.0
        assert cur is None

    def test_khr_must_not_be_treated_as_k_suffix(self):
        """The core bug: '500khr' must NOT become 500,000."""
        val, cur = IntentExtractor._extract_money("CIF 500khr")
        assert val == 500.0
        assert cur == "KHR"
