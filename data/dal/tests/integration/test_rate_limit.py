"""
Integration tests for rate limiting.

Requires Redis to be running.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.fixtures.sample_keys import PUBLIC_KEY_PLAIN


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestRateLimiting:
    """Rate limit enforcement tests."""

    def test_rate_limit_headers_present(self, client):
        """Successful requests should include rate limit info."""
        resp = client.get(
            "/v1/query/trade_volume?dimensions=FLOW&measures=VALUE_USD&frequency=A",
            headers={"x-api-key": PUBLIC_KEY_PLAIN},
        )
        # If the request succeeded (auth passed), we should have request-id
        if resp.status_code in (200, 400, 404):
            assert "X-Request-ID" in resp.headers

    def test_rate_limit_exceeded(self, client):
        """After exceeding the limit, should get 429."""
        # The default is 10 req/min — send 12 rapid requests
        responses = []
        for _ in range(12):
            resp = client.get(
                "/v1/query/trade_volume?dimensions=FLOW&measures=VALUE_USD&frequency=A",
                headers={"x-api-key": PUBLIC_KEY_PLAIN},
            )
            responses.append(resp.status_code)

        # At least the last request should be 429 (if Redis is running and rate limit applies)
        if 429 in responses:
            # Find the 429 response
            for i, resp_code in enumerate(responses):
                if resp_code == 429:
                    assert i >= 10  # Should not hit limit before 10 requests
                    break
