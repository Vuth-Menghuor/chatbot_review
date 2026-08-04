from typing import Any

from app.services.normalizers.base import BaseNormalizer
from app.services.normalizers.calculator.formatting import is_calculator_markdown_text


class CalculatorNormalizer(BaseNormalizer):
    """Route calculator payloads without changing the existing calculator block-building functions."""

    def can_handle(self, payload: dict[str, Any]) -> bool:
        result = payload.get("result")
        answer = payload.get("answer")
        return bool(
            payload.get("calculator_result")
            or payload.get("structured_result")
            or (isinstance(result, dict) and (result.get("tax_breakdown") or result.get("phases")))
            or payload.get("service") == "calculator"
            or payload.get("intent") == "calculator"
            or (isinstance(answer, str) and is_calculator_markdown_text(answer))
        )

    def normalize(self, payload: dict[str, Any]) -> str:
        return normalize_calculator_response(payload)


# For this registry MVP, calculator normalization only identifies the service; block behavior stays unchanged.
def normalize_calculator_response(payload: dict[str, Any]) -> str:
    return "calculator"
