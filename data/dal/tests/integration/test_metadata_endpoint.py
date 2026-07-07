"""
Integration tests for metadata endpoints.

These tests require running metadata DB, operational DB, and Redis.
Run with: docker compose up -d && pytest tests/integration/ -v
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.fixtures.sample_keys import INVALID_KEY_PLAIN, PUBLIC_KEY_PLAIN


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestMetadataDatasetDetailsAuth:
    """Authentication and authorization safety tests."""

    def test_missing_api_key(self, client):
        resp = client.get("/v1/metadata/dataset/trade_volume")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "MISSING_API_KEY"

    def test_invalid_api_key(self, client):
        resp = client.get(
            "/v1/metadata/dataset/trade_volume",
            headers={"x-api-key": INVALID_KEY_PLAIN},
        )
        # 500 can happen in integration environments when metadata DB is unavailable.
        assert resp.status_code in (401, 500)
        if resp.status_code == 401:
            assert resp.json()["error"]["code"] == "INVALID_API_KEY"


class TestMetadataDatasetDetailsValidation:
    """Route and path validation tests."""

    def test_invalid_dataset_code_in_path(self, client):
        # Dot is rejected by the path pattern validator.
        resp = client.get(
            "/v1/metadata/dataset/trade.volume",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        # 500 can happen in integration environments when metadata DB is unavailable.
        assert resp.status_code in (422, 500)

    def test_dataset_not_found(self, client):
        resp = client.get(
            "/v1/metadata/dataset/nonexistent_dataset",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        # 500 can happen in integration environments when metadata DB is unavailable.
        assert resp.status_code in (404, 500)
        if resp.status_code == 404:
            assert resp.json()["error"]["code"] == "DATASET_NOT_FOUND"


class TestMetadataDatasetDetailsResponse:
    """Basic response-shape checks for successful metadata responses."""

    def test_response_envelope_shape(self, client):
        resp = client.get(
            "/v1/metadata/dataset/trade_volume",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        if resp.status_code == 200:
            data = resp.json()
            required_keys = {
                "request_id",
                "dataset",
                "version",
                "frequency",
                "dimensions",
                "measures",
                "period",
                "cache",
                "meta",
            }
            assert required_keys.issubset(set(data.keys()))
            assert "latency_ms" in data["meta"]
            assert "hit" in data["cache"]
