"""Data models for formatting operations."""
from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum

@dataclass
class CalculatorResponse:
    """Response from Calculator Service."""
    total: float  # Total tax in KHR
    breakdown: Dict[str, float]  # CD, ST, VAT, ET breakdown
    assumptions: list = None
    rates_applied: Dict[str, float] = None
    
    def __post_init__(self):
        if self.assumptions is None:
            self.assumptions = []
        if self.rates_applied is None:
            self.rates_applied = {}

@dataclass
class HSCodeInfo:
    """HS Code information from Retrieval Service."""
    hs_code: str
    description: str
    category: str = ""

class FormatterIntent(str, Enum):
    """Which type of response to format."""
    CALCULATION = "calculation"
    RETRIEVAL = "retrieval"
    TRADE_QUERY = "trade_query"
    GENERAL = "general"
    HS_CODE_LOOKUP = "hs_code_lookup"
