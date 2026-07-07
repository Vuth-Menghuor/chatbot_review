from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app, raise_server_exceptions=False)


def test_validation_error_returns_structured_response():
    response = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "short"})
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "validation_error"
    assert body["detail"] == "Request validation failed"
    assert body["request_id"]
    assert response.headers.get("X-Request-ID") == body["request_id"]
    assert body["errors"]


def test_not_found_returns_structured_response():
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "not_found"
    assert body["request_id"]


@pytest.mark.asyncio
async def test_http_exception_sets_error_detail_on_request_state():
    from app.core.exception_handlers import http_exception_handler
    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "path": "/test", "headers": [], "query_string": b""}
    request = Request(scope)
    request.state.request_id = "req-123"

    response = await http_exception_handler(request, HTTPException(status_code=401, detail="Authentication required"))
    assert response.status_code == 401
    assert request.state.error_detail == "Authentication required"


@pytest.mark.asyncio
async def test_enforce_rate_limit_logs_when_blocked():
    from app.services.rate_limit_service import enforce_rate_limit

    with patch("app.services.rate_limit_service.redis_client") as redis_mock, patch(
        "app.services.rate_limit_service.save_rate_limit_log", new_callable=AsyncMock
    ) as save_mock:
        redis_mock.incr = AsyncMock(return_value=6)
        redis_mock.expire = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await enforce_rate_limit("login:127.0.0.1", 5)

        assert exc.value.status_code == 429
        save_mock.assert_awaited_once()
