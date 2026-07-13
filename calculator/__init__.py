"""
GDCE Calculator Service
=======================
Import tax calculation service for Cambodia customs.

Project structure:
    - app/          Main application package
    - app/main.py   FastAPI entry point
    - app/core/     Core configuration and settings
    - app/api/      API routes
    - app/services/ Business logic and domain models
    - app/data/     Database and external service adapters
    - app/ai/       AI/LLM logic
    - app/schemas/  Pydantic request/response models
    - tests/        Test suite
    - docs/         Documentation

Version: 2.1
Last Updated: 2026-07-07
"""

__version__ = "2.1.0"
__author__ = "GDCE ChatBot Team"

# Export core domain models for external use
from .app.services import (
    CalculationRequest,
    CalculationResult,
    TaxLineItem,
    TaxReference,
)
from .app.core.config import Settings, get_settings

__all__ = [
    "CalculationRequest",
    "CalculationResult",
    "TaxLineItem",
    "TaxReference",
    "Settings",
    "get_settings",
]
