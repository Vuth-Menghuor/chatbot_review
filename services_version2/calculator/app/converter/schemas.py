"""
GDCE Calculator Service - Currency Converter Schemas
======================================================
Pydantic request/response models for the standalone currency converter.
"""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class CurrencyInfo(BaseModel):
    """Metadata for a supported currency."""

    code: str
    name: str
    symbol: str
    decimals: int


class SupportedCurrenciesResponse(BaseModel):
    """Response listing all supported currencies."""

    currencies: List[CurrencyInfo]
    count: int


class ConvertNaturalRequest(BaseModel):
    """Free-form conversion query."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description=(
            "Natural-language conversion request. Examples:\n"
            "- '40000usd to khr'\n"
            "- '$500 to euro'\n"
            "- '1000 THB = KHR'\n"
            "- 'convert 40000 USD to KHR'"
        ),
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "40000usd to khr",
            }
        }


class ConvertNaturalResponse(BaseModel):
    """Response after parsing a natural-language conversion query."""

    query: str = Field(..., description="Original query string")
    parsed_amount: float = Field(..., description="Extracted numeric amount")
    parsed_from: str = Field(..., description="Extracted source currency (normalized)")
    parsed_to: str = Field(..., description="Extracted target currency (normalized)")
    from_currency: str
    to_currency: str
    exchange_rate: float
    converted_amount: float
    note: str

    class Config:
        json_schema_extra = {
            "example": {
                "query": "40000usd to khr",
                "parsed_amount": 40000,
                "parsed_from": "USD",
                "parsed_to": "KHR",
                "from_currency": "USD",
                "to_currency": "KHR",
                "exchange_rate": 4042.0,
                "converted_amount": 161680000.0,
                "note": "1 USD = 4042.0000 KHR",
            }
        }


__all__ = [
    "ConvertNaturalRequest",
    "ConvertNaturalResponse",
    "SupportedCurrenciesResponse",
    "CurrencyInfo",
]
