from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from calculator.app.main import create_app
from calculator.app.api.deps import get_db
from calculator.app.services.calculator import DatabaseInterface

# Deterministic tests: force IntentExtractor to always fall back to regex
# (LLM extraction is non-deterministic and may return stale USD defaults)
from calculator.app.ai.intent_extractor import IntentExtractor

async def _mock_extract_llm(self, text: str):
    return None

IntentExtractor._extract_llm = _mock_extract_llm


class FakeDB(DatabaseInterface):
    def get_duty_rates(self, hs_code: str, origin_country: str, effective_date: str):
        return {"cd_rate": Decimal("0.15"), "st_rate": Decimal("0"), "vat_rate": Decimal("0.10"), "et_rate": Decimal("0")}

    def get_exchange_rate(self, currency_code: str, effective_date: str):
        return Decimal("4000") if currency_code == "USD" else Decimal("1")

    def get_hs_code_info(self, hs_code: str):
        return {"description": "Test HS", "unit": "u"}

    def get_declared_value(self, hs_code: str, effective_date: str = None):
        return None

    def check_health(self):
        return {"ok": True, "message": "ok"}

    def search_by_description(self, query: str):
        return None

    def save_calculation(self, calculation_result: Any):
        return None


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.dependency_overrides[get_db] = lambda: FakeDB()
    with TestClient(app) as test_client:
        yield test_client


def test_calculate_endpoint(client: TestClient):
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {
            "description": "Laptops",
            "hs_code": "8471",
            "origin_country": "TH",
            "quantity": 1,
        },
        "valuation": {"customs_value": 1000, "currency": "USD", "exchange_rate_to_khr": 560.0},
    }

    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "KHR"
    assert body["total"] > 0
    assert "breakdown" in body
    assert body["exchange_rate_usd_to_khr"] == 560.0


# ================================================================
# Ask-Back Flow Tests
# ================================================================

def test_normal_case_no_fta_calculates_normally(client: TestClient):
    """Normal import with no FTA/exemption should calculate fully."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Rice", "hs_code": "1006", "origin_country": "TH"},
        "valuation": {"customs_value": 5000, "currency": "USD"},
        "flags": {"fta_applicable": False},
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "KHR"
    assert body["total"] > 0
    assert body.get("preferential_rate_missing") is None
    assert body.get("requested_agreement") is None


def test_fta_without_rate_returns_ask_back(client: TestClient):
    """ACFTA claimed but DB has no rate and no DV → ask-back, no calculation."""
    # Override with a FakeDB that has no preferential rate for CN/ACFTA
    class FakeDBNoFTA(DatabaseInterface):
        def get_duty_rates(self, hs_code, origin_country, effective_date):
            if origin_country == "XX":
                return {"cd_rate": Decimal("0.15"), "st_rate": Decimal("0"), "vat_rate": Decimal("0.10"), "et_rate": Decimal("0")}
            return None
        def get_exchange_rate(self, currency_code, effective_date):
            return Decimal("4000")
        def get_hs_code_info(self, hs_code):
            return {"description": "Test HS", "unit": "u"}
        def get_declared_value(self, hs_code, effective_date=None):
            return None
        def check_health(self):
            return {"ok": True, "message": "ok"}
        def search_by_description(self, query):
            return None
        def save_calculation(self, calculation_result):
            return None

    app = create_app()
    app.dependency_overrides[get_db] = lambda: FakeDBNoFTA()
    with TestClient(app) as tc:
        payload = {
            "calculation_date": "2026-03-25",
            "regime": "import",
            "goods": {"description": "Cars", "hs_code": "8703", "origin_country": "CN"},
            "valuation": {"customs_value": 10000, "currency": "USD"},
            "flags": {
                "fta_applicable": True,
                "fta_certificate_type": "ACFTA",
            },
        }
        resp = tc.post("/calculate_import_taxes", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("preferential_rate_missing") is True
        assert body.get("requested_agreement") == "ACFTA"
        assert body["total"] == 0
        assert body["breakdown"]["cop_amount"] == 0


def test_fta_with_rate_calculates_normally(client: TestClient):
    """ACFTA claimed with preferential_cd_rate=0 → full calculation."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Cars", "hs_code": "8703", "origin_country": "CN"},
        "valuation": {"customs_value": 10000, "currency": "USD"},
        "flags": {
            "fta_applicable": True,
            "fta_certificate_type": "ACFTA",
            "preferential_cd_rate": 0,
        },
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("preferential_rate_missing") is False
    assert body["total"] > 0
    # COP should be 0 because CD rate = 0%
    assert body["breakdown"]["cop_amount"] == 0


