"""Base handler that executes intent strategies via the DAL."""

from __future__ import annotations

from typing import Any

from ..dal import DALClient, DALRequestBuilder
from ..core.exceptions import UnknownIntentError
from .registry import HandlerRegistry
from .strategies import IntentStrategy
from .mixins import resolve_period_range, resolve_limit


class BaseHandler:
    """Applies an intent strategy to build and execute a DAL request."""

    def __init__(
        self,
        dal_client: DALClient | None = None,
        request_builder: DALRequestBuilder | None = None,
    ) -> None:
        self.dal_client = dal_client or DALClient.from_env()
        self.request_builder = request_builder or DALRequestBuilder()

    def handle(self, intent: str, params: dict[str, Any]) -> dict[str, Any]:
        """Resolve strategy, build DAL request, execute, and return raw response."""
        strategy = HandlerRegistry.get(intent)

        # Merge strategy defaults into params
        merged = self._merge_strategy_defaults(params, strategy)

        # Build DAL request
        request = self.request_builder.build_request(intent, merged)

        # Execute
        response = self.dal_client.execute(request)
        return response

    def _merge_strategy_defaults(self, params: dict[str, Any], strategy: IntentStrategy) -> dict[str, Any]:
        merged = dict(params)

        # Metrics
        if not merged.get("metrics"):
            merged["metrics"] = strategy.default_metrics

        # Group by / dimensions
        if not merged.get("group_by"):
            merged["group_by"] = strategy.default_group_by
        if not merged.get("dimensions"):
            merged["dimensions"] = strategy.default_dimensions

        # Sort
        if not merged.get("sort") and not merged.get("sort_metric") and strategy.default_sort:
            sort_order = merged.get("sort_order")
            if sort_order:
                metric = strategy.default_sort.split(":")[0]
                merged["sort"] = f"{metric}:{sort_order}"
            else:
                merged["sort"] = strategy.default_sort

        # Limit
        merged["limit"] = resolve_limit(merged, strategy)

        # Period / frequency
        period, start_period, end_period, resolved_freq = resolve_period_range(merged)
        if period:
            merged["period"] = period
        if start_period:
            merged["start_period"] = start_period
        if end_period:
            merged["end_period"] = end_period

        # Priority: explicit user frequency > strategy default > resolved
        if merged.get("frequency"):
            pass  # keep explicit user-supplied frequency
        elif strategy.default_frequency:
            merged["frequency"] = strategy.default_frequency
        elif resolved_freq:
            merged["frequency"] = resolved_freq

        return merged
