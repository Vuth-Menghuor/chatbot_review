"""
GDCE Calculator Service - Test Fixtures
========================================
Shared pytest fixtures available across all test modules.

Usage:
    Run from project root:
        pytest services/calculator/tests/ -v

Phase 2 TODO:
    - Add fixture: `test_client` (FastAPI TestClient with create_app())
    - Add fixture: `mock_db` (in-memory DatabaseInterface stub)
    - Add fixture: `sample_request` (typical CalculateImportTaxesRequest dict)
    - Add fixture: `sample_csv_path` (path to test duty_rates.csv subset)
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Placeholder fixtures — will be fleshed out in Phase 2
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_calculation_request() -> dict:
    """A minimal valid calculate_import_taxes request body."""
    return {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {
            "description": "Laptops",
            "hs_code": "8471.30",
            "origin_country": "Thailand",
            "quantity": 10,
            "unit": "unit",
        },
        "valuation": {
            "customs_value": 50000.0,
            "currency": "USD",
        },
        "flags": {
            "fta_applicable": False,
        },
    }


@pytest.fixture
def sample_goods_no_hs_code() -> dict:
    """Request where hs_code is omitted (tests auto-lookup path)."""
    return {
        "calculation_date": "2026-03-25",
        "regime": "import",
        "goods": {
            "description": "Live Oxen",
            "origin_country": "Thailand",
            "quantity": 5,
            "unit": "head",
        },
        "valuation": {
            "customs_value": 25000.0,
            "currency": "USD",
        },
    }
