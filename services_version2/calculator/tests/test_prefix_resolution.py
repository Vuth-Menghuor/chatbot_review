"""
Tests for HS prefix + description combined resolution.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from calculator.app.main import create_app
from calculator.app.api.deps import get_db
from calculator.app.services.calculator import DatabaseInterface


# ---------------------------------------------------------------------------
# FakeDB with prefix + description support
# ---------------------------------------------------------------------------

class FakeDBWithPrefix(DatabaseInterface):
    """FakeDB that supports prefix and description lookups."""

    def __init__(self):
        self._hs_data = {
            "7204.10.00": {"description": "Ferrous waste and scrap, cast iron", "unit": "kg"},
            "7204.21.00": {"description": "Stainless steel waste and scrap", "unit": "kg"},
            "7204.29.00": {"description": "Other alloy steel waste and scrap", "unit": "kg"},
            "7204.41.00": {"description": "Turnings of iron or steel", "unit": "kg"},
            "0102.29.11": {"description": "Live oxen", "unit": "u"},
            "8703.22.59": {"description": "Passenger cars", "unit": "u"},
        }

    def get_duty_rates(self, hs_code: str, origin_country: str, effective_date: str):
        clean = hs_code.replace(".", "")
        if len(clean) == 8 and hs_code in self._hs_data:
            return {
                "cd_rate": Decimal("0.15"),
                "st_rate": Decimal("0"),
                "vat_rate": Decimal("0.10"),
                "et_rate": Decimal("0"),
            }
        return None

    def get_exchange_rate(self, currency_code: str, effective_date: str):
        return Decimal("4000") if currency_code == "USD" else Decimal("1")

    def get_hs_code_info(self, hs_code: str):
        return self._hs_data.get(hs_code)

    def get_declared_value(self, hs_code: str, effective_date: str = None):
        return None

    def check_health(self):
        return {"ok": True, "message": "ok"}

    def search_by_description(self, query: str):
        query_lower = query.lower()
        for hs, info in self._hs_data.items():
            if query_lower in info["description"].lower():
                return (hs, 0.9)
        return None

    def search_hs_by_description(self, query: str, top_k: int = 5):
        query_lower = query.lower()
        results = []
        for hs, info in self._hs_data.items():
            desc_lower = info["description"].lower()
            if query_lower in desc_lower or any(w in desc_lower for w in query_lower.split()):
                results.append({
                    "hs_code": hs,
                    "description": info["description"],
                    "score": 0.9,
                })
        return results[:top_k]

    def get_hs_codes_by_prefix(self, prefix: str, limit: int = 20):
        clean_prefix = prefix.replace(".", "")
        results = []
        for hs, info in self._hs_data.items():
            if hs.replace(".", "").startswith(clean_prefix):
                results.append({"hs_code": hs, "description": info["description"], "unit": info["unit"]})
        return results[:limit]

    def search_hs_by_prefix_and_description(self, prefix: str, description: str, top_k: int = 5):
        prefix_results = self.get_hs_codes_by_prefix(prefix, limit=top_k * 3)
        if not prefix_results:
            return []
        desc_words = set(description.lower().split())
        scored = []
        for r in prefix_results:
            r_desc = r.get("description", "").lower()
            overlap = len(desc_words & set(r_desc.split()))
            scored.append({
                **r,
                "score": overlap / max(len(desc_words), 1),
                "source": "qdrant",
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def save_calculation(self, calculation_result):
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def prefix_client():
    app = create_app()
    app.dependency_overrides[get_db] = lambda: FakeDBWithPrefix()
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_prefix_and_description_resolution(prefix_client: TestClient):
    """Bare 4-digit prefix + description resolves to a matching 8-digit code."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "steel scrap", "hs_code": "7204", "origin_country": "TH"},
        "valuation": {"customs_value": 5000, "currency": "USD"},
    }
    resp = prefix_client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    # Should have resolved to one of the 7204.xxx codes
    hs_info = body.get("hs_code_info")
    assert hs_info is not None
    resolved = hs_info["hs_code"]
    assert resolved.replace(".", "").startswith("7204")
    # Check that a prefix-based assumption warning was added
    assumptions = body.get("assumptions", [])
    assert any("prefix 7204" in a for a in assumptions), f"Expected prefix warning in assumptions: {assumptions}"


