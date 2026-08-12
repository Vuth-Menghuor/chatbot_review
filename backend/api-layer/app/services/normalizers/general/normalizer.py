from typing import Any

from app.services.normalizers.base import BaseNormalizer
from app.services.normalizers.fallback import normalize_service_name


class GeneralNormalizer(BaseNormalizer):
    """Route general chatbot payloads while leaving orchestrator answer content unchanged."""

    def can_handle(self, payload: dict[str, Any]) -> bool:
        service = normalize_service_name(payload.get("service") or payload.get("intent") or payload.get("route"))
        return bool(
            service == "general"
            or (payload.get("intent") == "general" and isinstance(payload.get("answer"), str))
            or (payload.get("service") == "general" and isinstance(payload.get("message"), str))
        )

    def normalize(self, payload: dict[str, Any]) -> str:
        return "general"
