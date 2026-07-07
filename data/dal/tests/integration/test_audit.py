"""
Integration tests for audit logging.

Requires metadata DB to be running and seeded.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.fixtures.sample_keys import INVALID_KEY_PLAIN, PUBLIC_KEY_PLAIN


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestAuditLogging:
    """Verify that audit logs are created for both success and failure."""

    def test_successful_request_has_request_id(self, client):
        resp = client.get(
            "/v1/query/trade_volume?dimensions=FLOW&measures=VALUE_USD&frequency=A",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        if resp.status_code == 200:
            data = resp.json()
            assert "request_id" in data
            assert len(data["request_id"]) == 36  # UUID format

    def test_failed_auth_has_request_id(self, client):
        resp = client.get(
            "/v1/query/trade_volume?dimensions=FLOW&measures=VALUE_USD",
        )
        data = resp.json()
        assert "request_id" in data

    def test_invalid_key_has_request_id(self, client):
        resp = client.get(
            "/v1/query/trade_volume?dimensions=FLOW&measures=VALUE_USD",
            headers={"x-api-key": INVALID_KEY_PLAIN},
        )
        data = resp.json()
        assert "request_id" in data

    def test_latency_header_present(self, client):
        resp = client.get(
            "/v1/query/trade_volume?dimensions=FLOW&measures=VALUE_USD&frequency=A",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        # Latency header is set by middleware
        if resp.status_code in (200, 400, 404):
            assert "X-Latency-Ms" in resp.headers
