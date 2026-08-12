from typing import Any

from app.services.normalizers.base import BaseNormalizer

KNOWN_SERVICE_NAMES = {"calculator", "trade", "retrieval", "general", "unknown"}

INTENT_SERVICE_MAP = {
    # Retrieval
    "hs_code_lookup": "retrieval",
    "customs_qa": "retrieval",
    "document_lookup": "retrieval",
    "regulation_lookup": "retrieval",
    "retrieval": "retrieval",
    "rag": "retrieval",
    "search": "retrieval",

    # Trade
    "trade_query": "trade",
    "trade_statistics": "trade",
    "trade_lookup": "trade",

    # Calculator
    "tax_calculation": "calculator",
    "import_tax_calculation": "calculator",
    "calculation": "calculator",

    # General
    "general": "general",
}


class FallbackNormalizer(BaseNormalizer):
    """Provide safe service classification until each service gets its own normalizer."""

    def can_handle(self, payload: dict[str, Any]) -> bool:
        return True

    def normalize(self, payload: dict[str, Any]) -> str:
        return create_plain_text_response(payload)


# Keep fallback output intentionally small for this MVP: only the service label is new.
def create_plain_text_response(payload: dict[str, Any]) -> str:
    return service_name_from_payload(payload) or "unknown"


# Infer the service from stable payload hints without introducing service-specific normalizer classes yet.
def service_name_from_payload(payload: dict[str, Any]) -> str | None:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    for value in (
        payload.get("service"),
        metadata.get("service"),
        payload.get("intent"),
        payload.get("route"),
        payload.get("answer_source"),
    ):
        service = normalize_service_name(value)
        if service:
            return service
    return None


# Restrict service values to the initial vocabulary expected by the API contract.
def normalize_service_name(value: Any) -> str | None:
    if value is None:
        return None
    service = str(value).strip().lower().replace("-", "_")
    mapped = INTENT_SERVICE_MAP.get(service)
    if mapped:
        return mapped
    if service in {"trade", "trade_service", "trade_data"}:
        return "trade"
    if service in {"retrieval", "retriever", "rag", "search"}:
        return "retrieval"
    if service in {"general", "general_chat", "chat"}:
        return "general"
    if service in {"calculator", "calculation", "tax_calculator", "import_tax_calculation"}:
        return "calculator"
    if service == "unknown":
        return "unknown"
    return None
