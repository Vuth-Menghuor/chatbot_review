"""
GDCE Calculator Service - Currency Converter Routes
====================================================
FastAPI router for standalone currency converter endpoints.

Endpoints:
    POST /v1/convert/natural  — Convert from natural-language query
    GET  /v1/currencies       — List supported currencies
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from ..api.deps import get_db
from .schemas import (
    ConvertNaturalRequest,
    ConvertNaturalResponse,
    SupportedCurrenciesResponse,
    CurrencyInfo,
)
from .service import CurrencyConverterService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["Currency Converter"])


def _get_service(db=Depends(get_db)) -> CurrencyConverterService:
    """Dependency factory: create converter service with DB."""
    return CurrencyConverterService(db)


# =====================================================================
# POST /v1/convert/natural
# =====================================================================

@router.post(
    "/convert/natural",
    response_model=ConvertNaturalResponse,
    summary="Convert currency from natural language",
    description="Parse a free-form query like '40000usd to khr' and convert using the latest rate.",
)
async def convert_currency_natural(
    request: ConvertNaturalRequest,
    service: CurrencyConverterService = Depends(_get_service),
) -> ConvertNaturalResponse:
    """
    Convert currency from a natural-language query string.

    Accepts flexible input:
    - "40000usd to khr"
    - "$500 to euro"
    - "1000 THB = KHR"
    - "convert 40000 USD to KHR"
    """
    try:
        result = service.convert_natural(query=request.query)
        return ConvertNaturalResponse(**result)
    except ValueError as exc:
        logger.warning(f"Natural converter validation error: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(f"Natural converter internal error: {exc}")
        raise HTTPException(status_code=500, detail="Internal error during currency conversion") from exc


# =====================================================================
# GET /v1/currencies
# =====================================================================

@router.get(
    "/currencies",
    response_model=SupportedCurrenciesResponse,
    summary="List supported currencies",
    description="Return all currencies supported by the converter with metadata.",
)
async def get_supported_currencies(
    service: CurrencyConverterService = Depends(_get_service),
) -> SupportedCurrenciesResponse:
    """
    List all supported currencies.

    Includes ISO code, full name, symbol, and decimal precision.
    """
    try:
        currencies = service.get_supported_currencies()
        return SupportedCurrenciesResponse(
            currencies=[CurrencyInfo(**c) for c in currencies],
            count=len(currencies),
        )
    except Exception as exc:
        logger.exception(f"Currency list error: {exc}")
        raise HTTPException(status_code=500, detail="Internal error retrieving currency list") from exc
