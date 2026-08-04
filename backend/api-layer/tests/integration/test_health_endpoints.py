from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.api.v1.endpoints import health as health_endpoint
from app.main import app


# This file verifies health routes while replacing external DB/Redis/HTTP dependencies.


# Minimal DB connection fake for the health endpoint's SELECT 1 check.
class FakeDb:
    # The endpoint only needs execute() to complete without error.
    async def execute(self, _statement):
        return None


# Async context manager that behaves like SessionLocal().
class FakeSessionContext:
    # Let each test choose whether database acquisition should fail.
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    # Return a fake DB session or raise to simulate database outage.
    async def __aenter__(self):
        if self.fail:
            raise RuntimeError("database unavailable")
        return FakeDb()

    # Do not suppress exceptions from the tested code.
    async def __aexit__(self, exc_type, exc, tb):
        return False


# Minimal Redis fake for the health endpoint's ping check.
class FakeRedis:
    # Let each test choose whether Redis should fail.
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    # Simulate Redis ping success or failure.
    async def ping(self):
        if self.fail:
            raise RuntimeError("redis unavailable")
        return True


# Minimal HTTP response fake for the orchestrator health check.
class FakeResponse:
    # Let the fake response raise like httpx does for non-2xx status codes.
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    # Match the httpx.Response API used by the endpoint.
    def raise_for_status(self):
        if self.fail:
            raise httpx.HTTPStatusError("bad upstream", request=httpx.Request("GET", "http://test"), response=httpx.Response(503))


# Async client fake so the test does not call the real orchestrator service.
class FakeAsyncClient:
    fail = False

    # Accept the same constructor shape as httpx.AsyncClient.
    def __init__(self, *args, **kwargs) -> None:
        pass

    # Support async with httpx.AsyncClient(...).
    async def __aenter__(self):
        return self

    # Do not suppress exceptions from the endpoint.
    async def __aexit__(self, exc_type, exc, tb):
        return False

    # Return a fake response for the orchestrator /health request.
    async def get(self, _url):
        return FakeResponse(fail=self.fail)


# Request logging is tested elsewhere; this keeps health tests from writing logs to Postgres.
async def noop_save_api_request_log(**_kwargs):
    return None


# Apply the no-op request logger to every test in this file.
@pytest.fixture(autouse=True)
def disable_request_log_db_write(monkeypatch):
    monkeypatch.setattr("app.middleware.request_log_middleware.save_api_request_log", noop_save_api_request_log)


# Liveness should not check dependencies; it only proves the API process can respond.
@pytest.mark.asyncio
async def test_live_endpoint_reports_process_is_alive(monkeypatch):
    monkeypatch.setattr(health_endpoint, "SessionLocal", lambda: FakeSessionContext(fail=True))
    monkeypatch.setattr(health_endpoint, "redis_client", FakeRedis(fail=True))
    FakeAsyncClient.fail = True
    monkeypatch.setattr(health_endpoint, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# When all dependencies respond, readiness should allow this instance to receive traffic.
@pytest.mark.asyncio
async def test_ready_endpoint_reports_ready_when_dependencies_are_available(monkeypatch):
    monkeypatch.setattr(health_endpoint, "SessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr(health_endpoint, "redis_client", FakeRedis())
    FakeAsyncClient.fail = False
    monkeypatch.setattr(health_endpoint, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {
            "postgres": "up",
            "redis": "up",
            "orchestrator": "up",
        },
    }


# Readiness should return 503 when dependencies fail so load balancers stop sending traffic.
@pytest.mark.asyncio
async def test_ready_endpoint_returns_503_when_dependencies_are_unavailable(monkeypatch):
    monkeypatch.setattr(health_endpoint, "SessionLocal", lambda: FakeSessionContext(fail=True))
    monkeypatch.setattr(health_endpoint, "redis_client", FakeRedis(fail=True))
    FakeAsyncClient.fail = True
    monkeypatch.setattr(health_endpoint, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {
            "postgres": "down",
            "redis": "down",
            "orchestrator": "down",
        },
    }


# Legacy /health stays available for current scripts while /live and /ready become the preferred checks.
@pytest.mark.asyncio
async def test_legacy_health_endpoint_reports_degraded_without_503(monkeypatch):
    monkeypatch.setattr(health_endpoint, "SessionLocal", lambda: FakeSessionContext(fail=True))
    monkeypatch.setattr(health_endpoint, "redis_client", FakeRedis(fail=True))
    FakeAsyncClient.fail = True
    monkeypatch.setattr(health_endpoint, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "database": "unavailable",
        "redis": "unavailable",
        "main_chatbot_service": "unavailable",
    }
