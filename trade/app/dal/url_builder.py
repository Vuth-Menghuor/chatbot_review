"""Build DAL query URLs from a DALRequest."""

from __future__ import annotations

import os
from typing import Any, Mapping
from urllib.parse import urlencode

from app.dal.dal_models import DALRequest


class DALUrlBuilder:
    """Build the canonical DAL request URL and headers.

    Matches the DAL spec:
    - path: /v1/query/{dataset}
    - query params: dimensions, measures, version, start-period, end-period,
      period, frequency, repeatable filter, sort, limit, offset
    - header: x-api-key
    """

    def __init__(self, base_url: str, dataset: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.dataset = dataset
        self.api_key = api_key or ""

    @classmethod
    def from_env(cls) -> "DALUrlBuilder":
        return cls(
            base_url=os.getenv("DAL_BASE_URL", "http://localhost:8000"),
            dataset=os.getenv("DAL_DATASET_CODE", "trade_volume"),
            api_key=os.getenv("DAL_API_KEY", ""),
        )

    def build(self, request: DALRequest | Mapping[str, Any]) -> str:
        """Build URL from a DALRequest or dict."""
        if isinstance(request, DALRequest):
            payload = request.model_dump()
        else:
            payload = dict(request)

        query_parts: dict[str, Any] = {}

        dimensions = payload.get("dimensions") or payload.get("group_by")
        if dimensions:
            query_parts["dimensions"] = ",".join(str(item) for item in dimensions if str(item).strip())

        measures = payload.get("metrics")
        if measures:
            query_parts["measures"] = ",".join(str(item) for item in measures if str(item).strip())

        if payload.get("version"):
            version = payload["version"]
            if version == "trade_volume_1.0":
                version = "1.0"
            query_parts["version"] = version
        if payload.get("start_period"):
            query_parts["start-period"] = payload["start_period"]
        if payload.get("end_period"):
            query_parts["end-period"] = payload["end_period"]
        if payload.get("period"):
            query_parts["period"] = payload["period"]
        if payload.get("frequency"):
            query_parts["frequency"] = payload["frequency"]
        if payload.get("sort"):
            query_parts["sort"] = payload["sort"]

        query_parts["limit"] = payload.get("limit", 1000)
        query_parts["offset"] = payload.get("offset", 0)

        filters = self._filters_to_query(payload.get("filters", {}))
        if filters:
            query_parts["filter"] = filters

        return f"{self.base_url}/v1/query/{self.dataset}?{urlencode(query_parts, doseq=True)}"

    def headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _filters_to_query(self, filters: Mapping[str, Any]) -> list[str]:
        """Convert structured filter fields into DAL repeatable filter strings."""
        query_filters: list[str] = []
        ignored_keys = {
            "PERIOD",
            "START_PERIOD",
            "END_PERIOD",
            "FREQUENCY",
            "VERSION",
            "LIMIT",
            "OFFSET",
        }

        # Normalize all keys in filters to uppercase locally
        normalized_filters = {str(k).upper(): v for k, v in filters.items()}

        for key, value in normalized_filters.items():
            if key in ignored_keys:
                continue
            if value is None or value == "":
                continue
            if isinstance(value, (list, tuple, set)):
                valid_items = [str(item) for item in value if item is not None and str(item).strip() != ""]
                if valid_items:
                    query_filters.append(f"{key}:in:{','.join(valid_items)}")
            else:
                query_filters.append(f"{key}:eq:{value}")

        # Ensure FLOW is serialized if present in filters
        if "FLOW" in normalized_filters and normalized_filters["FLOW"]:
            flow_val = normalized_filters["FLOW"]
            flow_eq = f"FLOW:eq:{flow_val}"
            flow_in = "FLOW:in:"
            if not any(f == flow_eq or f.startswith(flow_in) for f in query_filters):
                if isinstance(flow_val, (list, tuple, set)):
                    valid_items = [str(item) for item in flow_val if item is not None and str(item).strip() != ""]
                    if valid_items:
                        query_filters.append(f"FLOW:in:{','.join(valid_items)}")
                else:
                    query_filters.append(f"FLOW:eq:{flow_val}")

        return query_filters
