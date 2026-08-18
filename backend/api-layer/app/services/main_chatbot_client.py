from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import json
import httpx
from fastapi import HTTPException

from app.core.config import settings

DEFAULT_CHAT_STREAM_PATH = "/query/stream"


@dataclass(frozen=True)
class ChatStreamEvent:
    type: str
    content: str | None = None
    data: dict[str, Any] | None = None


class MainChatbotClient:
    def __init__(self) -> None:
        self.base_url = settings.main_service_url
        self._client: httpx.AsyncClient | None = None

    # FastAPI lifespan injects the shared client here so requests do not create new connections.
    def set_client(self, client: httpx.AsyncClient) -> None:
        self._client = client

    # Shutdown closes the shared/fallback client and clears the reference for clean restarts/tests.
    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
        self._client = None

    # Provide a fallback client for direct service tests or scripts that do not run FastAPI lifespan.
    async def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=5.0,
                    read=settings.http_timeout_seconds,
                    write=10.0,
                    pool=5.0,
                ),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._client

    # Centralize orchestrator request execution and convert upstream failures to API errors.
    async def request(self, method: str, path: str, **kwargs) -> Any:
        try:
            client = await self.client()
            response = await client.request(method, f"{self.base_url}{path}", **kwargs)
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = "Main Chatbot Service request failed"
            try:
                detail = exc.response.json().get("detail", detail)
            except Exception:
                pass
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Main Chatbot Service is temporarily unavailable") from exc

    async def stream_sse(self, method: str, path: str, **kwargs) -> AsyncIterator[str]:
        decoder = SSETextDecoder()
        buffer = ""
        async for chunk in self.stream(method, path, **kwargs):
            buffer += decoder.decode(chunk).replace("\r\n", "\n")
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                if block.strip():
                    yield block
        buffer += decoder.flush()
        if buffer.strip():
            yield buffer

    async def stream_chat(
        self,
        body: dict[str, Any],
        *,
        path: str = DEFAULT_CHAT_STREAM_PATH,
    ) -> AsyncIterator[ChatStreamEvent]:
        async for block in self.stream_sse("POST", path, json=body):
            event = parse_orchestrator_sse_block(block)
            if event:
                yield event

    async def stream(self, method: str, path: str, **kwargs) -> AsyncIterator[bytes]:
        client = await self.client()
        async with client.stream(method, f"{self.base_url}{path}", **kwargs) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk


class SSETextDecoder:
    def __init__(self) -> None:
        import codecs

        self._decoder = codecs.getincrementaldecoder("utf-8")()

    def decode(self, chunk: bytes) -> str:
        return self._decoder.decode(chunk)

    def flush(self) -> str:
        return self._decoder.decode(b"", final=True)


def parse_orchestrator_sse_block(block: str) -> ChatStreamEvent | None:
    if not block.strip() or block.lstrip().startswith(":"):
        return None

    event = "message"
    data_lines: list[str] = []
    for line in block.split("\n"):
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if not data_lines:
        return None

    try:
        data = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        data = {"content": "\n".join(data_lines)}

    if event == "start" and isinstance(data, dict):
        return ChatStreamEvent(type="progress", data={"stage": "start", **data})

    if isinstance(data, dict) and event in {"message", "delta"}:
        content = first_present_text(data, "content", "delta", "text", "chunk")
        if content:
            return ChatStreamEvent(type="delta", content=content)
        return None

    if event == "progress" and isinstance(data, dict):
        return ChatStreamEvent(type="progress", data=data)

    if event == "done" and isinstance(data, dict):
        return ChatStreamEvent(type="done", data=data)

    if event == "error" and isinstance(data, dict):
        detail = data.get("detail") or data.get("error") or "Chat stream failed"
        return ChatStreamEvent(type="error", data={"detail": str(detail)})

    if event == "clarification" and isinstance(data, dict):
        return ChatStreamEvent(type="clarification", data=data)

    return None


def first_present_text(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value
    return None


main_chatbot_client = MainChatbotClient()
