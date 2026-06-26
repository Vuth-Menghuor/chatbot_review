"""Thin HTTP client for DAL."""

from __future__ import annotations

import os
from typing import Any, Mapping

import httpx

from dal.dal_models import DALRequest
from dal.url_builder import DALUrlBuilder
from dal.exceptions import DALError


class DALClient:
    """Send requests to DAL and return the raw JSON response."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        dataset: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("DAL_BASE_URL", "http://localhost:8000")).rstrip("/")
        self.api_key = api_key or os.getenv("DAL_API_KEY", "")
        self.dataset = dataset or os.getenv("DAL_DATASET_CODE", "trade_volume")
        self.timeout = timeout
        self._url_builder = DALUrlBuilder(self.base_url, self.dataset, self.api_key)

    @classmethod
    def from_env(cls, timeout: float = 20.0) -> "DALClient":
        return cls(timeout=timeout)

    def execute(self, payload: DALRequest | dict[str, Any]) -> dict[str, Any]:
        request = payload if isinstance(payload, DALRequest) else DALRequest.model_validate(payload)
        url = self._url_builder.build(request)
        headers = self._url_builder.headers()

        import time
        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries + 1):
            try:
                response = httpx.get(url, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    data = {"records": data if isinstance(data, list) else [data]}
                data.setdefault("metadata", {})
                data["metadata"]["dal_source_url"] = url
                return data
            except httpx.TimeoutException as exc:
                if attempt == max_retries:
                    raise DALError(f"DAL request timed out after {self.timeout} seconds", status_code=504) from exc
                time.sleep(backoff)
                backoff *= 2.0
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else 500
                if status == 429 and attempt < max_retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise DALError(f"DAL request failed with HTTP {status}", status_code=status) from exc
            except httpx.RequestError as exc:
                if attempt == max_retries:
                    raise DALError(f"DAL request failed: {exc}", status_code=502) from exc
                time.sleep(backoff)
                backoff *= 2.0
