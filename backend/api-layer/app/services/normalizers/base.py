from abc import ABC, abstractmethod
from typing import Any


class BaseNormalizer(ABC):
    """Minimal interface for routing raw orchestrator payloads to service-specific normalizers."""

    @abstractmethod
    def can_handle(self, payload: dict[str, Any]) -> bool:
        """Return True when this normalizer supports the payload."""
        raise NotImplementedError

    @abstractmethod
    def normalize(self, payload: dict[str, Any]) -> Any:
        """Normalize the supported payload into the registry's current output shape."""
        raise NotImplementedError
