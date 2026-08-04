from typing import Any

from app.services.normalizers.base import BaseNormalizer
from app.services.normalizers.fallback import normalize_service_name
from app.services.normalizers.trade.structured import first_structured_trade_result


class TradeNormalizer(BaseNormalizer):
    """Route structured trade payloads before the generic fallback handles plain service labels."""

    def can_handle(self, payload: dict[str, Any]) -> bool:
        service = normalize_service_name(payload.get("service") or payload.get("intent") or payload.get("route"))
        return service == "trade" or first_structured_trade_result(payload) is not None

    def normalize(self, payload: dict[str, Any]) -> str:
        return normalize_trade_response(payload)


# For this MVP, the registry output remains the service label while block creation stays in the chat normalizer.
def normalize_trade_response(payload: dict[str, Any]) -> str:
    return "trade"
