"""
GDCE Calculator Service
=======================
Import tax calculation service for Cambodia customs.

Microservice structure:
    - core/       Business logic (zero framework dependencies)
    - api/        FastAPI endpoints and schemas
    - infrastructure/  Database and external service adapters
    - tests/      Test suite

Version: 2.0
Last Updated: 2026-04-08
"""

__version__ = "2.0.0"
__author__ = "GDCE ChatBot Team"

# Export core domain models for external use
from .core import (
    CalculationRequest,
    CalculationResult,
    TaxLineItem,
    TaxReference,
    Settings,
    get_settings,
)

__all__ = [
    "CalculationRequest",
    "CalculationResult",
    "TaxLineItem",
    "TaxReference",
    "Settings",
    "get_settings",
]
