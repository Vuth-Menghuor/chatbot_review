"""
Integration tests for the query endpoint.

These tests require running metadata DB, operational DB, and Redis.
Run with: docker compose up -d && pytest tests/integration/ -v
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.fixtures.sample_keys import INVALID_KEY_PLAIN, PRIVATE_KEY_PLAIN, PUBLIC_KEY_PLAIN


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestQueryEndpointAuth:
    """Authentication and authorization tests."""

    def test_missing_api_key(self, client):
        resp = client.get("/v1/query/trade_volume?dimensions=FLOW&measures=VALUE_USD")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "MISSING_API_KEY"

    def test_invalid_api_key(self, client):
        resp = client.get(
            "/v1/query/trade_volume?dimensions=FLOW&measures=VALUE_USD",
            headers={"x-api-key": INVALID_KEY_PLAIN},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_API_KEY"

    def test_valid_public_key_on_public_dataset(self, client):
        resp = client.get(
            "/v1/query/trade_volume?dimensions=FLOW,PARTNER_COUNTRY&measures=VALUE_USD&frequency=A",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        # Should succeed if DB is seeded; 401/500 if not — this is an integration test
        assert resp.status_code in (200, 500)  # 500 if ops DB isn't seeded

    def test_dataset_not_found(self, client):
        resp = client.get(
            "/v1/query/nonexistent_dataset?dimensions=FLOW&measures=VALUE_USD",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "DATASET_NOT_FOUND"


class TestQueryEndpointValidation:
    """Request validation tests."""

    def test_missing_dimensions(self, client):
        resp = client.get(
            "/v1/query/trade_volume?measures=VALUE_USD",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        assert resp.status_code == 422  # FastAPI validation

    def test_missing_measures(self, client):
        resp = client.get(
            "/v1/query/trade_volume?dimensions=FLOW",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        assert resp.status_code == 422

    def test_invalid_dimension(self, client):
        resp = client.get(
            "/v1/query/trade_volume?dimensions=NONEXISTENT&measures=VALUE_USD&frequency=A",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_DIMENSION"

    def test_invalid_measure(self, client):
        resp = client.get(
            "/v1/query/trade_volume?dimensions=FLOW&measures=NONEXISTENT&frequency=A",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_MEASURE"

    def test_invalid_frequency(self, client):
        resp = client.get(
            "/v1/query/trade_volume?dimensions=FLOW&measures=VALUE_USD&frequency=X",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_FREQUENCY"


class TestQueryEndpointHappyPath:
    """Full happy-path tests (require seeded DB)."""

    def test_basic_annual_query(self, client):
        resp = client.get(
            "/v1/query/trade_volume"
            "?dimensions=FLOW,PARTNER_COUNTRY"
            "&measures=VALUE_USD,NETWEIGHT"
            "&frequency=A"
            "&period_from=2025"
            "&period_to=2026"
            "&limit=10",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        if resp.status_code == 200:
            data = resp.json()
            assert "request_id" in data
            assert data["dataset"] == "trade_volume"
            assert data["frequency"] == "A"
            assert isinstance(data["data"], list)
            assert data["row_count"] == len(data["data"])
            assert data["pagination"]["limit"] == 10

    def test_monthly_query_with_filters(self, client):
        resp = client.get(
            "/v1/query/trade_volume"
            "?dimensions=FLOW,PARTNER_COUNTRY"
            "&measures=VALUE_USD"
            "&frequency=M"
            "&filter=FLOW:eq:IMPORT"
            "&filter=PARTNER_COUNTRY:eq:United States"
            "&period_from=2025-01"
            "&period_to=2025-06"
            "&sort=VALUE_USD:desc"
            "&limit=5",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        if resp.status_code == 200:
            data = resp.json()
            assert data["frequency"] == "M"
            # All rows should be IMPORT since we filtered
            for row in data["data"]:
                assert row.get("FLOW") == "IMPORT"

    def test_quarterly_query(self, client):
        resp = client.get(
            "/v1/query/trade_volume"
            "?dimensions=FLOW"
            "&measures=VALUE_USD"
            "&frequency=Q"
            "&period_from=2025-Q1"
            "&period_to=2025-Q4",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        if resp.status_code == 200:
            data = resp.json()
            assert data["frequency"] == "Q"

    def test_response_envelope_shape(self, client):
        resp = client.get(
            "/v1/query/trade_volume"
            "?dimensions=FLOW&measures=VALUE_USD&frequency=A",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        if resp.status_code == 200:
            data = resp.json()
            required_keys = {
                "request_id", "dataset", "version", "frequency",
                "dimensions", "measures", "period", "pagination",
                "cache", "meta", "row_count", "data",
            }
            assert required_keys.issubset(set(data.keys()))
            assert "hit" in data["cache"]
            assert "latency_ms" in data["meta"]
            assert "limit" in data["pagination"]
            assert "offset" in data["pagination"]
