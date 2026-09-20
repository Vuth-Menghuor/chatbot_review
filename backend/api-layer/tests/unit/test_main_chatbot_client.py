from __future__ import annotations

import asyncio

import httpx
from fastapi import HTTPException
import pytest

from app.services.main_chatbot_client import MainChatbotClient


# This file protects the shared HTTP-client behavior used for orchestrator calls.


# Build a reusable httpx client with a fake transport instead of calling the real orchestrator.
def mock_async_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class ChunkedAsyncStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


# Requests should use the injected shared client and parse JSON responses.
def test_request_uses_injected_shared_client():
    asyncio.run(_request_uses_injected_shared_client())


async def _request_uses_injected_shared_client():
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
def test_request_returns_none_for_204_response():
    asyncio.run(_request_returns_none_for_204_response())


async def _request_returns_none_for_204_response():
    shared_client = mock_async_client(lambda _request: httpx.Response(204))
    client = MainChatbotClient()
    client.set_client(shared_client)

    assert await client.request("DELETE", "/internal/chats/chat-1") is None

    await client.aclose()


# Upstream HTTP errors should become FastAPI HTTPException with the upstream status code.
def test_request_maps_upstream_http_error_to_http_exception():
    asyncio.run(_request_maps_upstream_http_error_to_http_exception())


async def _request_maps_upstream_http_error_to_http_exception():
    shared_client = mock_async_client(lambda _request: httpx.Response(502, json={"detail": "bad gateway"}))
    client = MainChatbotClient()
    client.set_client(shared_client)

    with pytest.raises(HTTPException) as exc_info:
        await client.request("GET", "/query")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "bad gateway"

    await client.aclose()


def test_stream_sse_yields_complete_sse_blocks_without_parsing_payloads():
    asyncio.run(_stream_sse_yields_complete_sse_blocks_without_parsing_payloads())


async def _stream_sse_yields_complete_sse_blocks_without_parsing_payloads():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/query/stream"
        return httpx.Response(
            200,
            stream=ChunkedAsyncStream([
                b"event: delta\r\n",
                b'data: {"content":"hel"}\r\n\r\nevent: done\n',
                b'data: {"answer":"hello"}\n\n',
            ]),
            headers={"content-type": "text/event-stream"},
        )

    shared_client = mock_async_client(handler)
    client = MainChatbotClient()
    client.set_client(shared_client)

    blocks = [block async for block in client.stream_sse("POST", "/query/stream", json={"question": "hello"})]

    assert blocks == [
        'event: delta\ndata: {"content":"hel"}',
        'event: done\ndata: {"answer":"hello"}',
    ]

    await client.aclose()


def test_stream_yields_upstream_bytes_without_decoding_or_buffering_response():
    asyncio.run(_stream_yields_upstream_bytes_without_decoding_or_buffering_response())


async def _stream_yields_upstream_bytes_without_decoding_or_buffering_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/query/stream"
        return httpx.Response(
            200,
            stream=ChunkedAsyncStream([b"event: delta\n", b'data: {"content":"hi"}\n\n']),
            headers={"content-type": "text/event-stream"},
        )

    shared_client = mock_async_client(handler)
    client = MainChatbotClient()
    client.set_client(shared_client)

    chunks = [chunk async for chunk in client.stream("POST", "/query/stream", json={"question": "hello"})]

    assert chunks == [b"event: delta\n", b'data: {"content":"hi"}\n\n']

    await client.aclose()


def test_stream_chat_parses_upstream_sse_into_typed_events():
    asyncio.run(_stream_chat_parses_upstream_sse_into_typed_events())


async def _stream_chat_parses_upstream_sse_into_typed_events():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/query/stream"
        return httpx.Response(
            200,
            stream=ChunkedAsyncStream([
                b'event: start\ndata: {"request_id":"upstream"}\n\n',
                b'event: delta\ndata: {"content":""}\n\n',
                b'event: delta\ndata: {"content":"The "}\n\n',
                b'data: {"chunk":""}\n\n',
                b'data: {"chunk":"answer "}\n\n',
                b'event: delta\ndata: {"content":{"type":"table"}}\n\n',
                b'event: clarification\ndata: {"questions":["Which product?"]}\n\n',
                b'event: done\ndata: {"request_id":"upstream","answer":"The answer."}\n\n',
            ]),
            headers={"content-type": "text/event-stream"},
        )

    shared_client = mock_async_client(handler)
    client = MainChatbotClient()
    client.set_client(shared_client)

    events = [event async for event in client.stream_chat({"question": "hello"})]

    assert [(event.type, event.content, event.data) for event in events] == [
        ("progress", None, {"stage": "start", "request_id": "upstream"}),
        ("delta", "The ", None),
        ("delta", "answer ", None),
        ("clarification", None, {"questions": ["Which product?"]}),
        ("done", None, {"request_id": "upstream", "answer": "The answer."}),
    ]

    await client.aclose()
