from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import settings


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


main_chatbot_client = MainChatbotClient()