def test_exemption_without_rate_returns_ask_back(client: TestClient):
    """QIP exemption claimed but no rate → ask-back."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Machinery", "hs_code": "8471", "origin_country": "XX"},
        "valuation": {"customs_value": 50000, "currency": "USD"},
        "flags": {"qip_exemption": True},
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("preferential_rate_missing") is True
    assert body.get("requested_agreement") == "QIP"
    assert body["total"] == 0


def test_exemption_with_rate_calculates_normally(client: TestClient):
    """QIP exemption with preferential_cd_rate=5 → full calculation."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Machinery", "hs_code": "8471", "origin_country": "XX"},
        "valuation": {"customs_value": 50000, "currency": "USD"},
        "flags": {"qip_exemption": True, "preferential_cd_rate": 5},
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("preferential_rate_missing") is False
    assert body["total"] > 0


# ================================================================
# Ask-Back: Description vs HS Code Conflict
# ================================================================

def test_query_conflict_description_vs_hs_asks_back(client: TestClient):
    """
    When the user says 'steel' but gives HS 8703 (motor vehicles),
    the calculator detects a chapter mismatch and asks back.
    """
    class FakeDBWithConflict(DatabaseInterface):
        def get_duty_rates(self, hs_code, origin_country, effective_date):
            return {"cd_rate": Decimal("0.15"), "st_rate": Decimal("0"), "vat_rate": Decimal("0.10"), "et_rate": Decimal("0")}

        def get_exchange_rate(self, currency_code, effective_date):
            return Decimal("4000")

        def get_hs_code_info(self, hs_code):
            # Return different descriptions so the message is clear
            if hs_code.startswith("8703"):
                return {"description": "Motor vehicles", "unit": "u"}
            if hs_code.startswith("7204"):
                return {"description": "Iron and steel waste and scrap", "unit": "kg"}
            return {"description": "Test HS", "unit": "u"}

        def get_declared_value(self, hs_code, effective_date=None):
            return None

        def check_health(self):
            return {"ok": True, "message": "ok"}

        def search_hs_by_description(self, query, top_k=1):
            """Return a result that maps 'steel' to HS 7204."""
            if "steel" in query.lower():
                return [{"hs_code": "7204.10.00", "description": "Iron and steel waste and scrap", "score": 0.95}]
            return []

        def search_by_description(self, query):
            return None

        def save_calculation(self, calculation_result):
            return None

    app = create_app()
    app.dependency_overrides[get_db] = lambda: FakeDBWithConflict()
    with TestClient(app) as tc:
        resp = tc.post("/query", json={"question": "Calculate tax for steel HS 8703 CIF 10500 USD from China"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["needs_clarification"] is True
        assert body["source"] == "conflict_detector"
        assert "steel" in body["answer"]
        assert "8703" in body["answer"]
        assert "Motor vehicles" in body["answer"] or "motor vehicles" in body["answer"].lower()


def test_query_no_conflict_proceeds_normally(client: TestClient):
    """
    When description and HS code align (same chapter), calculation proceeds.
    """
    class FakeDBNoConflict(DatabaseInterface):
        def get_duty_rates(self, hs_code, origin_country, effective_date):
            return {"cd_rate": Decimal("0.15"), "st_rate": Decimal("0"), "vat_rate": Decimal("0.10"), "et_rate": Decimal("0")}

        def get_exchange_rate(self, currency_code, effective_date):
            return Decimal("4000")

        def get_hs_code_info(self, hs_code):
            return {"description": "Cars", "unit": "u"}

        def get_declared_value(self, hs_code, effective_date=None):
            return None

        def check_health(self):
            return {"ok": True, "message": "ok"}

        def search_hs_by_description(self, query, top_k=1):
            # Description resolves to same chapter 87
            if "car" in query.lower() or "vehicle" in query.lower():
                return [{"hs_code": "8703.22.00", "description": "Motor cars", "score": 0.95}]
            return []

        def search_by_description(self, query):
            return None

        def save_calculation(self, calculation_result):
            return None

    app = create_app()
    app.dependency_overrides[get_db] = lambda: FakeDBNoConflict()
    with TestClient(app) as tc:
        resp = tc.post("/query", json={"question": "Calculate tax for cars HS 8703 CIF 20000 USD from Japan"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body.get("needs_clarification") is not True
        assert body["source"] in ("llm", "regex")


def test_petroleum_with_fta_returns_ask_back(client: TestClient):
    """Petroleum case + ACFTA without rate and DB has no rate → ask-back."""
    # Use a FakeDB that returns no preferential rate for CN/ACFTA
    class FakeDBNoFTA(DatabaseInterface):
        def get_duty_rates(self, hs_code, origin_country, effective_date):
            if origin_country == "XX":
                return {"cd_rate": Decimal("0.15"), "st_rate": Decimal("0.10"), "vat_rate": Decimal("0.10"), "et_rate": Decimal("0"), "atp_rate": Decimal("0.02")}
            return None
        def get_exchange_rate(self, currency_code, effective_date):
            return Decimal("4000")
        def get_hs_code_info(self, hs_code):
            return {"description": "Petroleum", "unit": "ltr"}
        def get_declared_value(self, hs_code, effective_date=None):
            return None
        def check_health(self):
            return {"ok": True, "message": "ok"}
        def search_by_description(self, query):
            return None
        def save_calculation(self, calculation_result):
            return None

    app = create_app()
    app.dependency_overrides[get_db] = lambda: FakeDBNoFTA()
    with TestClient(app) as tc:
        payload = {
            "calculation_date": "2026-03-25",
            "regime": "import",
            "goods": {
                "description": "Diesel",
                "hs_code": "2710.19",
                "origin_country": "CN",
                "net_mass_kg": 10000,
                "volume_liter": 12000,
            },
            "valuation": {"customs_value": 8000, "currency": "USD", "declared_value": 600, "declared_value_basis": "per_ton"},
            "flags": {
                "petroleum_case": True,
                "fta_applicable": True,
                "fta_certificate_type": "ACFTA",
            },
        }
        resp = tc.post("/calculate_import_taxes", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("preferential_rate_missing") is True
        assert body.get("requested_agreement") == "ACFTA"
        assert body["total"] == 0


def test_rubber_with_exemption_returns_ask_back(client: TestClient):
    """Rubber export + diplomatic exemption without rate → ask-back."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "export",
        "goods": {"description": "Natural Rubber", "hs_code": "4001.10", "net_mass_kg": 5000},
        "valuation": {"customs_value": 3000, "currency": "USD"},
        "flags": {
            "rubber_case": True,
            "diplomatic_exemption": True,
        },
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("preferential_rate_missing") is True
    assert body.get("requested_agreement") == "Diplomatic"
    assert body["total"] == 0


def test_fta_dv_dq_with_fta_returns_ask_back(client: TestClient):
    """FTA/DV/DQ case + ATIGA without rate → ask-back."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Steel", "hs_code": "7204", "origin_country": "VN"},
        "valuation": {"customs_value": 20000, "currency": "USD"},
        "flags": {
            "fta_applicable": True,
            "fta_certificate_type": "ATIGA",
            "dq_applicable": True,
            "dq_factor": 0.4,
        },
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("preferential_rate_missing") is True
    assert body.get("requested_agreement") == "ATIGA"
    assert body["total"] == 0


def test_multiple_exemptions_triggers_first(client: TestClient):
    """Both QIP and SEZ claimed → first match in map triggers ask-back."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Equipment", "hs_code": "8471", "origin_country": "XX"},
        "valuation": {"customs_value": 10000, "currency": "USD"},
        "flags": {"qip_exemption": True, "sez_applicable": True},
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("preferential_rate_missing") is True
    # qip_exemption is first in the exemption_map
    assert body.get("requested_agreement") == "QIP"
    assert body["total"] == 0


def test_sez_exemption_returns_ask_back(client: TestClient):
    """SEZ claimed without rate → ask-back."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Equipment", "hs_code": "8471", "origin_country": "XX"},
        "valuation": {"customs_value": 10000, "currency": "USD"},
        "flags": {"sez_applicable": True},
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("preferential_rate_missing") is True
    assert body.get("requested_agreement") == "SEZ"
    assert body["total"] == 0


def test_diplomatic_exemption_returns_ask_back(client: TestClient):
    """Diplomatic exemption claimed without rate → ask-back."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Car", "hs_code": "8703", "origin_country": "XX"},
        "valuation": {"customs_value": 50000, "currency": "USD"},
        "flags": {"diplomatic_exemption": True},
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("preferential_rate_missing") is True
    assert body.get("requested_agreement") == "Diplomatic"
    assert body["total"] == 0


# ================================================================
# Currency Fallback Chain Tests
# ================================================================

def test_currency_explicitly_provided_uses_it(client: TestClient):
    """Explicit currency 'EUR' is used directly; no inference assumptions."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Wine", "hs_code": "2204", "origin_country": "FR"},
        "valuation": {"customs_value": 10000, "currency": "EUR"},
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] > 0
    assumptions = body.get("assumptions", [])
    assert not any("inferred as" in a for a in assumptions)
    assert not any("defaulting to KHR" in a for a in assumptions)


def test_no_currency_infers_from_origin(client: TestClient):
    """No currency provided but origin_country is Thailand → inferred as THB."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Rice", "hs_code": "1006", "origin_country": "Thailand"},
        "valuation": {"customs_value": 5000},  # currency omitted
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assumptions = body.get("assumptions", [])
    assert any("inferred as THB" in a for a in assumptions)
    assert body["total"] > 0


def test_no_currency_no_origin_defaults_khr(client: TestClient):
    """No currency and no origin_country → defaults to KHR."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Rice", "hs_code": "1006"},  # no origin_country
        "valuation": {"customs_value": 5000},  # currency omitted
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assumptions = body.get("assumptions", [])
    assert any("defaulting to KHR" in a for a in assumptions)
    assert body["total"] > 0


def test_garbage_origin_defaults_khr(client: TestClient):
    """No currency and garbage origin_country → defaults to KHR."""
    payload = {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {"description": "Rice", "hs_code": "1006", "origin_country": "XYZ"},
        "valuation": {"customs_value": 5000},  # currency omitted
    }
    resp = client.post("/calculate_import_taxes", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assumptions = body.get("assumptions", [])
    assert any("defaulting to KHR" in a for a in assumptions)
    assert body["total"] > 0


def test_nl_no_currency_infers_from_origin(client: TestClient):
    """NL query with no currency but origin 'Thailand' → endpoint infers THB."""
    resp = client.post("/query", json={"question": "import tax for 847130 from Thailand value 10000"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assumptions = body["result"]["assumptions"]
    assert any("inferred as THB" in a for a in assumptions)


def test_nl_no_currency_no_origin_defaults_khr(client: TestClient):
    """NL query with no currency and no origin → endpoint defaults to KHR."""
    resp = client.post("/query", json={"question": "import tax for 847130 value 10000"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assumptions = body["result"]["assumptions"]
    assert any("defaulting to KHR" in a for a in assumptions)
