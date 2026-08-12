from typing import Any

from app.schemas.normalized_chat import ChatContentBlock
from app.services.normalizers.calculator.adapter import (
    blocks_from_structured_calculator_result,
    build_calculator_blocks,
    first_structured_calculator_result,
)


def normalize_structured_calculator_blocks(payload: dict[str, Any], content: str) -> list[ChatContentBlock]:
    return build_calculator_blocks(payload, content)
