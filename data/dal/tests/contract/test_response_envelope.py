"""Contract tests for response envelopes and OpenAPI schema."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestErrorEnvelope:
    def test_missing_api_key_envelope(self, client):
        resp = client.get("/v1/query/trade_volume?dimensions=FLOW&measures=VALUE_USD")
        data = resp.json()
        assert "request_id" in data
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

    def test_error_code_is_string(self, client):
        resp = client.get("/v1/query/trade_volume?dimensions=FLOW&measures=VALUE_USD")
        assert isinstance(resp.json()["error"]["code"], str)


class TestOpenAPISchema:
    def test_openapi_json_accessible(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        assert "openapi" in resp.json()

    def test_query_endpoint_in_schema(self, client):
        schema = client.get("/openapi.json").json()
        assert any("query" in p and "{dataset}" in p for p in schema["paths"])

    def test_health_endpoints_in_schema(self, client):
        paths = list(client.get("/openapi.json").json()["paths"].keys())
        assert "/health/live" in paths
        assert "/health/ready" in paths

    def test_docs_accessible(self, client):
        assert client.get("/docs").status_code == 200
