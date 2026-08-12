from typing import Any

from app.services.normalizers.base import BaseNormalizer
from app.services.normalizers.calculator.adapter import calculator_response_adapter


class CalculatorNormalizer(BaseNormalizer):
    """Route calculator payloads to the calculator response adapter."""

    def can_handle(self, payload: dict[str, Any]) -> bool:
        return calculator_response_adapter.can_handle(payload)

    def normalize(self, payload: dict[str, Any]) -> str:
        return normalize_calculator_response(payload)


def normalize_calculator_response(payload: dict[str, Any]) -> str:
    return calculator_response_adapter.service_name(payload)
