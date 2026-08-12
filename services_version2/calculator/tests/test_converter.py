"""
GDCE Calculator Service - Currency Converter Tests
====================================================
Test the standalone currency converter endpoints.
Uses FakeDB + TestClient pattern (same as test_api.py).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from calculator.app.main import create_app
from calculator.app.api.deps import get_db
from calculator.app.services.calculator import DatabaseInterface


class FakeDB(DatabaseInterface):
    """Minimal fake DB with exchange rate data for converter tests."""

    def get_duty_rates(self, hs_code: str, origin_country: str, effective_date: str):
        return {"cd_rate": Decimal("0.15"), "st_rate": Decimal("0"), "vat_rate": Decimal("0.10"), "et_rate": Decimal("0")}

    def get_exchange_rate(self, currency_code: str, effective_date: str):
        rates = {
            "USD": Decimal("4022"),
            "THB": Decimal("129.5"),
            "EUR": Decimal("4784"),
            "KHR": Decimal("1"),
        }
        return rates.get(currency_code.upper())

    def get_all_exchange_rates(self, effective_date: str = None):
        return {
            "USD": Decimal("4022"),
            "THB": Decimal("129.5"),
            "EUR": Decimal("4784"),
            "KHR": Decimal("1"),
        }

    def get_hs_code_info(self, hs_code: str):
        return {"description": "Test HS", "unit": "u"}

    def get_declared_value(self, hs_code: str, effective_date: str = None):
        return None

    def check_health(self):
        return {"ok": True, "message": "ok"}

    def search_by_description(self, query: str):
        return None

    def save_calculation(self, calculation_result):
        return None


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.dependency_overrides[get_db] = lambda: FakeDB()
    with TestClient(app) as test_client:
        yield test_client


# ================================================================
# GET /v1/currencies
# ================================================================

def test_get_supported_currencies(client: TestClient):
    """List all supported currencies."""
    resp = client.get("/v1/currencies")
    assert resp.status_code == 200
    body = resp.json()
    assert "currencies" in body
    assert body["count"] > 0
    codes = {c["code"] for c in body["currencies"]}
    assert "USD" in codes
    assert "KHR" in codes
    assert "EUR" in codes


def test_currency_info_has_required_fields(client: TestClient):
    """Each currency entry should have code, name, symbol, decimals."""
    resp = client.get("/v1/currencies")
    assert resp.status_code == 200
    body = resp.json()
    for c in body["currencies"]:
        assert "code" in c
        assert "name" in c
        assert "symbol" in c
        assert "decimals" in c


# ================================================================
# POST /v1/convert/natural
# ================================================================

def test_natural_convert_glued_amount_currency(client: TestClient):
    """'40000usd to khr' — amount glued to currency code."""
    resp = client.post("/v1/convert/natural", json={"query": "40000usd to khr"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed_amount"] == 40000
    assert body["parsed_from"] == "USD"
    assert body["parsed_to"] == "KHR"
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "KHR"
    assert body["converted_amount"] > 0


def test_natural_convert_with_symbol(client: TestClient):
    """'$500 to euro' — symbol + natural name."""
    resp = client.post("/v1/convert/natural", json={"query": "$500 to euro"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed_amount"] == 500
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "EUR"


def test_natural_convert_with_equals(client: TestClient):
    """'1000 THB = KHR' — equals separator."""
    resp = client.post("/v1/convert/natural", json={"query": "1000 THB = KHR"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed_amount"] == 1000
    assert body["from_currency"] == "THB"
    assert body["to_currency"] == "KHR"


def test_natural_convert_explicit_convert(client: TestClient):
    """'convert 40000 USD to KHR' — explicit verb."""
    resp = client.post("/v1/convert/natural", json={"query": "convert 40000 USD to KHR"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed_amount"] == 40000
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "KHR"


def test_natural_convert_with_arrow(client: TestClient):
    """'40000 usd → khr' — arrow separator."""
    resp = client.post("/v1/convert/natural", json={"query": "40000 usd → khr"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed_amount"] == 40000
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "KHR"


def test_natural_convert_missing_amount_returns_400(client: TestClient):
    """Query with no amount should return 400."""
    resp = client.post("/v1/convert/natural", json={"query": "usd to khr"})
    assert resp.status_code == 400


def test_natural_convert_empty_query_returns_422(client: TestClient):
    """Empty query should trigger FastAPI validation (422)."""
    resp = client.post("/v1/convert/natural", json={"query": ""})
    assert resp.status_code == 422


# ================================================================
# POST /v1/convert/natural — additional edge cases
# ================================================================

def test_natural_convert_comma_in_amount(client: TestClient):
    """'10,000 USD to KHR' — comma-separated thousands."""
    resp = client.post("/v1/convert/natural", json={"query": "10,000 USD to KHR"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed_amount"] == 10000
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "KHR"


def test_natural_convert_decimal_amount(client: TestClient):
    """'1500.50 USD to KHR' — decimal amount."""
    resp = client.post("/v1/convert/natural", json={"query": "1500.50 USD to KHR"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed_amount"] == 1500.5


def test_natural_convert_with_convert_verb(client: TestClient):
    """'convert 1000 THB to KHR' — explicit verb before amount."""
    resp = client.post("/v1/convert/natural", json={"query": "convert 1000 THB to KHR"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed_amount"] == 1000
    assert body["from_currency"] == "THB"
    assert body["to_currency"] == "KHR"


def test_natural_convert_missing_target_returns_400(client: TestClient):
    """'100 USD' — missing target currency should return 400."""
    resp = client.post("/v1/convert/natural", json={"query": "100 USD"})
    assert resp.status_code == 400


def test_natural_convert_only_text_returns_400(client: TestClient):
    """Query with no amount and no parseable currencies."""
    resp = client.post("/v1/convert/natural", json={"query": "hello world"})
    assert resp.status_code == 400


def test_natural_convert_cross_currency(client: TestClient):
    """USD → EUR (cross rate through KHR)."""
    resp = client.post("/v1/convert/natural", json={"query": "100 USD to EUR"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "EUR"
    assert body["exchange_rate"] > 0
    assert body["exchange_rate"] < 1  # USD is weaker than EUR in fake rates


def test_natural_convert_same_currency(client: TestClient):
    """USD → USD should return rate 1.0."""
    resp = client.post("/v1/convert/natural", json={"query": "500 USD to USD"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["exchange_rate"] == 1.0
    assert body["converted_amount"] == 500.0
    assert "same" in body["note"].lower()


def test_natural_convert_khr_rounding_up(client: TestClient):
    """Converting 1 THB to KHR → 129.5 → rounded UP to nearest 100 = 200."""
    resp = client.post("/v1/convert/natural", json={"query": "1 THB to KHR"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["to_currency"] == "KHR"
    assert body["converted_amount"] >= 200.0


def test_natural_convert_response_has_all_fields(client: TestClient):
    """Every response field declared in schema is present."""
    resp = client.post("/v1/convert/natural", json={"query": "40000usd to khr"})
    assert resp.status_code == 200
    body = resp.json()
    required = {
        "query", "parsed_amount", "parsed_from", "parsed_to",
        "from_currency", "to_currency", "exchange_rate",
        "converted_amount", "note",
    }
    assert required.issubset(set(body.keys()))
