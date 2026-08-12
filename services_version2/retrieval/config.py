"""
Compatibility wrapper that re-exports the canonical configuration objects
from ``app.config`` so callers at the package root can import directly from
``config`` instead of ``app.config``.

.. deprecated::
    Prefer importing from ``app.config`` directly. This shim exists only for
    backward compatibility with scripts that expect a root-level ``config``
    module.
"""

from .app.config import RetrievalConfig, get_config, reset_config

__all__ = ["RetrievalConfig", "get_config", "reset_config"]