"""Handler registry: maps intent strings to strategies."""

from __future__ import annotations

from ..core.exceptions import UnknownIntentError
from .strategies import STRATEGIES, IntentStrategy


class HandlerRegistry:
    """Lookup intent strategies."""

    @staticmethod
    def get(intent: str) -> IntentStrategy:
        if intent not in STRATEGIES:
            raise UnknownIntentError(intent)
        return STRATEGIES[intent]
