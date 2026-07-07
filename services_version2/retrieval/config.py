"""
Compatibility wrapper for retrieval configuration.
"""

from .app.config import RetrievalConfig, get_config, reset_config

__all__ = ["RetrievalConfig", "get_config", "reset_config"]