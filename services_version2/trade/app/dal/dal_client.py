"""Thin HTTP client for DAL."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.core.countries import ASEAN_MEMBER_CODES, EU_MEMBER_CODES
from app.dal.dal_models import DALRequest
from app.dal.exceptions import DALError
from app.dal.url_builder import DALUrlBuilder


class DALClient:
    """Send requests to DAL and return the raw JSON response."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        dataset: str | None = None,
        timeout: float | None = None,
    ) -> None:
        from app.core.config import get_settings
        settings = get_settings()
        self.base_url = (base_url or os.getenv("DAL_BASE_URL", "http://localhost:8000")).rstrip("/")
        self.api_key = api_key or os.getenv("DAL_API_KEY", "")
        self.dataset = dataset or os.getenv("DAL_DATASET_CODE", "trade_volume")
        self.timeout = timeout if timeout is not None else settings.dal_timeout
        self.max_retries = settings.dal_max_retries
        self.backoff = settings.dal_backoff
        self._url_builder = DALUrlBuilder(self.base_url, self.dataset, self.api_key)

    @classmethod
    def from_env(cls, timeout: float | None = None) -> "DALClient":
        return cls(timeout=timeout)

    def execute(self, payload: DALRequest | dict[str, Any]) -> dict[str, Any]:
        request = payload if isinstance(payload, DALRequest) else DALRequest.model_validate(payload)

        # Expand regional codes (EU/ASEAN) to list of member countries
        # to ensure the database can query them.
        import copy
        REGIONAL_EXPANSIONS = {
            "EU": list(EU_MEMBER_CODES),  # EU_MEMBER_CODES is an ordered tuple; list() preserves order exactly
            "ASEAN": list(ASEAN_MEMBER_CODES),
        }

        request_copy = copy.deepcopy(request)
        if "PARTNER_COUNTRY" in request_copy.filters:
            val = request_copy.filters["PARTNER_COUNTRY"]
            if isinstance(val, str) and val.upper() in REGIONAL_EXPANSIONS:
                request_copy.filters["PARTNER_COUNTRY"] = REGIONAL_EXPANSIONS[val.upper()]
            elif isinstance(val, list):
                new_list = []
                for item in val:
                    if str(item).upper() in REGIONAL_EXPANSIONS:
                        new_list.extend(REGIONAL_EXPANSIONS[str(item).upper()])
                    else:
                        new_list.append(item)
                request_copy.filters["PARTNER_COUNTRY"] = new_list

        url = self._url_builder.build(request_copy)
        headers = self._url_builder.headers()

        import time
        max_retries = self.max_retries
        backoff = self.backoff

        for attempt in range(max_retries + 1):
            try:
                response = httpx.get(url, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    data = {"records": data if isinstance(data, list) else [data]}
                elif "data" in data and "records" not in data:
                    data["records"] = data["data"]
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
