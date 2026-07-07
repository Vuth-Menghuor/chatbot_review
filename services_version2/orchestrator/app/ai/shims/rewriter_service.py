"""Rewriter shim moved into llm_first_layer/shims.

Delegates to `get_llm_first_layer_service()` while preserving a
flexible `RewriterServiceConfig` for legacy callers.
"""
from typing import Optional, Any

from .. import get_llm_first_layer_service


class RewriterServiceConfig:
    """Flexible config holder for legacy callers to avoid breaking kwargs."""
    def __init__(self, **kwargs):
        self.rewrite_provider = kwargs.get("rewrite_provider", "gemini")
        self.gemini_api_key = kwargs.get("gemini_api_key", "")
        self.gemini_model = kwargs.get("gemini_model", "gemini-3.1-flash-lite")
        self.gemini_timeout = kwargs.get("gemini_timeout", 30)
        for k, v in kwargs.items():
            setattr(self, k, v)


# Backward-compatible alias for type hints
RewriterService = Any


def get_rewriter_service(config: Optional[RewriterServiceConfig] = None) -> Any:
    if config and (getattr(config, "rewrite_provider", None) == "ollama" or hasattr(config, "ollama_host")):
        from ...services.input_rewriter import InputRewriter
        return InputRewriter(
            ollama_host=getattr(config, "ollama_host", "http://localhost:11434"),
            model=getattr(config, "ollama_model", "default")
        )
    return get_llm_first_layer_service()


__all__ = ["RewriterServiceConfig", "RewriterService", "get_rewriter_service"]
