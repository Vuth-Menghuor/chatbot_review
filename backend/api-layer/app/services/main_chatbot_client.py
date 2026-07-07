from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import settings


class MainChatbotClient:
    def __init__(self) -> None:
        self.base_url = settings.main_service_url

    async def request(self, method: str, path: str, **kwargs) -> Any:
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
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
