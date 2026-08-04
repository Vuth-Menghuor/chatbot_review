from typing import Any

from app.services.normalizers.base import BaseNormalizer


class NormalizerRegistry:
    """Select the first normalizer that can handle a payload and otherwise use the fallback."""

    def __init__(self, normalizers: list[BaseNormalizer], fallback: BaseNormalizer) -> None:
        self.normalizers = normalizers
        self.fallback = fallback

    def normalize(self, payload: dict[str, Any]) -> Any:
        for normalizer in self.normalizers:
            if normalizer.can_handle(payload):
                return normalizer.normalize(payload)

        return self.fallback.normalize(payload)
