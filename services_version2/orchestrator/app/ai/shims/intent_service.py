"""Intent shim moved into llm_first_layer/shims.

Delegates to `get_llm_first_layer_service()` while keeping a flexible
`IntentServiceConfig` for legacy callers.
"""
from typing import Optional, Any

from .. import get_llm_first_layer_service


class IntentServiceConfig:
    """Flexible configuration holder for legacy callers.

    Accepts arbitrary keyword arguments and stores them as attributes so
    legacy code passing provider/llm_host/llm_model/timeout still works.
    """
    def __init__(self, **kwargs):
        self.provider = kwargs.get("provider", "gemini")
        self.timeout = kwargs.get("timeout", 60)
        for k, v in kwargs.items():
            setattr(self, k, v)


# Backward-compatible alias for type hints
OrchestratorIntentService = Any


def get_intent_service(config: Optional[IntentServiceConfig] = None) -> Any:
    """Return the unified llm first layer service as the intent detector."""
    return get_llm_first_layer_service()


__all__ = ["IntentServiceConfig", "OrchestratorIntentService", "get_intent_service"]
