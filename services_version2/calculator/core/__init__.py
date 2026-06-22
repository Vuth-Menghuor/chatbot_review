"""
GDCE Calculator Service - Core Package
=======================================
Business logic and domain models with zero framework dependencies.
API consumers depend on this, not vice versa.

Exports:
    - models: CalculationRequest, CalculationResult, TaxLineItem, TaxReference
    - config: Settings, get_settings() [imported from root]
"""

from ..config import Settings, get_settings  # noqa: F401
from .models import (  # noqa: F401
    CalculationRequest,
    CalculationResult,
    TaxLineItem,
    TaxReference,
)

__all__ = [
    "Settings",
    "get_settings",
    "CalculationRequest",
    "CalculationResult",
    "TaxLineItem",
    "TaxReference",
]
