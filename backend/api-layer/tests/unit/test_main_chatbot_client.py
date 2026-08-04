from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException

from app.services.main_chatbot_client import MainChatbotClient


# This file protects the shared HTTP-client behavior used for orchestrator calls.


# Build a reusable httpx client with a fake transport instead of calling the real orchestrator.
def mock_async_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# Requests should use the injected shared client and parse JSON responses.
@pytest.mark.asyncio
async def test_request_uses_injected_shared_client():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"answer": "ok"})

    # Inject one client and make two calls to prove the wrapper reuses it.
    shared_client = mock_async_client(handler)
    client = MainChatbotClient()
    client.set_client(shared_client)

    response = await client.request("POST", "/query", json={"question": "hello"})
    second_response = await client.request("GET", "/health")

    assert response == {"answer": "ok"}
    assert second_response == {"answer": "ok"}
    assert len(calls) == 2
    assert calls[0].url.path == "/query"
    assert calls[1].url.path == "/health"

    # Closing the wrapper should close the injected shared client.
    await client.aclose()
    assert shared_client.is_closed


# A 204 response should return None instead of trying to decode JSON.
@pytest.mark.asyncio
async def test_request_returns_none_for_204_response():
    shared_client = mock_async_client(lambda _request: httpx.Response(204))
    client = MainChatbotClient()
    client.set_client(shared_client)

    assert await client.request("DELETE", "/internal/chats/chat-1") is None

    await client.aclose()


# Upstream HTTP errors should become FastAPI HTTPException with the upstream status code.
@pytest.mark.asyncio
async def test_request_maps_upstream_http_error_to_http_exception():
    shared_client = mock_async_client(lambda _request: httpx.Response(502, json={"detail": "bad gateway"}))
    client = MainChatbotClient()
    client.set_client(shared_client)

    with pytest.raises(HTTPException) as exc_info:
        await client.request("GET", "/query")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "bad gateway"

    await client.aclose()
