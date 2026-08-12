"""
GDCE Calculator Service - Currency Converter Layer
====================================================
Standalone currency conversion feature. Reuses the existing CurrencyHandler
and exchange-rate infrastructure without touching core tax-calculation logic.

Exported components:
    - CurrencyConverterService  (business logic)
    - converter_router          (FastAPI routes)
    - converter schemas         (Pydantic models)
"""

from __future__ import annotations

from .schemas import (
    ConvertNaturalRequest,
    ConvertNaturalResponse,
    SupportedCurrenciesResponse,
)
from .service import CurrencyConverterService
from .routes import router as converter_router

__all__ = [
    "ConvertNaturalRequest",
    "ConvertNaturalResponse",
    "SupportedCurrenciesResponse",
    "CurrencyConverterService",
    "converter_router",
]
