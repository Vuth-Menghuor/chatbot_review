from typing import Any

from app.services.normalizers.base import BaseNormalizer
from app.services.normalizers.fallback import normalize_service_name
from app.services.normalizers.retrieval.structured import first_structured_retrieval_result


class RetrievalNormalizer(BaseNormalizer):
    """Route retrieval payloads before fallback while preserving existing markdown/citation behavior."""

    def can_handle(self, payload: dict[str, Any]) -> bool:
        service = normalize_service_name(payload.get("service") or payload.get("intent") or payload.get("route"))
        return service == "retrieval" or first_structured_retrieval_result(payload) is not None

    def normalize(self, payload: dict[str, Any]) -> str:
        return normalize_retrieval_response(payload)


# For this MVP, retrieval normalization only identifies the service; block shaping stays contract-compatible.
def normalize_retrieval_response(payload: dict[str, Any]) -> str:
    return "retrieval"
