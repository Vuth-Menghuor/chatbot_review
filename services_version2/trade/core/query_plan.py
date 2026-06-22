"""Query Plan Lifecycle State Containers.

Enforces clear state transitions and type safety across the 5 pipeline stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass(frozen=True)
class RawQueryPlan:
    """Stage 1 Output: Raw extracted properties from user input or LLM."""
    intent: str
    raw_origin_country: Optional[str] = None
    raw_destination_country: Optional[str] = None
    raw_partner_countries: Optional[List[str]] = None
    raw_trade_direction: Optional[str] = None
    raw_product: Optional[str] = None
    raw_mode_of_transport: Optional[Union[str, List[str]]] = None
    raw_year: Optional[int] = None
    raw_years: Optional[List[int]] = None
    raw_month: Optional[int] = None
    raw_quarter: Optional[str] = None
    raw_semester: Optional[int] = None
    raw_start_period: Optional[str] = None
    raw_end_period: Optional[str] = None
    raw_frequency: Optional[str] = None
    raw_group_by: Optional[List[str]] = None
    raw_dimensions: Optional[List[str]] = None
    raw_metrics: Optional[List[str]] = None
    raw_sort_order: Optional[str] = None
    raw_sort_metric: Optional[str] = None
    raw_limit: Optional[int] = None
    raw_offset: Optional[int] = None
    version: str = "trade_volume_1.0"
    question: Optional[str] = None


@dataclass(frozen=True)
class EnrichedQueryPlan:
    """Stage 2 Output: Synonyms and text inputs resolved to standard codes."""
    intent: str
    origin_country: Optional[str] = None
    destination_country: Optional[str] = None
    partner_countries: Optional[List[str]] = None
    trade_direction: Optional[str] = None  # IM, EX
    hs_code: Optional[str] = None
    hs_chapter: Optional[str] = None
    sitc_section: Optional[str] = None
    sitc_division: Optional[str] = None
    mode_of_transport: Optional[Union[str, List[str]]] = None
    year: Optional[int] = None
    years: Optional[List[int]] = None
    month: Optional[int] = None
    quarter: Optional[str] = None
    semester: Optional[int] = None
    start_period: Optional[str] = None
    end_period: Optional[str] = None
    frequency: Optional[str] = None
    group_by: Optional[List[str]] = None
    dimensions: Optional[List[str]] = None
    metrics: Optional[List[str]] = None
    sort_order: Optional[str] = None
    sort_metric: Optional[str] = None
    limit: Optional[int] = None
    offset: Optional[int] = None
    version: str = "trade_volume_1.0"
    hs_vs_sitc_suggestion: Optional[str] = None  # "HS" or "SITC"
    question: Optional[str] = None


@dataclass(frozen=True)
class ScopedQueryPlan:
    """Stage 3 Output: Scoping rules, base defaults, country perspective flips, and classification system locked in."""
    intent: str
    version: str
    origin_country: Optional[str]
    destination_country: Optional[str]
    partner_countries: Optional[List[str]]
    trade_direction: Optional[str]
    hs_code: Optional[str]
    hs_chapter: Optional[str]
    sitc_section: Optional[str]
    sitc_division: Optional[str]
    mode_of_transport: Optional[Union[str, List[str]]]
    year: Optional[int]
    years: Optional[List[int]]
    month: Optional[int]
    quarter: Optional[str]
    semester: Optional[int]
    start_period: Optional[str]
    end_period: Optional[str]
    frequency: Optional[str]
    group_by: List[str]
    dimensions: List[str]
    metrics: List[str]
    sort_order: Optional[str]
    sort_metric: Optional[str]
    limit: int
    offset: int
    question: Optional[str] = None


@dataclass(frozen=True)
class FinalQueryPlan:
    """Stage 4 Output: Fully structured query parameters ready for validation & serialization."""
    intent: str
    version: str
    filters: Dict[str, Any]
    metrics: List[str]
    group_by: List[str]
    dimensions: List[str]
    period: Optional[str]
    start_period: Optional[str]
    end_period: Optional[str]
    frequency: Optional[str]
    sort: Optional[str]
    limit: int
    offset: int
    extra: Dict[str, Any] = field(default_factory=dict)