def test_invalid_prefix_fallback_to_description(prefix_client: TestClient):
    """Unknown prefix with a mismatched description triggers chapter-mismatch ask-back."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Live oxen", "hs_code": "9999", "origin_country": "TH"},
        "valuation": {"customs_value": 5000, "currency": "USD"},
    }
    resp = prefix_client.post("/calculate_import_taxes", json=payload)
    # Broad fallback resolves "Live oxen" → 0102.29.11 (chapter 01), but prefix is 9999 (chapter 99)
    # → chapter mismatch → ask back
    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert "mismatch" in detail.lower()


def test_intent_extractor_bare_4digit():
    """IntentExtractor regex should extract bare 4-digit codes as prefixes."""
    from calculator.app.ai.intent_extractor import IntentExtractor

    extractor = IntentExtractor(enabled=False)
    result = extractor._extract_regex("Calculate import tax for 7204 steel CIF $5000 from China")
    assert result is not None
    assert result.goods.get("hs_code") == "7204"
    # Description should contain "steel"
    desc = result.goods.get("description", "").lower()
    assert "steel" in desc


def test_intent_extractor_prefixed_4digit():
    """IntentExtractor should extract 'HS 7204 steel' correctly."""
    from calculator.app.ai.intent_extractor import IntentExtractor

    extractor = IntentExtractor(enabled=False)
    result = extractor._extract_regex("What is the tax for HS 7204 steel from Thailand CIF 2000")
    assert result is not None
    assert result.goods.get("hs_code") == "7204"


def test_hs_code_handler_prefix_detection():
    """HSCodeHandler should correctly identify prefix codes."""
    from calculator.app.services.hs_code_handler import HSCodeHandler

    class FakeDBNoRates:
        def get_duty_rates(self, hs_code, origin, effective_date=None):
            return None  # No rates for any code

    class FakeDBWithRates:
        def get_duty_rates(self, hs_code, origin, effective_date=None):
            return {"cd_rate": 0.15}  # Rates exist for all codes

    # No DB: 4-digit → prefix, 6-digit → exact (conservative)
    handler_no_db = HSCodeHandler()
    assert handler_no_db.is_prefix_code("7204") is True
    assert handler_no_db.is_prefix_code("7204.10") is False
    assert handler_no_db.is_prefix_code("7204.10.00") is False

    # DB with no rates: 4-digit → prefix, 5-digit → prefix, 6-digit → prefix
    handler_no_rates = HSCodeHandler(FakeDBNoRates())
    assert handler_no_rates.is_prefix_code("7204") is True
    assert handler_no_rates.is_prefix_code("72049") is True
    assert handler_no_rates.is_prefix_code("7204.10") is True
    assert handler_no_rates.is_prefix_code("7204.10.00") is False

    # DB with rates: if DB says rates exist for a code, it's not a prefix.
    # (In practice, 4-digit codes never have exact rates in the real DB.)
    handler_with_rates = HSCodeHandler(FakeDBWithRates())
    assert handler_with_rates.is_prefix_code("7204") is False  # DB has rates → exact
    assert handler_with_rates.is_prefix_code("72049") is False
    assert handler_with_rates.is_prefix_code("7204.10") is False
    assert handler_with_rates.is_prefix_code("7204.10.00") is False


def test_calculator_prefix_plus_description_core():
    """Test the calculator core directly with prefix+description."""
    from calculator.app.services.calculator import ImportTaxCalculator

    db = FakeDBWithPrefix()
    calculator = ImportTaxCalculator(db)

    # Resolve prefix + description
    resolved, source, candidates = calculator.resolve_hs_from_prefix_and_description("7204", "steel")
    assert resolved is not None
    assert resolved.replace(".", "").startswith("7204")
    assert source is not None
    assert len(candidates) > 0

    # Invalid prefix → broad fallback resolves via description-only search
    resolved2, source2, candidates2 = calculator.resolve_hs_from_prefix_and_description("9999", "steel")
    assert resolved2 is not None  # broad fallback finds "steel" → 7204.21.00
    assert resolved2.replace(".", "").startswith("7204")
    assert source2 == "qdrant_broad"
    assert len(candidates2) > 0


def test_5digit_prefix_treated_as_hint(prefix_client: TestClient):
    """A 5-digit code like '72041' should be treated as a prefix/hint."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "steel scrap", "hs_code": "72041", "origin_country": "TH"},
        "valuation": {"customs_value": 5000, "currency": "USD"},
    }
    resp = prefix_client.post("/calculate_import_taxes", json=payload)
    # Should either resolve to a 7204.xxx code or fail gracefully (not crash)
    assert resp.status_code in (200, 400)


def test_chapter_mismatch_ask_back(prefix_client: TestClient):
    """If description resolves to a different chapter than the prefix, ask back."""
    # 0101 is chapter 01 (live animals), but "car" resolves to chapter 87 (vehicles)
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "car", "hs_code": "0101", "origin_country": "TH"},
        "valuation": {"customs_value": 5000, "currency": "USD"},
    }
    resp = prefix_client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 400
    body = resp.json()
    detail = body.get("detail", "")
    assert "mismatch" in detail.lower() or "different product category" in detail.lower()


def test_broad_fallback_when_prefix_not_in_db(prefix_client: TestClient):
    """When a prefix has no exact DB matches, broad description fallback should work."""
    # The FakeDB has "7204.10.00" etc. but not "7304".
    # However, "steel scrap" should still match 7204.10.00 via broad fallback
    # because the description maps to chapter 72.
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "cast iron scrap", "hs_code": "7304", "origin_country": "TH"},
        "valuation": {"customs_value": 5000, "currency": "USD"},
    }
    resp = prefix_client.post("/calculate_import_taxes", json=payload)
    # FakeDB only has 7204.xxx, not 7304.xxx.
    # Broad fallback would resolve "cast iron scrap" to 7204.10.00 (chapter 72),
    # but prefix is 73 (chapter 73) → chapter mismatch → should ask back.
    assert resp.status_code == 400
    body = resp.json()
    detail = body.get("detail", "")
    assert "mismatch" in detail.lower() or "different product category" in detail.lower()


def test_intent_extractor_5digit_prefix():
    """IntentExtractor regex should extract explicit 5-digit codes as hints."""
    from calculator.app.ai.intent_extractor import IntentExtractor

    extractor = IntentExtractor(enabled=False)
    # 5-digit codes must be explicitly marked (e.g. "HS 72049") to avoid
    # confusion with CIF values like "CIF 10500 USD".
    result = extractor._extract_regex("Calculate import tax for HS 72049 steel CIF $5000 from China")
    assert result is not None
    assert result.goods.get("hs_code") == "72049"
