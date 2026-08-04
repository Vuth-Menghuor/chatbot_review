from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services import rate_limit_service


# This fake isolates rate-limit behavior from a live Redis server.
class FakeRedis:
    # Let each test choose between normal Redis behavior and simulated Redis failure.
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.counts: dict[str, int] = {}
        self.expired: list[tuple[str, int]] = []

    # Simulate Redis INCR because the service uses it as the request counter.
    async def incr(self, key: str) -> int:
        if self.fail:
            raise RuntimeError("redis unavailable")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    # Capture expiry calls so tests can verify the rate-limit window is set.
    async def expire(self, key: str, window_seconds: int) -> None:
        self.expired.append((key, window_seconds))


# Requests under the limit should pass and initialize the Redis expiry window.
@pytest.mark.asyncio
async def test_enforce_rate_limit_allows_requests_under_limit(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(rate_limit_service, "redis_client", redis)

    await rate_limit_service.enforce_rate_limit("chat:user-1", limit=2, window_seconds=30)
    await rate_limit_service.enforce_rate_limit("chat:user-1", limit=2, window_seconds=30)

    assert redis.counts["rate_limit:chat:user-1"] == 2
    assert redis.expired == [("rate_limit:chat:user-1", 30)]


# Requests over the limit should raise 429 and persist a blocked rate-limit log.
@pytest.mark.asyncio
async def test_enforce_rate_limit_blocks_and_logs_when_limit_exceeded(monkeypatch):
    redis = FakeRedis()
    logged_payloads = []

    # Capture the log payload instead of writing to the database.
    async def fake_save_rate_limit_log(**kwargs):
        logged_payloads.append(kwargs)

    monkeypatch.setattr(rate_limit_service, "redis_client", redis)
    monkeypatch.setattr(rate_limit_service, "save_rate_limit_log", fake_save_rate_limit_log)

    await rate_limit_service.enforce_rate_limit("chat:user-1", limit=1)
    with pytest.raises(HTTPException) as exc_info:
        await rate_limit_service.enforce_rate_limit("chat:user-1", limit=1)

    assert exc_info.value.status_code == 429
    assert logged_payloads[0]["limit_key"] == "chat:user-1"
    assert logged_payloads[0]["request_count"] == 2
    assert logged_payloads[0]["blocked"] is True


# Redis outages should not take down the API, so the limiter intentionally fails open.
@pytest.mark.asyncio
async def test_enforce_rate_limit_fails_open_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr(rate_limit_service, "redis_client", FakeRedis(fail=True))

    await rate_limit_service.enforce_rate_limit("chat:user-1", limit=0)
